import os

import pytest

from src.ingestion_agent import IngestionAgent
from src.llm_client import LLMClient
from src.rag_agent import HashingEmbeddingFunction, RAGAgent, get_embedding_function
from src.schemas import RAGAnswer

SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "sample_filings",
    "nimbus_dynamics_10k_fy2025.txt",
)


def _chunks():
    ing = IngestionAgent(chunk_size=300, chunk_overlap=50)
    text = ing.load_local_filing(SAMPLE_PATH)
    return ing.chunk(text)


def test_index_adds_all_chunks():
    llm = LLMClient(mode="mock")
    rag = RAGAgent(llm, collection_name="test_index_all")
    chunks = _chunks()
    count = rag.index(chunks)
    assert count == len(chunks)
    assert rag.collection.count() == len(chunks)


def test_retrieve_returns_relevant_chunk_ids():
    llm = LLMClient(mode="mock")
    rag = RAGAgent(llm, collection_name="test_retrieve")
    rag.index(_chunks())
    ids = rag.retrieve("What is the leverage ratio covenant?", k=3)
    assert len(ids) > 0
    assert len(ids) <= 3


def test_retrieve_on_empty_index_returns_empty_list():
    llm = LLMClient(mode="mock")
    rag = RAGAgent(llm, collection_name="test_empty")
    assert rag.retrieve("anything") == []


def test_answer_returns_valid_schema_with_sources():
    llm = LLMClient(mode="mock")
    rag = RAGAgent(llm, collection_name="test_answer")
    rag.index(_chunks())
    mock = {
        "question": "What is the leverage ratio?",
        "answer": "The leverage ratio was 3.3x against a covenant limit of 3.5x.",
        "source_chunks": [],
    }
    result = rag.answer("What is the leverage ratio?", k=3, mock_response=mock)
    assert isinstance(result, RAGAnswer)
    assert len(result.source_chunks) > 0


def test_embedding_factory_returns_hashing_by_default():
    fn = get_embedding_function("hashing")
    assert isinstance(fn, HashingEmbeddingFunction)


def test_embedding_factory_rejects_unknown_mode():
    with pytest.raises(ValueError):
        get_embedding_function("not_a_real_mode")
