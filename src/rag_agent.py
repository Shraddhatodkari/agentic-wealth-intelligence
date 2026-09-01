"""
RAG Agent
---------
Embeds filing chunks into a local ChromaDB collection and answers
ad-hoc analyst questions ("what's the debt maturity schedule?") by
retrieving the most relevant chunks and passing them to the LLM.

Uses ChromaDB's default embedding function (all-MiniLM-L6-v2, runs
locally, no API key needed) so retrieval works identically in mock
and live LLM modes - only the final answer-generation call depends
on LLM_MODE.
"""

from __future__ import annotations

import hashlib
from typing import List

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from .ingestion_agent import Chunk
from .llm_client import LLMClient
from .schemas import RAGAnswer


class HashingEmbeddingFunction(EmbeddingFunction):
    """
    Deterministic, dependency-free embedding function based on hashed
    word n-grams. Used as the default so indexing/retrieval work fully
    offline (no model download, no API key).

    For production use, swap in `chromadb.utils.embedding_functions
    .SentenceTransformerEmbeddingFunction` (all-MiniLM-L6-v2) or a
    Gemini embedding call once outbound network access to fetch the
    model - or the embeddings API - is available.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def name(self) -> str:
        return "hashing_embedding_function"

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for text in input:
            vec = [0.0] * self.dim
            words = text.lower().split()
            for i in range(len(words)):
                for n in (1, 2):
                    gram = " ".join(words[i : i + n])
                    if not gram:
                        continue
                    idx = int(hashlib.md5(gram.encode(), usedforsecurity=False).hexdigest(), 16) % self.dim
                    vec[idx] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def get_embedding_function(mode: str = "hashing"):
    """
    Factory for the embedding function used by RAGAgent, selected via
    `Settings.embedding_mode` ("hashing" | "sentence_transformer").

    "sentence_transformer" uses chromadb's built-in
    SentenceTransformerEmbeddingFunction (all-MiniLM-L6-v2) for real
    semantic search - it downloads model weights from HuggingFace on
    first use, so it requires outbound network access not available in
    every sandboxed environment. This raises with a clear message rather
    than silently falling back, so a misconfigured deployment fails loudly
    instead of quietly using a lower-quality embedding.
    """
    if mode == "hashing":
        return HashingEmbeddingFunction()

    if mode == "sentence_transformer":
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            return SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        except Exception as e:
            raise RuntimeError(
                "EMBEDDING_MODE=sentence_transformer requires network access to "
                "download the all-MiniLM-L6-v2 model from HuggingFace on first use, "
                "and the `sentence-transformers` package. Install it with "
                "`pip install sentence-transformers`, ensure network access, or set "
                "EMBEDDING_MODE=hashing to use the offline default."
            ) from e

    raise ValueError(f"Unknown embedding mode: {mode!r}")


RAG_PROMPT_TEMPLATE = """Answer the analyst's question using ONLY the
context below. If the context doesn't contain the answer, say so.

Context:
---
{context}
---

Question: {question}
"""


class RAGAgent:
    def __init__(
        self,
        llm: LLMClient,
        collection_name: str = "filing_chunks",
        embedding_function=None,
    ):
        self.llm = llm
        self.client = chromadb.EphemeralClient()
        self.embedding_function = embedding_function or HashingEmbeddingFunction()
        # Fresh collection per instance keeps tests isolated from each other
        self.collection = self.client.get_or_create_collection(
            collection_name, embedding_function=self.embedding_function
        )

    def index(self, chunks: List[Chunk]) -> int:
        if not chunks:
            return 0
        self.collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"section": c.section} for c in chunks],
        )
        return len(chunks)

    def retrieve(self, question: str, k: int = 4) -> List[str]:
        if self.collection.count() == 0:
            return []
        results = self.collection.query(query_texts=[question], n_results=min(k, self.collection.count()))
        return results["ids"][0]

    def answer(self, question: str, k: int = 4, mock_response: dict | None = None) -> RAGAnswer:
        top_ids = self.retrieve(question, k=k)
        docs = self.collection.get(ids=top_ids)["documents"] if top_ids else []
        context = "\n---\n".join(docs)
        prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

        default_mock = {
            "question": question,
            "answer": "No context available.",
            "source_chunks": top_ids,
        }
        result = self.llm.structured_call(
            prompt=prompt,
            schema=RAGAnswer,
            mock_response=mock_response or {**default_mock, "source_chunks": top_ids},
        )
        result.source_chunks = top_ids
        return result
