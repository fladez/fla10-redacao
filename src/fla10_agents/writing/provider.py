"""Provedores de linguagem para produção e revisão editorial."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from fla10_agents.config import OpenRouterSettings

RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_WRITING_MODEL = "openai/gpt-5.5"


def default_writing_model() -> str:
    return os.getenv("FLA10_WRITING_MODEL", "").strip() or DEFAULT_WRITING_MODEL


def default_review_model() -> str:
    configured = os.getenv("FLA10_REVIEW_MODEL", "").strip()
    return configured or default_writing_model()


class ProviderError(RuntimeError):
    """Falha segura ao chamar o provedor de linguagem."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    served_model: str | None
    usage: dict[str, Any]
    elapsed_seconds: float
    finish_reason: str


class LLMProvider(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> LLMResponse: ...


class OpenRouterProvider:
    """Cliente mínimo do OpenRouter, sem fallback silencioso de modelo."""

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://openrouter.ai/api/v1",
        *,
        client: httpx.Client | None = None,
        attempts: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        if not api_key.strip():
            raise ProviderError("OPENROUTER_API_KEY não definida.")

        self.api_key = api_key.strip()
        self.api_url = api_url.rstrip("/")
        self._client = client
        self._attempts = max(1, attempts)
        self._base_delay = max(0.0, base_delay)

    @classmethod
    def from_env(cls, **kwargs: Any) -> OpenRouterProvider:
        settings = OpenRouterSettings.from_env()
        return cls(settings.api_key, settings.api_url, **kwargs)

    def _client_or_create(self) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False

        return httpx.Client(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, connect=30.0)
        ), True

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        client, owns_client = self._client_or_create()
        last_error: Exception | None = None

        try:
            for attempt in range(self._attempts):
                try:
                    response = client.post(
                        f"{self.api_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://fla10.news",
                            "X-Title": "Fla10-Agents - editorial writing",
                        },
                        json=payload,
                    )
                except httpx.TransportError as exc:
                    last_error = exc
                else:
                    if (
                        response.status_code not in RETRY_STATUS_CODES
                        or attempt == self._attempts - 1
                    ):
                        return response
                    last_error = None

                if attempt < self._attempts - 1:
                    time.sleep(self._base_delay * (2**attempt))
        finally:
            if owns_client:
                client.close()

        if last_error is not None:
            raise ProviderError(
                "Falha de transporte ao chamar o OpenRouter; a chave não foi exibida."
            ) from last_error

        raise ProviderError("Não foi possível concluir a chamada ao OpenRouter.")

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 1.0,
            "max_completion_tokens": max_tokens,
            "provider": {"allow_fallbacks": False},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started_at = time.perf_counter()
        response = self._post(payload)

        if response.status_code == 400 and json_mode:
            payload.pop("response_format", None)
            response = self._post(payload)

        elapsed = round(time.perf_counter() - started_at, 3)

        if response.is_error:
            raise ProviderError(
                f"OpenRouter respondeu HTTP {response.status_code} para {model}. "
                "A chave não será exibida; consulte o painel do provedor."
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice["finish_reason"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Resposta inesperada do OpenRouter para {model}."
            ) from exc

        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"O modelo {model} retornou conteúdo vazio.")

        if finish_reason != "stop":
            raise ProviderError(
                f"O modelo {model} não concluiu normalmente "
                f"(finish_reason: {finish_reason!r})."
            )

        return LLMResponse(
            text=text,
            model=model,
            served_model=data.get("model"),
            usage=data.get("usage") or {},
            elapsed_seconds=elapsed,
            finish_reason=finish_reason,
        )
