"""Execução controlada do teste comparativo de modelos via OpenRouter."""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from fla10_agents.config import OpenRouterSettings

MODEL_CANDIDATES = {
    "GPT-5.5": "openai/gpt-5.5",
    "GPT-4o-mini": "openai/gpt-4o-mini",
    "Qwen2.5-72B-Instruct": "qwen/qwen-2.5-72b-instruct",
}

MAX_OUTPUT_TOKENS = 7000
TEMPERATURE = 0.2
TOP_P = 1.0


class ModelEvaluationError(RuntimeError):
    """Falha segura durante a execução de uma avaliação."""


def _read_test_material(project_root: Path) -> tuple[str, str]:
    docs = project_root / "docs"
    prompt_path = docs / "12-prompt-comum-teste-reportagem.md"
    dossier_path = docs / "13-caso-teste-a-forca-da-nacao.md"
    missing = [str(path) for path in (prompt_path, dossier_path) if not path.is_file()]
    if missing:
        raise ModelEvaluationError(
            "Arquivos do teste não encontrados: " + ", ".join(missing)
        )
    return prompt_path.read_text(encoding="utf-8"), dossier_path.read_text(encoding="utf-8")


def _request_model(
    client: httpx.Client,
    settings: OpenRouterSettings,
    model_id: str,
    prompt: str,
    dossier: str,
) -> dict[str, Any]:
    started_at = perf_counter()
    response = client.post(
        f"{settings.api_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fla10.news",
            "X-Title": "Fla10-Agents - avaliação editorial",
        },
        json={
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt}\n\n## Material documental anexado\n\n{dossier}",
                }
            ],
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "provider": {"allow_fallbacks": False},
        },
    )
    elapsed_seconds = round(perf_counter() - started_at, 3)
    if response.is_error:
        raise ModelEvaluationError(
            f"Falha no modelo {model_id}: HTTP {response.status_code}. "
            "Consulte o painel do OpenRouter; a chave não será exibida."
        )
    try:
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelEvaluationError(
            f"Resposta inesperada do modelo {model_id}; resultado não foi salvo."
        ) from exc
    if not isinstance(text, str) or not text.strip():
        raise ModelEvaluationError(f"O modelo {model_id} retornou conteúdo vazio.")
    return {"text": text, "response": payload, "elapsed_seconds": elapsed_seconds}


def run_report_test(project_root: Path | None = None) -> Path:
    """Executa os três modelos e salva saídas cegas e metadados localmente."""
    root = project_root or Path.cwd()
    prompt, dossier = _read_test_material(root)
    settings = OpenRouterSettings.from_env()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = root / "artifacts" / "model-evaluation" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    model_items = list(MODEL_CANDIDATES.items())
    secrets.SystemRandom().shuffle(model_items)
    blind_map: dict[str, str] = {}
    metadata: list[dict[str, Any]] = []

    timeout = httpx.Timeout(300.0, connect=30.0)
    with httpx.Client(timeout=timeout) as client:
        for index, (model_name, model_id) in enumerate(model_items):
            blind_label = f"Texto-{chr(ord('X') + index)}"
            result = _request_model(client, settings, model_id, prompt, dossier)
            (output_dir / f"{blind_label}.md").write_text(
                result["text"], encoding="utf-8"
            )
            usage = result["response"].get("usage", {})
            metadata.append(
                {
                    "blind_label": blind_label,
                    "requested_model": model_id,
                    "served_model": result["response"].get("model"),
                    "provider": result["response"].get("provider"),
                    "usage": usage,
                    "reported_cost_usd": usage.get("cost"),
                    "elapsed_seconds": result["elapsed_seconds"],
                    "generation": {
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "max_tokens": MAX_OUTPUT_TOKENS,
                        "fallbacks_allowed": False,
                    },
                }
            )
            blind_map[blind_label] = model_name

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "chave-cegamento.json").write_text(
        json.dumps(blind_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_dir
