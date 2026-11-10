
"""Execução controlada do teste comparativo de modelos via OpenRouter."""

import hashlib
import json
import os
import secrets
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from fla10_agents.config import OpenRouterSettings

MODEL_CANDIDATES = {
    "GPT-6 Sol": "openai/gpt-6-sol",
    "GPT-6.1 Terra": "openai/gpt-6.1-terra",
    "GPT-6 Luna": "openai/gpt-6-luna",
    "GPT-6 Luna Pro": "openai/gpt-6-luna-pro",
}

MAX_OUTPUT_TOKENS = 7000
TEMPERATURE = 0.2
TOP_P = 1.0

MATERIAL_SCHEMA_VERSION = 1

MATERIAL_FILES = {
    "prompt": "material/prompt.md",
    "dossier": "material/dossier.md",
}


class ModelEvaluationError(RuntimeError):
    """Falha segura durante a execução de uma avaliação."""


def _write_text_atomic(path: Path, content: str) -> None:
    """Grava um arquivo por substituição atômica no mesmo diretório."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _write_json_atomic(path: Path, data: Any) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    _write_text_atomic(path, content)


def _read_test_material(project_root: Path) -> tuple[str, str]:
    docs = project_root / "docs"
    prompt_path = docs / "12-prompt-comum-teste-reportagem.md"
    dossier_path = docs / "13-caso-teste-a-forca-da-nacao.md"

    missing = [str(path) for path in (prompt_path, dossier_path) if not path.is_file()]
    if missing:
        raise ModelEvaluationError(
            "Arquivos do teste não encontrados: " + ", ".join(missing)
        )

    return (
        prompt_path.read_text(encoding="utf-8"),
        dossier_path.read_text(encoding="utf-8"),
    )


def _save_input_material(
    output_dir: Path,
    prompt: str,
    dossier: str,
) -> dict[str, Any]:
    """Preserva os documentos da execução e registra seus hashes SHA-256."""
    material_dir = output_dir / "material"
    material_dir.mkdir(parents=True, exist_ok=False)

    contents = {
        "prompt": prompt,
        "dossier": dossier,
    }
    files: dict[str, Any] = {}

    for key, relative_path in MATERIAL_FILES.items():
        content = contents[key]
        encoded = content.encode("utf-8")

        _write_text_atomic(output_dir / relative_path, content)

        files[key] = {
            "file": relative_path,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "size_bytes": len(encoded),
        }

    manifest = {
        "schema_version": MATERIAL_SCHEMA_VERSION,
        "files": files,
    }

    _write_json_atomic(output_dir / "material.json", manifest)
    return manifest


def _load_input_material(
    output_dir: Path,
) -> tuple[str, str, dict[str, Any]]:
    """Carrega e verifica os documentos originais de uma execução."""
    manifest_path = output_dir / "material.json"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ModelEvaluationError(
            "Manifesto do material ausente ou inválido; retomada bloqueada."
        ) from exc

    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != MATERIAL_SCHEMA_VERSION
        or not isinstance(manifest.get("files"), dict)
        or set(manifest["files"]) != set(MATERIAL_FILES)
    ):
        raise ModelEvaluationError(
            "Estrutura do manifesto inválida ou incompatível; retomada bloqueada."
        )

    contents: dict[str, str] = {}

    for key, relative_path in MATERIAL_FILES.items():
        entry = manifest["files"][key]

        if (
            not isinstance(entry, dict)
            or entry.get("file") != relative_path
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in entry["sha256"])
            or type(entry.get("size_bytes")) is not int
            or entry["size_bytes"] < 0
        ):
            raise ModelEvaluationError(
                f"Registro de integridade inválido ({key}); retomada bloqueada."
            )

        try:
            raw = (output_dir / relative_path).read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ModelEvaluationError(
                f"Snapshot ausente ou ilegível ({key}); retomada bloqueada."
            ) from exc

        actual_hash = hashlib.sha256(raw).hexdigest()

        if (
            actual_hash != entry["sha256"]
            or len(raw) != entry["size_bytes"]
        ):
            raise ModelEvaluationError(
                f"Integridade do snapshot comprometida ({key}); retomada bloqueada."
            )

        contents[key] = content

    return contents["prompt"], contents["dossier"], manifest


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
            "X-Title": "Fla10-Agents - editorial evaluation",
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
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
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
        choice = payload["choices"][0]
        text = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelEvaluationError(
            f"Resposta inesperada do modelo {model_id}; resultado não foi salvo."
        ) from exc

    if not isinstance(text, str) or not text.strip():
        raise ModelEvaluationError(
            f"O modelo {model_id} retornou conteúdo vazio."
        )

    if finish_reason != "stop":
        raise ModelEvaluationError(
            f"O modelo {model_id} não concluiu normalmente "
            f"(finish_reason: {finish_reason!r}). Resultado não será aceito."
        )

    return {
        "text": text,
        "response": payload,
        "elapsed_seconds": elapsed_seconds,
        "finish_reason": finish_reason,
    }


def run_report_test(
    project_root: Path | None = None,
    resume_run_id: str | None = None,
) -> Path:
    """Executa ou retoma os quatro modelos sem repetir resultados concluídos."""
    root = project_root or Path.cwd()
    output_root = root / "artifacts" / "model-evaluation"

    model_items = list(MODEL_CANDIDATES.items())
    labels = [f"Texto-{label}" for label in ("X", "Y", "Z", "W")]
    model_ids = set(MODEL_CANDIDATES.values())

    if resume_run_id is None:
        prompt, dossier = _read_test_material(root)

        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = output_root / run_id
        output_dir.mkdir(parents=True, exist_ok=False)

        input_manifest = _save_input_material(
            output_dir,
            prompt,
            dossier,
        )

        secrets.SystemRandom().shuffle(model_items)

        blind_map = {
            labels[i]: model_name
            for i, (model_name, _) in enumerate(model_items)
        }

        metadata: list[dict[str, Any]] = []

        _write_json_atomic(
            output_dir / "chave-cegamento.json",
            blind_map,
        )

    else:
        try:
            datetime.strptime(resume_run_id, "%Y%m%dT%H%M%SZ")
        except ValueError as exc:
            raise ModelEvaluationError(
                "Identificador de execução inválido."
            ) from exc

        run_id = resume_run_id
        output_dir = output_root / run_id

        if not output_dir.is_dir():
            raise ModelEvaluationError(
                "Pasta da execução não encontrada."
            )

        prompt, dossier, input_manifest = _load_input_material(output_dir)

        required_files = (
            "status.json",
            "metadata.json",
            "chave-cegamento.json",
        )

        if any(not (output_dir / name).is_file() for name in required_files):
            raise ModelEvaluationError(
                "Execução sem arquivos de controle completos; retomada bloqueada."
            )

        try:
            status_data = json.loads(
                (output_dir / "status.json").read_text(encoding="utf-8")
            )
            blind_map = json.loads(
                (output_dir / "chave-cegamento.json").read_text(encoding="utf-8")
            )
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
        except (ValueError, OSError, UnicodeError) as exc:
            raise ModelEvaluationError(
                "Arquivos de controle inválidos; retomada bloqueada."
            ) from exc

        if (
            not isinstance(status_data, dict)
            or status_data.get("run_id") != run_id
        ):
            raise ModelEvaluationError(
                "Identificação da execução inconsistente; retomada bloqueada."
            )

        if status_data.get("input_material") != input_manifest:
            raise ModelEvaluationError(
                "Manifesto de integridade divergente do status da execução; "
                "retomada bloqueada."
            )

        if status_data.get("status") not in ("failed", "running"):
            raise ModelEvaluationError(
                "Somente execuções interrompidas ou com falha podem ser retomadas."
            )

        if not isinstance(blind_map, dict):
            raise ModelEvaluationError(
                "Chave de cegamento inválida; retomada bloqueada."
            )

        if (
            not all(isinstance(label, str) for label in blind_map)
            or not all(isinstance(name, str) for name in blind_map.values())
            or set(blind_map) != set(labels)
            or set(blind_map.values()) != set(MODEL_CANDIDATES)
            or not isinstance(metadata, list)
        ):
            raise ModelEvaluationError(
                "Chave de cegamento ou metadados inconsistentes; retomada bloqueada."
            )

        completed_ids: set[str] = set()

        for item in metadata:
            if not isinstance(item, dict) or not isinstance(item.get("model"), str):
                raise ModelEvaluationError(
                    "Metadados contêm registros inválidos; retomada bloqueada."
                )

            model_id = item["model"]

            if model_id not in model_ids or model_id in completed_ids:
                raise ModelEvaluationError(
                    "Metadados contêm modelos inválidos ou duplicados."
                )

            completed_ids.add(model_id)

            model_name = next(
                name
                for name, candidate_id in MODEL_CANDIDATES.items()
                if candidate_id == model_id
            )

            label = next(
                label
                for label, name in blind_map.items()
                if name == model_name
            )

            result_path = output_dir / f"{label}.md"

            try:
                saved_text = result_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ModelEvaluationError(
                    f"Resultado ilegível ({label}); retomada bloqueada."
                ) from exc

            if not saved_text.strip():
                raise ModelEvaluationError(
                    f"Resultado vazio ({label}); retomada bloqueada."
                )

        for label, model_name in blind_map.items():
            model_id = MODEL_CANDIDATES[model_name]
            text_exists = (output_dir / f"{label}.md").exists()

            if model_id not in completed_ids and text_exists:
                raise ModelEvaluationError(
                    f"{label} existe sem metadados de conclusão. "
                    "Retomada automática bloqueada para evitar cobrança duplicada."
                )

        model_items = [
            (blind_map[label], MODEL_CANDIDATES[blind_map[label]])
            for label in labels
        ]

    settings = OpenRouterSettings.from_env()

    def save_metadata() -> None:
        ordered_metadata = sorted(
            metadata,
            key=lambda item: item["model"],
        )
        _write_json_atomic(
            output_dir / "metadata.json",
            ordered_metadata,
        )

    def save_status(
        status: str,
        error_type: str | None = None,
    ) -> None:
        data = {
            "status": status,
            "run_id": run_id,
            "completed_models": len(metadata),
            "total_models": len(model_items),
            "input_material": input_manifest,
        }

        if error_type is not None:
            data["error_type"] = error_type

        _write_json_atomic(
            output_dir / "status.json",
            data,
        )

    completed_ids = {
        item["model"]
        for item in metadata
    }

    save_metadata()
    save_status("running")

    timeout = httpx.Timeout(300.0, connect=30.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            for label, (model_name, model_id) in zip(labels, model_items):
                if model_id in completed_ids:
                    continue

                result = _request_model(
                    client,
                    settings,
                    model_id,
                    prompt,
                    dossier,
                )

                _write_text_atomic(
                    output_dir / f"{label}.md",
                    result["text"],
                )

                usage = result["response"].get("usage") or {}
                completion_details = (
                    usage.get("completion_tokens_details") or {}
                )

                metadata.append(
                    {
                        "model": model_id,
                        "served_model": result["response"].get("model"),
                        "provider": result["response"].get("provider"),
                        "usage": usage,
                        "reported_cost_usd": usage.get("cost"),
                        "reasoning_tokens": completion_details.get(
                            "reasoning_tokens"
                        ),
                        "elapsed_seconds": result["elapsed_seconds"],
                        "generation": {
                            "temperature": TEMPERATURE,
                            "top_p": TOP_P,
                            "max_completion_tokens": MAX_OUTPUT_TOKENS,
                            "fallbacks_allowed": False,
                        },
                    }
                )

                completed_ids.add(model_id)

                save_metadata()
                save_status("running")

    except Exception as exc:
        save_metadata()
        save_status("failed", type(exc).__name__)
        raise

    save_status("completed")
    return output_dir
