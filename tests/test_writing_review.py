import json

import pytest

from fla10_agents.writing.review import (
    BLOCKED_VERDICT,
    READY_VERDICT,
    ReviewError,
    decide_draft,
    deterministic_issues,
    review_draft,
)
from tests.support import (
    NOW,
    FakeProvider,
    make_dossier,
    make_draft,
    make_proposal,
    make_writing_vault,
    write_state,
)


def test_deterministic_review_accepts_complete_draft() -> None:
    issues, checks = deterministic_issues(make_draft())

    assert issues == []
    assert "checklist de Onde Assistir" in checks


def test_deterministic_review_flags_missing_service_data() -> None:
    draft = make_draft(
        body_markdown="Texto curto sem serviço.",
        ai_summary="",
        body_html="Texto curto sem serviço.",
    )

    issues, _ = deterministic_issues(draft)
    descriptions = " ".join(issue.description for issue in issues)

    assert "Corpo curto" in descriptions
    assert "Resumo para IA ausente" in descriptions
    assert "Horário do jogo" in descriptions


def test_review_draft_persists_ready_verdict(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )

    report = review_draft(
        database,
        "draft-1",
        None,
        model="deterministico",
        vault_root=make_writing_vault(tmp_path),
        now=NOW,
    )

    assert report.verdict == READY_VERDICT
    assert report.reviewer_model == "deterministico"
    assert report.issues == []


def test_review_draft_combines_llm_critical_issue(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )
    provider = FakeProvider(json.dumps({
        "issues": [{
            "severity": "critico",
            "category": "factualidade",
            "description": "O texto afirma público presente sem fonte.",
            "evidence": "Público presente",
        }],
        "summary": "Há afirmação sem suporte.",
    }))

    report = review_draft(
        database,
        "draft-1",
        provider,
        model="fake/reviewer",
        vault_root=make_writing_vault(tmp_path),
        now=NOW,
    )

    assert report.verdict == BLOCKED_VERDICT
    assert report.issues[-1].severity == "critico"
    assert report.summary == "Há afirmação sem suporte."


def test_approval_requires_review(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )

    with pytest.raises(ReviewError, match="Revise"):
        decide_draft(database, "draft-1", "approved")


def test_approval_blocks_critical_review(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )
    review_draft(
        database,
        "draft-1",
        FakeProvider(json.dumps({
            "issues": [{
                "severity": "critico",
                "category": "factualidade",
                "description": "Fato sem suporte.",
            }],
            "summary": "",
        })),
        model="fake/reviewer",
        vault_root=make_writing_vault(tmp_path),
        now=NOW,
    )

    with pytest.raises(ReviewError, match="bloqueado"):
        decide_draft(database, "draft-1", "approved")


def test_approval_after_clean_review(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )
    review_draft(
        database,
        "draft-1",
        None,
        model="deterministico",
        vault_root=make_writing_vault(tmp_path),
        now=NOW,
    )

    draft = decide_draft(database, "draft-1", "approved")

    assert draft.editorial_decision == "approved"
