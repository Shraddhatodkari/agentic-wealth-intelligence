"""
Unified LLM client.

Supports:
- mock: deterministic tests only
- live: Gemini
- ollama: local/production LLM mode

All structured responses are validated through Pydantic.
"""

from __future__ import annotations

import json
from typing import Any, Type

import requests
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.config import settings

# Backwards-compatible alias used by existing tests/integrations.
OLLAMA_MODEL_NAME = settings.ollama_model


class LLMCallError(RuntimeError):
    """Raised when an LLM call fails or returns invalid structured data."""


class LLMClient:
    """Unified client for mock, Gemini, and Ollama modes."""

    SUPPORTED_MODES = {"mock", "live", "ollama"}

    def __init__(self, mode: str | None = None):
        self.mode = (mode or settings.llm_mode).lower()
        self._client = None

        if self.mode not in self.SUPPORTED_MODES:
            raise ValueError(
                f"Unsupported LLM mode: {self.mode}. Expected one of: {sorted(self.SUPPORTED_MODES)}"
            )

        if self.mode == "live":
            api_key = settings.gemini_api_key

            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is required when LLM_MODE=live")

            self._client = genai.Client(api_key=api_key)

    def structured_call(
        self,
        prompt: str,
        schema: Type[BaseModel],
        mock_response: dict[str, Any] | None = None,
    ) -> BaseModel:
        """
        Execute an LLM call and return a validated Pydantic object.

        No raw LLM response is allowed to propagate through the application.
        """

        if self.mode == "mock":
            if mock_response is None:
                raise ValueError("mock_response is required in mock mode")

            try:
                return schema.model_validate(mock_response)
            except ValidationError as exc:
                raise LLMCallError(f"Mock response failed schema validation: {exc}") from exc

        if self.mode == "live":
            return self._gemini_call(prompt, schema)

        if self.mode == "ollama":
            return self._ollama_call(prompt, schema)

        raise LLMCallError(f"Unsupported LLM mode: {self.mode}")

    def _gemini_call(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """Call Gemini with native structured-output enforcement."""

        if self._client is None:
            raise LLMCallError("Gemini client is not initialized")

        try:
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )

            text = getattr(response, "text", None)

            if not text:
                raise LLMCallError("Gemini returned an empty response")

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMCallError(f"Gemini returned invalid JSON: {exc}") from exc

            try:
                return schema.model_validate(parsed)
            except ValidationError as exc:
                raise LLMCallError(f"Gemini response failed schema validation: {exc}") from exc

        except LLMCallError:
            raise

        except Exception as exc:
            raise LLMCallError(f"Gemini request failed: {exc}") from exc

    def _ollama_call(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """
        Call Ollama using native JSON-schema constrained output.

        Ollama remains the intended local/production mode.
        """

        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {
                "temperature": 0,
                "num_ctx": 2048,
            },
        }

        try:
            response = requests.post(
                settings.ollama_url,
                json=payload,
                timeout=600,
            )

            response.raise_for_status()

        except requests.exceptions.ConnectionError as exc:
            raise LLMCallError(
                "Could not connect to Ollama at "
                f"{settings.ollama_url}. "
                "Make sure Ollama is running and the configured model "
                f"'{settings.ollama_model}' is available."
            ) from exc

        except requests.exceptions.Timeout as exc:
            raise LLMCallError(
                "Ollama request timed out after 600 seconds. "
                "The local model may be overloaded or the prompt "
                "may be too large."
            ) from exc

        except requests.exceptions.RequestException as exc:
            raise LLMCallError(f"Ollama request failed: {exc}") from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise LLMCallError("Ollama returned a non-JSON HTTP response.") from exc

        text = result.get("response", "").strip()

        if not text:
            raise LLMCallError("Ollama returned an empty response.")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMCallError(f"Ollama returned invalid JSON: {exc}. Raw response: {text[:500]}") from exc

        # Normalize common LLM confidence formats before strict schema validation.
        # The application schema intentionally uses 0.0-1.0.
        # Models sometimes return "2/10", 2, or 8/10 despite the prompt.
        # Convert those representations deterministically rather than weakening
        # the Pydantic contract.
        if isinstance(parsed, dict) and "confidence_score" in parsed:
            confidence = parsed["confidence_score"]

            if isinstance(confidence, str):
                match = re.fullmatch(
                    r"\s*(\d+(?:\.\d+)?)\s*/\s*10\s*",
                    confidence,
                )
                if match:
                    parsed["confidence_score"] = float(match.group(1)) / 10.0
                else:
                    try:
                        parsed["confidence_score"] = float(confidence)
                    except ValueError:
                        pass

            elif isinstance(confidence, (int, float)):
                if 1 < float(confidence) <= 10:
                    parsed["confidence_score"] = float(confidence) / 10.0

        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise LLMCallError(
                f"Ollama response failed schema validation: {exc}. Raw response: {text[:1000]}"
            ) from exc

