"""Adaptador CrewAI para o motor gratuito DeepSeek V4 do OpenCode.

O CrewAI chama este LLM como qualquer outro provedor. Cada chamada executa o
CLI local do OpenCode, envia o prompt pela entrada padrão e lê os eventos JSON
de volta. Não há chave de API nem custo por geração.

O adaptador declara que não suporta function calling nativo. Com isso, o
CrewAI usa o laço ReAct em texto: descreve as ferramentas no prompt, o modelo
responde com "Action:" e "Action Input:", e o CrewAI executa a ferramenta.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from crewai.llms.base_llm import BaseLLM
from pydantic import model_validator

OPENCODE_MODEL = "opencode/deepseek-v4.1-flash-free"
DEFAULT_TIMEOUT_SECONDS = 900.0

PLAIN_AGENT_PROMPT = """\
You are a plain text generation engine. You have no tools and no access to
files, shell, the web, or the user's environment. Never mention tools,
permissions, files, or your runtime.

Follow the user's instructions exactly, including any requested output format
such as Thought, Action, Action Input, Observation, and Final Answer. When the
user asks for a ReAct-style tool call, write the Action and Action Input lines
as text; do not try to execute anything.

Do not add commentary about your capabilities. Produce only the requested
content.
"""


class OpenCodeError(RuntimeError):
    """Falha ao executar o runtime local do OpenCode."""


def find_opencode_executable() -> str:
    """Localiza o binário do OpenCode sem depender de caminho fixo."""
    configured = os.getenv("FLA10_OPENCODE_BIN", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        raise OpenCodeError(
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

    raise OpenCodeError(
        "Runtime do OpenCode não encontrado. Instale o OpenCode ou defina "
        "FLA10_OPENCODE_BIN com o caminho do executável."
    )


def _positive_float(value: object, default: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_int(value: object) -> int:
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


def render_messages(messages: str | list[dict[str, Any]]) -> str:
    """Transforma a lista de mensagens do CrewAI em um único prompt."""
    if isinstance(messages, str):
        return messages

    labels = {
        "system": "Instruções de sistema",
        "user": "Tarefa",
        "assistant": "Resposta anterior do assistente",
        "tool": "Resultado da ferramenta",
    }
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content")
        if isinstance(content, list):
            text = " ".join(
                block["text"]
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            )
        elif content is None:
            text = ""
        else:
            text = str(content)

        if not text.strip():
            continue
        parts.append(f"# {labels.get(role, role.capitalize())}\n\n{text.strip()}")

    return "\n\n".join(parts)


def parse_opencode_events(output: str, *, model: str) -> tuple[str, str, dict[str, Any]]:
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
                prompt_tokens = _as_int(tokens.get("input"))
                completion_tokens = _as_int(tokens.get("output"))
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "reasoning_tokens": _as_int(tokens.get("reasoning")),
                }
        elif event_type == "error":
            message = part.get("error") or event.get("error")
            if isinstance(message, dict):
                message = message.get("message")
            detail = str(message).strip() if message else "erro não detalhado"
            raise OpenCodeError(
                f"O runtime do OpenCode informou erro para {model}: {detail}"
            )

    if not saw_event:
        raise OpenCodeError(
            f"O runtime do OpenCode não retornou eventos reconhecíveis para {model}."
        )

    text = "".join(text_parts).strip()
    if not text:
        raise OpenCodeError(f"O modelo {model} retornou conteúdo vazio.")

    if finish_reason is None:
        raise OpenCodeError(
            f"O modelo {model} não informou a conclusão da geração."
        )

    return text, finish_reason, usage


class OpenCodeLLM(BaseLLM):
    """LLM do CrewAI executado pelo runtime local do OpenCode."""

    model: str = OPENCODE_MODEL
    executable: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    working_dir: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if not data.get("model"):
            data["model"] = OPENCODE_MODEL
        if not data.get("timeout"):
            data["timeout"] = _positive_float(
                os.getenv("FLA10_OPENCODE_TIMEOUT", "").strip(),
                DEFAULT_TIMEOUT_SECONDS,
            )
        return data

    def model_post_init(self, __context: Any, /) -> None:
        if not self.executable:
            self.executable = find_opencode_executable()
        if not self.working_dir:
            base = Path(tempfile.gettempdir()) / "fla10-redacao-opencode"
            base.mkdir(parents=True, exist_ok=True)
            self.working_dir = str(base)

    def supports_function_calling(self) -> bool:
        """Usa o laço ReAct em texto, sem function calling nativo."""
        return False

    def supports_stop_words(self) -> bool:
        return True

    def get_input_tokens_count(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_model: Any | None = None,
    ) -> int:
        """Estimativa local, sem o aviso de contagem aproximada do CrewAI."""
        del tools, response_model
        return (len(render_messages(messages)) + 3) // 4

    def call(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        del tools, callbacks, available_functions, from_task, from_agent

        prompt = render_messages(messages)
        if response_model is not None:
            schema = json.dumps(
                response_model.model_json_schema(), ensure_ascii=False, indent=2
            )
            prompt += (
                "\n\n# Formato obrigatório\n\n"
                "Responda apenas com um objeto JSON válido, sem comentários, "
                "que siga exatamente este schema:\n\n"
                f"{schema}"
            )

        prompt = (
            "# Instruções de sistema\n\n"
            f"{PLAIN_AGENT_PROMPT.strip()}\n\n"
            "# Tarefa\n\n"
            f"{prompt}"
        )

        command = " ".join(
            shlex.quote(part)
            for part in (
                str(self.executable),
                "run",
                "--model",
                self.model,
                "--format",
                "json",
                "--archived",
                "--auto",
            )
        )
        command = f"cd {shlex.quote(str(self.working_dir))} && exec {command}"

        try:
            completed = subprocess.run(
                command,
                shell=True,
                executable="/bin/sh",
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OpenCodeError(
                "Runtime do OpenCode não encontrado. Configure "
                "FLA10_OPENCODE_BIN com o caminho do executável."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OpenCodeError(
                f"O modelo {self.model} excedeu o limite de "
                f"{self.timeout:.0f} segundos."
            ) from exc
        except OSError as exc:
            raise OpenCodeError(
                "Não foi possível executar o runtime local do OpenCode."
            ) from exc

        if completed.returncode != 0:
            try:
                parse_opencode_events(completed.stdout, model=self.model)
            except OpenCodeError as exc:
                raise exc from None
            detail = (completed.stderr or "").strip().splitlines()
            suffix = f" Detalhe: {detail[-1]}" if detail else ""
            raise OpenCodeError(
                f"O runtime do OpenCode terminou com código "
                f"{completed.returncode} para {self.model}.{suffix}"
            )

        text, finish_reason, usage = parse_opencode_events(
            completed.stdout, model=self.model
        )
        if finish_reason == "length":
            raise OpenCodeError(
                f"O modelo {self.model} interrompeu a resposta por limite de tokens."
            )

        if usage:
            self._track_token_usage_internal(usage)

        return self._apply_stop_words(text)

    async def acall(self, *args: Any, **kwargs: Any) -> str:
        import asyncio

        return await asyncio.to_thread(self.call, *args, **kwargs)
