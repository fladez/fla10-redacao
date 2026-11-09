from pathlib import Path

import pytest

from fla10_agents.config import OpenRouterSettings
from fla10_agents.evaluation import (
    MODEL_CANDIDATES,
    ModelEvaluationError,
    _read_test_material,
)


def test_model_candidates_are_the_three_approved_models() -> None:
    assert set(MODEL_CANDIDATES.values()) == {
        "openai/gpt-5.5",
        "openai/gpt-4o-mini",
        "qwen/qwen-2.5-72b-instruct",
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
    with pytest.raises(ModelEvaluationError, match="Arquivos do teste não encontrados"):
        _read_test_material(tmp_path)


def test_openrouter_settings_require_local_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY não definido"):
        OpenRouterSettings.from_env()


def test_openrouter_settings_read_key_without_changing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-test-key")
    settings = OpenRouterSettings.from_env()

    assert settings.api_key == "local-test-key"
    assert settings.api_url == "https://openrouter.ai/api/v1"
