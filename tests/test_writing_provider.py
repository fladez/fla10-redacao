"""Testes do motor gratuito DeepSeek V4 usado na produção e na revisão."""

import json
import subprocess

import pytest

from fla10_agents.writing.provider import (
    OpenCodeProvider,
    ProviderError,
    build_provider,
    default_review_model,
    default_writing_model,
    parse_opencode_events,
)


def test_default_models_use_free_deepseek(monkeypatch) -> None:
    monkeypatch.delenv("FLA10_WRITING_MODEL", raising=False)
    monkeypatch.delenv("FLA10_REVIEW_MODEL", raising=False)
    assert default_writing_model() == "opencode/deepseek-v4.1-flash-free"
    assert default_review_model() == "opencode/deepseek-v4.1-flash-free"

    monkeypatch.setenv("FLA10_WRITING_MODEL", "outro/modelo")
    assert default_review_model() == "outro/modelo"

    monkeypatch.setenv("FLA10_REVIEW_MODEL", "revisor/modelo")
    assert default_review_model() == "revisor/modelo"


def test_build_provider_uses_opencode(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "opencode"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("FLA10_OPENCODE_BIN", str(executable))

    provider = build_provider()

    assert isinstance(provider, OpenCodeProvider)
    assert provider.executable == str(executable)


def test_find_opencode_executable_uses_env(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "opencode"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("FLA10_OPENCODE_BIN", str(executable))

    provider = OpenCodeProvider()

    assert provider.executable == str(executable)


def test_find_opencode_executable_rejects_missing_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLA10_OPENCODE_BIN", str(tmp_path / "ausente"))

    with pytest.raises(ProviderError, match="inexistente"):
        OpenCodeProvider()


def opencode_events(
    text: str = '{"ok": true}',
    *,
    reason: str = "stop",
    cost: float = 0,
) -> str:
    events = [
        {
            "type": "text",
            "part": {"type": "text", "text": text},
        },
        {
            "type": "step_finish",
            "part": {
                "reason": reason,
                "cost": cost,
                "tokens": {
                    "input": 120,
                    "output": 30,
                    "reasoning": 5,
                    "cache": {"read": 10, "write": 0},
                },
            },
        },
    ]
    return "\n".join(json.dumps(event) for event in events)


def make_opencode(
    tmp_path,
    stdout: str,
    *,
    returncode: int = 0,
    calls: list[dict[str, object]] | None = None,
) -> OpenCodeProvider:
    def runner(command, **kwargs):
        if calls is not None:
            calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout,
            stderr="",
        )

    executable = tmp_path / "opencode"
    executable.write_text("", encoding="utf-8")
    return OpenCodeProvider(
        str(executable),
        timeout=12,
        working_dir=tmp_path,
        runner=runner,
    )


def test_opencode_provider_reads_json_events(tmp_path) -> None:
    calls: list[dict[str, object]] = []
    provider = make_opencode(tmp_path, opencode_events(), calls=calls)

    response = provider.complete(
        "Escreva a matéria.",
        model="opencode/deepseek-v4.1-flash-free",
        system="Você é o produtor.",
    )

    assert response.text == '{"ok": true}'
    assert response.served_model == "opencode/deepseek-v4.1-flash-free"
    assert response.usage["prompt_tokens"] == 120
    assert response.usage["completion_tokens"] == 30
    assert response.usage["reasoning_tokens"] == 5
    assert response.usage["cost"] == 0
    assert response.finish_reason == "stop"

    call = calls[0]
    command = call["command"]
    assert command[1:5] == ["run", "--model", "opencode/deepseek-v4.1-flash-free", "--format"]
    assert call["input"].startswith("# Instruções de sistema")
    assert "Você é o produtor." in call["input"]
    assert "Escreva a matéria." in call["input"]
    assert call["cwd"] == str(tmp_path)
    assert call["timeout"] == 12


def test_opencode_provider_rejects_nonzero_exit(tmp_path) -> None:
    provider = make_opencode(tmp_path, "", returncode=2)

    with pytest.raises(ProviderError, match="código 2"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_timeout(tmp_path) -> None:
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 12)

    provider = OpenCodeProvider(
        str(tmp_path / "opencode"),
        runner=runner,
        working_dir=tmp_path,
    )

    with pytest.raises(ProviderError, match="excedeu"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_missing_runtime(tmp_path) -> None:
    def runner(command, **kwargs):
        raise FileNotFoundError(command[0])

    provider = OpenCodeProvider(
        str(tmp_path / "opencode"),
        runner=runner,
        working_dir=tmp_path,
    )

    with pytest.raises(ProviderError, match="FLA10_OPENCODE_BIN"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_error_event(tmp_path) -> None:
    stdout = json.dumps({
        "type": "error",
        "part": {"error": {"message": "modelo indisponível"}},
    })
    provider = make_opencode(tmp_path, stdout)

    with pytest.raises(ProviderError, match="modelo indisponível"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_empty_output(tmp_path) -> None:
    provider = make_opencode(tmp_path, "linha inválida")

    with pytest.raises(ProviderError, match="eventos reconhecíveis"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_empty_text(tmp_path) -> None:
    stdout = "\n".join([
        json.dumps({"type": "text", "part": {"text": "   "}}),
        json.dumps({"type": "step_finish", "part": {"reason": "stop"}}),
    ])
    provider = make_opencode(tmp_path, stdout)

    with pytest.raises(ProviderError, match="vazio"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_missing_finish(tmp_path) -> None:
    stdout = json.dumps({"type": "text", "part": {"text": "ok"}})
    provider = make_opencode(tmp_path, stdout)

    with pytest.raises(ProviderError, match="conclusão"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_opencode_provider_rejects_truncated_generation(tmp_path) -> None:
    provider = make_opencode(tmp_path, opencode_events(reason="length"))

    with pytest.raises(ProviderError, match="finish_reason"):
        provider.complete("texto", model="opencode/deepseek-v4.1-flash-free")


def test_parse_opencode_events_concatenates_text_parts() -> None:
    stdout = "\n".join([
        json.dumps({"type": "text", "part": {"text": "parte 1 "}}),
        json.dumps({"type": "text", "part": {"text": "parte 2"}}),
        json.dumps({
            "type": "step_finish",
            "part": {"reason": "stop", "tokens": {"input": 1, "output": 2}},
        }),
    ])

    text, reason, usage = parse_opencode_events(stdout, model="m")

    assert text == "parte 1 parte 2"
    assert reason == "stop"
    assert usage["total_tokens"] == 3
