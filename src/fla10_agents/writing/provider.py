"""Provedores de linguagem para produção e revisão editorial."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

OPENCODE_DEFAULT_TIMEOUT_SECONDS = 600.0
OPENCODE_DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"

DEFAULT_WRITING_MODEL = OPENCODE_DEFAULT_MODEL


def default_writing_model() -> str:
    configured = os.getenv("FLA10_WRITING_MODEL", "").strip()
    return configured or DEFAULT_WRITING_MODEL


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


class OpenCodeProvider:
    """Executa o modelo gratuito pelo runtime local do OpenCode.

    O prompt é enviado pela entrada padrão, sem aparecer na linha de comando.
    O runtime controla a geração; `max_tokens`, `temperature` e `json_mode`
    não têm equivalente na CLI e são preservados apenas no contrato.
    """

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout: float = OPENCODE_DEFAULT_TIMEOUT_SECONDS,
        working_dir: str | Path | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.executable = executable or find_opencode_executable()
        self.timeout = max(1.0, timeout)
        self.working_dir = str(
            Path(working_dir).expanduser()
            if working_dir is not None
            else Path(tempfile.gettempdir())
        )
        self._runner = runner or subprocess.run

    @classmethod
    def from_env(cls, **kwargs: Any) -> OpenCodeProvider:
        executable = os.getenv("FLA10_OPENCODE_BIN", "").strip() or None
        timeout_value = os.getenv("FLA10_OPENCODE_TIMEOUT", "").strip()
        timeout = (
            float(timeout_value)
            if timeout_value
            else OPENCODE_DEFAULT_TIMEOUT_SECONDS
        )
        return cls(executable, timeout=timeout, **kwargs)

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
        del max_tokens, temperature, json_mode

        full_prompt = prompt
        if system:
            full_prompt = (
                "# Instruções de sistema\n\n"
                f"{system.strip()}\n\n"
                "# Tarefa\n\n"
                f"{prompt}"
            )

        command = [
            self.executable,
            "run",
            "--model",
            model,
            "--format",
            "json",
            "--archived",
            "--auto",
        ]

        started_at = time.perf_counter()

        try:
            completed = self._runner(
                command,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                "Runtime do OpenCode não encontrado. "
                "Configure FLA10_OPENCODE_BIN com o caminho do executável."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"O modelo {model} excedeu o limite de {self.timeout:.0f} segundos."
            ) from exc
        except OSError as exc:
            raise ProviderError(
                "Não foi possível executar o runtime local do OpenCode."
            ) from exc

        elapsed = round(time.perf_counter() - started_at, 3)

        if completed.returncode != 0:
            raise ProviderError(
                f"O runtime do OpenCode terminou com código "
                f"{completed.returncode} para {model}."
            )

        text, finish_reason, usage = parse_opencode_events(
            completed.stdout,
            model=model,
        )

        if finish_reason != "stop":
            raise ProviderError(
                f"O modelo {model} não concluiu normalmente "
                f"(finish_reason: {finish_reason!r})."
            )

        return LLMResponse(
            text=text,
            model=model,
            served_model=model,
            usage=usage,
            elapsed_seconds=elapsed,
            finish_reason=finish_reason,
        )


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def parse_opencode_events(
    output: str,
    *,
    model: str,
) -> tuple[str, str, dict[str, Any]]:
    """Lê os eventos JSON emitidos por `opencode run --format json`."""
    text_parts: list[str] = []
    finish_reason: str | None = None
    usage: dict[str, Any] = {}
    saw_event = False

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except ValueError:
            continue

        if not isinstance(event, dict):
            continue

        saw_event = True
        event_type = event.get("type")
        part = event.get("part")
        if not isinstance(part, dict):
            part = {}

        if event_type == "text":
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        elif event_type == "step_finish":
            reason = part.get("reason")
            if isinstance(reason, str):
                finish_reason = reason
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                prompt_tokens = _non_negative_int(tokens.get("input"))
                completion_tokens = _non_negative_int(tokens.get("output"))
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "reasoning_tokens": _non_negative_int(tokens.get("reasoning")),
                    "cost": part.get("cost", 0),
                    "cache": tokens.get("cache") or {},
                }
        elif event_type == "error":
            message = part.get("error") or event.get("error")
            if isinstance(message, dict):
                message = message.get("message")
            detail = str(message).strip() if message else "erro não detalhado"
            raise ProviderError(
                f"O runtime do OpenCode informou erro para {model}: {detail}"
            )

    if not saw_event:
        raise ProviderError(
            f"O runtime do OpenCode não retornou eventos reconhecíveis para {model}."
        )

    text = "".join(text_parts).strip()
    if not text:
        raise ProviderError(f"O modelo {model} retornou conteúdo vazio.")

    if finish_reason is None:
        raise ProviderError(
            f"O modelo {model} não informou a conclusão da geração."
        )

    return text, finish_reason, usage


def find_opencode_executable() -> str:
    """Localiza o binário do OpenCode sem depender de um caminho fixo."""
    configured = os.getenv("FLA10_OPENCODE_BIN", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        raise ProviderError(
            "FLA10_OPENCODE_BIN aponta para um arquivo inexistente."
        )

    found = shutil.which("opencode")
    if found:
        return found

    runtime_root = (
        Path.home()
        / "Library"
        / "Application Support"
        / "OpenBot"
        / "provider-runtimes"
        / "opencode"
    )
    candidates = sorted(
        (
            *runtime_root.glob("*/bin/opencode"),
            *runtime_root.glob("*/*/bin/opencode"),
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return str(candidates[0])

    raise ProviderError(
        "Runtime do OpenCode não encontrado. Instale o OpenCode ou defina "
        "FLA10_OPENCODE_BIN com o caminho do executável."
    )


def build_provider() -> LLMProvider:
    """Retorna o motor gratuito DeepSeek V4 pelo runtime local do OpenCode."""
    return OpenCodeProvider.from_env()
