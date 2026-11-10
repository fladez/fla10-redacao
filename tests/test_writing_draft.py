import json

import pytest

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.writing.draft import (
    WritingError,
    generate_draft,
    parse_json_object,
    render_site_html,
)
from tests.support import (
    NOW,
    FakeProvider,
    make_dossier,
    make_proposal,
    make_writing_vault,
    write_state,
    writing_payload,
)


def test_parse_json_object_accepts_code_fence() -> None:
    payload = parse_json_object("```json\n{\"title\": \"x\"}\n```")
    assert payload == {"title": "x"}


def test_parse_json_object_rejects_invalid_text() -> None:
    with pytest.raises(WritingError):
        parse_json_object("sem json")


def test_render_site_html_uses_site_markers() -> None:
    html = render_site_html(
        "Primeiro parágrafo com **destaque**.\n\n## Subtítulo\n\nSegundo parágrafo."
    )

    assert "<h3>Subtítulo</h3>" in html
    assert "<strong>destaque</strong>" in html
    assert html.count("<br><br>") == 2
    assert "<p>" not in html


def test_render_site_html_escapes_html() -> None:
    html = render_site_html("<script>alert('x')</script>")
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_generate_draft_persists_result_and_sources(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(database, proposal=make_proposal(), dossier=make_dossier())
    provider = FakeProvider(json.dumps(writing_payload(), ensure_ascii=False))

    draft = generate_draft(
        database,
        "p1",
        provider,
        model="fake/model",
        vault_root=vault,
        now=NOW,
    )

    assert draft.title.startswith("Flamengo x Palmeiras")
    assert draft.body_html.startswith("O Flamengo enfrenta")
    assert draft.sources[0].author_or_institution == "CBF"
    assert draft.prompt_sha256 is not None
    assert provider.calls[0]["model"] == "fake/model"

    with EditorialRepository(database) as store:
        stored = store.get_draft(draft.draft_id)

    assert stored is not None
    assert stored.editorial_decision == "awaiting_human"


def test_generate_draft_requires_approved_proposal(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(
        database,
        proposal=make_proposal(decision="awaiting_human"),
        dossier=make_dossier(),
    )

    with pytest.raises(WritingError, match="aprovada"):
        generate_draft(
            database,
            "p1",
            FakeProvider(json.dumps(writing_payload())),
            model="fake/model",
            vault_root=vault,
            now=NOW,
        )


def test_generate_draft_requires_sufficient_dossier(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(recommendation="apuração insuficiente"),
    )

    with pytest.raises(WritingError, match="dossiê"):
        generate_draft(
            database,
            "p1",
            FakeProvider(json.dumps(writing_payload())),
            model="fake/model",
            vault_root=vault,
            now=NOW,
        )


def test_generate_draft_rejects_invalid_output(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(database, proposal=make_proposal(), dossier=make_dossier())

    with pytest.raises(WritingError):
        generate_draft(
            database,
            "p1",
            FakeProvider(json.dumps({"title": "curto"})),
            model="fake/model",
            vault_root=vault,
            now=NOW,
        )
