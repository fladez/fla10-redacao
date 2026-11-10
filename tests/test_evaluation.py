
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from fla10_agents import evaluation
from fla10_agents.config import OpenRouterSettings
from fla10_agents.evaluation import (
    MATERIAL_FILES,
    MODEL_CANDIDATES,
    ModelEvaluationError,
    _read_test_material,
    _request_model,
    run_report_test,
)


def test_model_candidates_are_the_four_approved_models() -> None:
    assert MODEL_CANDIDATES == {
        "GPT-6 Sol": "openai/gpt-6-sol",
        "GPT-6.1 Terra": "openai/gpt-6.1-terra",
        "GPT-6 Luna": "openai/gpt-6-luna",
        "GPT-6 Luna Pro": "openai/gpt-6-luna-pro",
    }


def test_read_test_material_loads_prompt_and_dossier(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "12-prompt-comum-teste-reportagem.md").write_text(
        "prompt", encoding="utf-8"
    )
    (docs / "13-caso-teste-a-forca-da-nacao.md").write_text(
        "dossier", encoding="utf-8"
    )

    prompt, dossier = _read_test_material(tmp_path)

    assert prompt == "prompt"
    assert dossier == "dossier"


def test_read_test_material_reports_missing_files(tmp_path: Path) -> None:
    with pytest.raises(
        ModelEvaluationError, match="Arquivos do teste não encontrados"
    ):
        _read_test_material(tmp_path)


def test_openrouter_settings_require_local_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("fla10_agents.config.find_dotenv", lambda **kwargs: "")

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY não definido"):
        OpenRouterSettings.from_env()


def test_openrouter_settings_read_key_without_changing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-test-key")

    settings = OpenRouterSettings.from_env()

    assert settings.api_key == "local-test-key"
    assert settings.api_url == "https://openrouter.ai/api/v1"


class FakeClient:
    def __init__(self, finish_reason: str) -> None:
        self.finish_reason = finish_reason
        self.request_body = None

    def post(self, url: str, **kwargs):
        self.request_body = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "Reportagem de teste."},
                        "finish_reason": self.finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "completion_tokens_details": {"reasoning_tokens": 25},
                },
            },
            request=httpx.Request("POST", url),
        )


def test_request_model_accepts_normal_completion() -> None:
    client = FakeClient("stop")
    settings = OpenRouterSettings(api_key="test-key")

    result = _request_model(
        client, settings, "openai/gpt-5.5", "prompt", "dossier"
    )

    assert result["text"] == "Reportagem de teste."
    assert result["finish_reason"] == "stop"
    assert client.request_body["max_completion_tokens"] == 7000
    assert "max_tokens" not in client.request_body


def test_request_model_rejects_truncated_completion() -> None:
    client = FakeClient("length")
    settings = OpenRouterSettings(api_key="test-key")

    with pytest.raises(
        ModelEvaluationError, match="não concluiu normalmente"
    ):
        _request_model(
            client, settings, "openai/gpt-5.5", "prompt", "dossier"
        )


def _prepare_report_test_project(project_root: Path) -> None:
    docs = project_root / "docs"
    docs.mkdir()
    (docs / "12-prompt-comum-teste-reportagem.md").write_text(
        "Prompt de teste", encoding="utf-8"
    )
    (docs / "13-caso-teste-a-forca-da-nacao.md").write_text(
        "Dossiê de teste", encoding="utf-8"
    )


class FakeContextClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _fake_model_result(model_id: str) -> dict:
    return {
        "text": f"Reportagem de teste para {model_id}.",
        "response": {
            "model": model_id,
            "provider": "provedor-teste",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "completion_tokens_details": {"reasoning_tokens": 25},
            },
        },
        "elapsed_seconds": 1.0,
        "finish_reason": "stop",
    }


def _configure_fake_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation.OpenRouterSettings,
        "from_env",
        lambda: OpenRouterSettings(api_key="test-key"),
    )
    monkeypatch.setattr(
        evaluation.httpx,
        "Client",
        lambda timeout: FakeContextClient(),
    )


