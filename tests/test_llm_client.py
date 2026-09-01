from unittest.mock import MagicMock, patch

import pytest

from src.config import settings
from src.llm_client import LLMCallError, LLMClient
from src.schemas import RAGAnswer


def test_mock_mode_returns_validated_schema_without_any_external_call():
    client = LLMClient(mode="mock")

    result = client.structured_call(
        prompt="test",
        schema=RAGAnswer,
        mock_response={
            "question": "q",
            "answer": "a",
            "source_chunks": [],
        },
    )

    assert isinstance(result, RAGAnswer)
    assert result.answer == "a"


def test_live_mode_without_api_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(
        "src.llm_client.settings.gemini_api_key",
        "",
    )

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        LLMClient(mode="live")


@patch("src.llm_client.genai.Client")
def test_live_mode_parses_gemini_response(mock_client_cls, monkeypatch):
    monkeypatch.setattr(
        "src.llm_client.settings.gemini_api_key",
        "fake-key-for-test",
    )

    mock_client = MagicMock()

    mock_client.models.generate_content.return_value = MagicMock(
        text='{"question": "q", "answer": "a", "source_chunks": []}'
    )

    mock_client_cls.return_value = mock_client

    client = LLMClient(mode="live")

    result = client.structured_call(
        prompt="test prompt",
        schema=RAGAnswer,
        mock_response={},
    )

    assert isinstance(result, RAGAnswer)
    assert result.answer == "a"


def test_ollama_mode_construction_does_not_require_ollama_running():
    client = LLMClient(mode="ollama")

    assert client.mode == "ollama"


@patch("requests.post")
def test_ollama_mode_parses_response(mock_post):
    mock_post.return_value = MagicMock(
        json=lambda: {"response": ('{"question": "q", "answer": "a", "source_chunks": []}')},
        raise_for_status=lambda: None,
    )

    client = LLMClient(mode="ollama")

    result = client.structured_call(
        prompt="test prompt",
        schema=RAGAnswer,
        mock_response={},
    )

    assert isinstance(result, RAGAnswer)
    assert result.answer == "a"


@patch("requests.post")
def test_ollama_mode_connection_error_gives_actionable_message(mock_post):
    import requests

    mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")

    client = LLMClient(mode="ollama")

    with pytest.raises(LLMCallError, match="running"):
        client.structured_call(
            prompt="test prompt",
            schema=RAGAnswer,
            mock_response={},
        )


@patch("requests.post")
def test_ollama_mode_sends_configured_model_name(
    mock_post,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.llm_client.settings.ollama_model",
        "llama3.2",
    )

    mock_post.return_value = MagicMock(
        json=lambda: {"response": ('{"question": "q", "answer": "a", "source_chunks": []}')},
        raise_for_status=lambda: None,
    )

    client = LLMClient(mode="ollama")

    client.structured_call(
        prompt="test prompt",
        schema=RAGAnswer,
        mock_response={},
    )

    # Inspect the actual HTTP request payload.
    payload = mock_post.call_args.kwargs["json"]

    assert payload["model"] == settings.ollama_model


@patch("requests.post")
def test_ollama_mode_sends_json_schema_format_to_force_structured_output(
    mock_post,
):
    mock_post.return_value = MagicMock(
        json=lambda: {"response": ('{"question": "q", "answer": "a", "source_chunks": []}')},
        raise_for_status=lambda: None,
    )

    client = LLMClient(mode="ollama")

    client.structured_call(
        prompt="test prompt",
        schema=RAGAnswer,
        mock_response={},
    )

    payload = mock_post.call_args.kwargs["json"]

    assert payload["format"] == RAGAnswer.model_json_schema()
