"""Testes do cliente OpenRouter usado na produção e na revisão."""

import json

import httpx
import pytest

from fla10_agents.writing.provider import (
    OpenRouterProvider,
    ProviderError,
    default_review_model,
    default_writing_model,
)


def make_provider(handler, **kwargs) -> OpenRouterProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterProvider(
        "test-key",
        "https://openrouter.example/api/v1",
        client=client,
        base_delay=0.0,
        **kwargs,
    )


def success_response(content: str = '{"ok": true}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-5.5",
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def test_provider_requires_api_key() -> None:
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider("   ")


def test_provider_returns_text_and_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return success_response()

    provider = make_provider(handler)
    response = provider.complete(
        "Escreva a matéria.",
        model="openai/gpt-5.5",
        system="Você é o produtor.",
        max_tokens=1234,
    )

    assert response.text == '{"ok": true}'
    assert response.served_model == "openai/gpt-5.5"
    assert response.usage["prompt_tokens"] == 10
    assert response.finish_reason == "stop"

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "openai/gpt-5.5"
    assert body["max_completion_tokens"] == 1234
    assert body["provider"] == {"allow_fallbacks": False}
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"] == "Escreva a matéria."

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer test-key"


def test_provider_retries_transient_status() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, json={"error": "limite"})
        return success_response()

    provider = make_provider(handler)
    response = provider.complete("texto", model="openai/gpt-5.5")

    assert calls["count"] == 2
    assert response.text == '{"ok": true}'


def test_provider_does_not_retry_client_error() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, json={"error": "chave inválida"})

    provider = make_provider(handler)

    with pytest.raises(ProviderError, match="401"):
        provider.complete("texto", model="openai/gpt-5.5")

    assert calls["count"] == 1


def test_provider_error_does_not_leak_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "falha"})

    provider = make_provider(handler)

    with pytest.raises(ProviderError) as excinfo:
        provider.complete("texto", model="openai/gpt-5.5")

    assert "test-key" not in str(excinfo.value)


def test_provider_retries_without_json_mode_when_rejected() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payloads.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format"})
        return success_response()

    provider = make_provider(handler)
    response = provider.complete("texto", model="openai/gpt-5.5")

    assert len(payloads) == 2
    assert "response_format" in payloads[0]
    assert "response_format" not in payloads[1]
    assert response.text == '{"ok": true}'


def test_provider_rejects_truncated_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"ok": '},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    provider = make_provider(handler)

    with pytest.raises(ProviderError, match="finish_reason"):
        provider.complete("texto", model="openai/gpt-5.5")


def test_provider_rejects_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = make_provider(handler)

    with pytest.raises(ProviderError, match="inesperada"):
        provider.complete("texto", model="openai/gpt-5.5")


def test_provider_rejects_empty_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "   "}, "finish_reason": "stop"}
                ]
            },
        )

    provider = make_provider(handler)

    with pytest.raises(ProviderError, match="vazio"):
        provider.complete("texto", model="openai/gpt-5.5")


def test_default_models_are_configurable(monkeypatch) -> None:
    monkeypatch.delenv("FLA10_WRITING_MODEL", raising=False)
    monkeypatch.delenv("FLA10_REVIEW_MODEL", raising=False)
    assert default_writing_model() == "openai/gpt-5.5"
    assert default_review_model() == "openai/gpt-5.5"

    monkeypatch.setenv("FLA10_WRITING_MODEL", "openai/gpt-5.4")
    assert default_review_model() == "openai/gpt-5.4"

    monkeypatch.setenv("FLA10_REVIEW_MODEL", "openai/gpt-5.4-mini")
    assert default_review_model() == "openai/gpt-5.4-mini"