def test_save_and_load_input_material_records_sha256(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    manifest = evaluation._save_input_material(
        output_dir,
        "Prompt original",
        "Dossiê original",
    )

    prompt_path = output_dir / MATERIAL_FILES["prompt"]
    dossier_path = output_dir / MATERIAL_FILES["dossier"]

    assert prompt_path.read_text(encoding="utf-8") == "Prompt original"
    assert dossier_path.read_text(encoding="utf-8") == "Dossiê original"
    assert manifest["schema_version"] == evaluation.MATERIAL_SCHEMA_VERSION

    assert manifest["files"]["prompt"]["sha256"] == hashlib.sha256(
        b"Prompt original"
    ).hexdigest()
    assert manifest["files"]["dossier"]["sha256"] == hashlib.sha256(
        "Dossiê original".encode()
    ).hexdigest()

    assert manifest["files"]["prompt"]["size_bytes"] == len(
        b"Prompt original"
    )
    assert manifest["files"]["dossier"]["size_bytes"] == len(
        "Dossiê original".encode()
    )

    saved_manifest = json.loads(
        (output_dir / "material.json").read_text(encoding="utf-8")
    )
    assert saved_manifest == manifest

    prompt, dossier, loaded_manifest = evaluation._load_input_material(
        output_dir
    )

    assert prompt == "Prompt original"
    assert dossier == "Dossiê original"
    assert loaded_manifest == manifest


def test_load_input_material_rejects_modified_snapshot(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    evaluation._save_input_material(
        output_dir,
        "Prompt original",
        "Dossiê original",
    )

    (output_dir / MATERIAL_FILES["prompt"]).write_text(
        "Prompt adulterado",
        encoding="utf-8",
    )

    with pytest.raises(
        ModelEvaluationError,
        match="Integridade do snapshot comprometida",
    ):
        evaluation._load_input_material(output_dir)


def test_load_input_material_rejects_missing_manifest(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    with pytest.raises(
        ModelEvaluationError,
        match="Manifesto do material ausente ou inválido",
    ):
        evaluation._load_input_material(output_dir)


def test_load_input_material_rejects_missing_snapshot(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    evaluation._save_input_material(
        output_dir,
        "Prompt original",
        "Dossiê original",
    )

    (output_dir / MATERIAL_FILES["prompt"]).unlink()

    with pytest.raises(
        ModelEvaluationError,
        match="Snapshot ausente ou ilegível",
    ):
        evaluation._load_input_material(output_dir)


def test_run_report_test_saves_complete_blind_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_report_test_project(tmp_path)
    _configure_fake_execution(monkeypatch)

    def fake_request(client, settings, model_id, prompt, dossier):
        status_files = list(
            (tmp_path / "artifacts" / "model-evaluation").glob(
                "*/status.json"
            )
        )
        assert len(status_files) == 1

        current_status = json.loads(
            status_files[0].read_text(encoding="utf-8")
        )
        assert current_status["status"] == "running"

        output_dir = status_files[0].parent
        assert (output_dir / "chave-cegamento.json").is_file()
        assert (output_dir / "material.json").is_file()
        assert (
            output_dir / MATERIAL_FILES["prompt"]
        ).read_text(encoding="utf-8") == "Prompt de teste"
        assert (
            output_dir / MATERIAL_FILES["dossier"]
        ).read_text(encoding="utf-8") == "Dossiê de teste"

        assert current_status["input_material"] == json.loads(
            (output_dir / "material.json").read_text(encoding="utf-8")
        )

        return _fake_model_result(model_id)

    monkeypatch.setattr(evaluation, "_request_model", fake_request)

    output_dir = run_report_test(tmp_path)

    status = json.loads(
        (output_dir / "status.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (output_dir / "metadata.json").read_text(encoding="utf-8")
    )
    blind_map = json.loads(
        (output_dir / "chave-cegamento.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output_dir / "material.json").read_text(encoding="utf-8")
    )

    assert status["status"] == "completed"
    assert status["completed_models"] == 4
    assert status["input_material"] == manifest
    assert len(metadata) == 4
    assert len(blind_map) == 4
    assert [item["model"] for item in metadata] == sorted(
        item["model"] for item in metadata
    )
    assert all("blind_label" not in item for item in metadata)
    assert all("requested_model" not in item for item in metadata)
    assert all(item["reasoning_tokens"] == 25 for item in metadata)

    metadata_text = (output_dir / "metadata.json").read_text(
        encoding="utf-8"
    )
    assert all(
        label not in metadata_text
        for label in ("Texto-X", "Texto-Y", "Texto-Z", "Texto-W")
    )
    assert len(list(output_dir.glob("Texto-*.md"))) == 4


def test_run_report_test_preserves_blind_map_on_partial_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_report_test_project(tmp_path)
    _configure_fake_execution(monkeypatch)

    request_count = 0

    def fake_request(client, settings, model_id, prompt, dossier):
        nonlocal request_count
        request_count += 1

        if request_count == 2:
            raise ModelEvaluationError(
                "Falha simulada no segundo modelo."
            )

        return _fake_model_result(model_id)

    monkeypatch.setattr(evaluation, "_request_model", fake_request)

    with pytest.raises(
        ModelEvaluationError, match="Falha simulada"
    ):
        run_report_test(tmp_path)

    output_root = tmp_path / "artifacts" / "model-evaluation"
    output_dir = next(output_root.iterdir())

    status = json.loads(
        (output_dir / "status.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (output_dir / "metadata.json").read_text(encoding="utf-8")
    )
    blind_map = json.loads(
        (output_dir / "chave-cegamento.json").read_text(encoding="utf-8")
    )

    assert status["status"] == "failed"
    assert status["completed_models"] == 1
    assert status["total_models"] == 4
    assert status["error_type"] == "ModelEvaluationError"
    assert len(metadata) == 1
    assert set(blind_map) == {
        "Texto-X",
        "Texto-Y",
        "Texto-Z",
        "Texto-W",
    }
    assert set(blind_map.values()) == set(MODEL_CANDIDATES)
    assert len(list(output_dir.glob("Texto-*.md"))) == 1
    assert status["input_material"] == json.loads(
        (output_dir / "material.json").read_text(encoding="utf-8")
    )

    # Uma divergência entre status e manifesto deve bloquear a retomada.
    status["input_material"]["files"]["prompt"]["sha256"] = "0" * 64
    (output_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    def unexpected_model_call(*args, **kwargs):
        raise AssertionError(
            "Nenhum modelo deveria ser chamado após divergência."
        )

    monkeypatch.setattr(
        evaluation, "_request_model", unexpected_model_call
    )

    with pytest.raises(
        ModelEvaluationError,
        match="Manifesto de integridade divergente",
    ):
        run_report_test(tmp_path, resume_run_id=output_dir.name)


def test_run_report_test_resume_does_not_repeat_completed_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_report_test_project(tmp_path)
    _configure_fake_execution(monkeypatch)

    first_run_calls = 0

    def fail_second_request(client, settings, model_id, prompt, dossier):
        nonlocal first_run_calls
        first_run_calls += 1

        if first_run_calls == 2:
            raise ModelEvaluationError("Interrupção simulada.")

        return _fake_model_result(model_id)

    monkeypatch.setattr(
        evaluation, "_request_model", fail_second_request
    )

    with pytest.raises(
        ModelEvaluationError, match="Interrupção simulada"
    ):
        run_report_test(tmp_path)

    output_dir = next(
        (tmp_path / "artifacts" / "model-evaluation").iterdir()
    )
    run_id = output_dir.name

    previous_metadata = json.loads(
        (output_dir / "metadata.json").read_text(encoding="utf-8")
    )
    completed_model = previous_metadata[0]["model"]

    # Modificar os documentos de origem não pode alterar uma retomada.
    (tmp_path / "docs" / "12-prompt-comum-teste-reportagem.md").write_text(
        "Prompt modificado depois da execução",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "13-caso-teste-a-forca-da-nacao.md").write_text(
        "Dossiê modificado depois da execução",
        encoding="utf-8",
    )

    resumed_calls = []

    def complete_remaining(client, settings, model_id, prompt, dossier):
        resumed_calls.append(model_id)

        assert prompt == "Prompt de teste"
        assert dossier == "Dossiê de teste"

        return _fake_model_result(model_id)

    monkeypatch.setattr(
        evaluation, "_request_model", complete_remaining
    )

    resumed_dir = run_report_test(
        tmp_path,
        resume_run_id=run_id,
    )

    status = json.loads(
        (resumed_dir / "status.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (resumed_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert resumed_dir == output_dir
    assert status["status"] == "completed"
    assert status["completed_models"] == 4
    assert len(metadata) == 4
    assert len(resumed_calls) == 3
    assert completed_model not in resumed_calls
    assert len(list(output_dir.glob("Texto-*.md"))) == 4


def test_resume_rejects_missing_material_before_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_report_test_project(tmp_path)
    _configure_fake_execution(monkeypatch)

    request_count = 0

    def interrupt_execution(client, settings, model_id, prompt, dossier):
        nonlocal request_count
        request_count += 1

        if request_count == 2:
            raise ModelEvaluationError("Interrupção simulada.")

        return _fake_model_result(model_id)

    monkeypatch.setattr(
        evaluation, "_request_model", interrupt_execution
    )

    with pytest.raises(
        ModelEvaluationError, match="Interrupção simulada"
    ):
        run_report_test(tmp_path)

    output_dir = next(
        (tmp_path / "artifacts" / "model-evaluation").iterdir()
    )
    run_id = output_dir.name

    (output_dir / "material.json").unlink()

    def unexpected_model_call(*args, **kwargs):
        raise AssertionError(
            "A retomada não deveria chamar nenhum modelo."
        )

    monkeypatch.setattr(
        evaluation, "_request_model", unexpected_model_call
    )

    with pytest.raises(
        ModelEvaluationError,
        match="Manifesto do material ausente ou inválido",
    ):
        run_report_test(tmp_path, resume_run_id=run_id)


def test_atomic_write_preserves_original_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "resultado.md"
    target.write_text("Conteúdo original.", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("Falha simulada na substituição.")

    monkeypatch.setattr(evaluation.os, "replace", fail_replace)

    with pytest.raises(OSError, match="Falha simulada"):
        evaluation._write_text_atomic(target, "Novo conteúdo.")

    assert target.read_text(encoding="utf-8") == "Conteúdo original."
    assert list(tmp_path.glob(".resultado.md.*.tmp")) == []


def test_resume_rejects_empty_registered_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_report_test_project(tmp_path)
    _configure_fake_execution(monkeypatch)

    request_count = 0

    def interrupt_after_one_result(
        client, settings, model_id, prompt, dossier
    ):
        nonlocal request_count
        request_count += 1

        if request_count == 2:
            raise ModelEvaluationError("Interrupção simulada.")

        result = _fake_model_result(model_id)
        result["response"]["usage"] = {}
        return result

    monkeypatch.setattr(
        evaluation, "_request_model", interrupt_after_one_result
    )

    with pytest.raises(
        ModelEvaluationError, match="Interrupção simulada"
    ):
        run_report_test(tmp_path)

    output_dir = next(
        (tmp_path / "artifacts" / "model-evaluation").iterdir()
    )
    run_id = output_dir.name

    metadata = json.loads(
        (output_dir / "metadata.json").read_text(encoding="utf-8")
    )
    blind_map = json.loads(
        (output_dir / "chave-cegamento.json").read_text(encoding="utf-8")
    )

    completed_model = metadata[0]["model"]
    completed_name = next(
        name
        for name, model_id in MODEL_CANDIDATES.items()
        if model_id == completed_model
    )
    completed_label = next(
        label
        for label, name in blind_map.items()
        if name == completed_name
    )

    (output_dir / f"{completed_label}.md").write_text(
        "",
        encoding="utf-8",
    )

    def unexpected_model_call(*args, **kwargs):
        raise AssertionError(
            "A retomada não deveria chamar nenhum modelo."
        )

    monkeypatch.setattr(
        evaluation, "_request_model", unexpected_model_call
    )

    with pytest.raises(
        ModelEvaluationError, match="Resultado vazio"
    ):
        run_report_test(tmp_path, resume_run_id=run_id)
