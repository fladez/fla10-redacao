"""Testes da preparação, exportação e registro de publicação assistida."""

import json
from datetime import datetime

import pytest

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.publication import (
    PublicationError,
    export_package,
    prepare_package,
    register_publication,
    slugify,
)
from fla10_agents.writing.review import decide_draft, review_draft
from tests.support import (
    NOW,
    make_dossier,
    make_draft,
    make_proposal,
    make_writing_vault,
    write_state,
)


def approved_draft(tmp_path, **draft_overrides):
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(**draft_overrides),
    )
    review_draft(
        database,
        "draft-1",
        None,
        model="deterministico",
        vault_root=make_writing_vault(tmp_path),
        now=NOW,
    )
    decide_draft(database, "draft-1", "approved")
    return database


def test_slugify_removes_accents_and_punctuation() -> None:
    assert slugify("Flamengo x Palmeiras: onde assistir?") == (
        "flamengo-x-palmeiras-onde-assistir"
    )
    assert slugify("!!!") == "materia"
    assert slugify("a" * 100, max_length=10) == "a" * 10


def test_slugify_corta_em_palavra_inteira() -> None:
    slug = slugify("CBF confirma final da Copa do Brasil Feminina no Luso-Brasileiro")

    assert len(slug) <= 80
    assert not slug.endswith("luso-brasile")


def test_prepare_requires_approved_draft(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(),
    )

    with pytest.raises(PublicationError, match="aprovação humana"):
        prepare_package(database, "draft-1", now=NOW)


def test_prepare_requires_review(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(editorial_decision="approved"),
    )

    with pytest.raises(PublicationError, match="revisão"):
        prepare_package(database, "draft-1", now=NOW)


def test_prepare_blocks_rejected_by_review(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    write_state(
        database,
        proposal=make_proposal(),
        dossier=make_dossier(),
        draft=make_draft(editorial_decision="approved"),
    )

    from fla10_agents.models import ReviewReport

    with EditorialRepository(database) as store:
        store.save_review(
            ReviewReport(
                draft_id="draft-1",
                verdict="bloqueado",
                issues=[],
                reviewer_model="teste",
                reviewed_at=NOW,
            )
        )

    with pytest.raises(PublicationError, match="bloqueado"):
        prepare_package(database, "draft-1", now=NOW)


def test_prepare_builds_package_without_publishing(tmp_path) -> None:
    database = approved_draft(tmp_path)

    package = prepare_package(database, "draft-1", now=NOW)

    assert package.status == "prepared"
    assert package.slug == "flamengo-x-palmeiras-onde-assistir-e-o-que-esperar-do-classico"
    assert package.title.startswith("Flamengo x Palmeiras")
    assert package.subtitle.startswith("Partida no Maracanã")
    assert package.body_html.startswith("O Flamengo enfrenta")
    assert package.seo.primary_keyword == "Flamengo x Palmeiras"
    assert package.published_at is None
    assert package.url is None

    with EditorialRepository(database) as store:
        assert store.get_package(package.package_id) is not None
        assert store.list_published_titles() == []


def test_export_writes_local_files_and_updates_status(tmp_path) -> None:
    database = approved_draft(tmp_path)
    package = prepare_package(database, "draft-1", now=NOW)

    destination = export_package(
        database,
        package.package_id,
        tmp_path / "exports",
        now=NOW,
    )

    assert destination == tmp_path / "exports" / package.package_id
    assert (destination / "article.html").read_text(encoding="utf-8") == package.body_html

    markdown = (destination / "article.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Flamengo x Palmeiras")
    assert package.subtitle in markdown
    assert package.body_markdown in markdown

    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["package_id"] == package.package_id
    assert metadata["status"] == "exported"
    assert metadata["seo"]["primary_keyword"] == "Flamengo x Palmeiras"

    stored = json.loads((destination / "package.json").read_text(encoding="utf-8"))
    assert stored["exported_at"] is not None

    with EditorialRepository(database) as store:
        updated = store.get_package(package.package_id)

    assert updated is not None
    assert updated.status == "exported"
    assert updated.exported_at is not None


def test_export_blocks_published_package(tmp_path) -> None:
    database = approved_draft(tmp_path)
    package = prepare_package(database, "draft-1", now=NOW)

    register_publication(
        database,
        package.package_id,
        url="https://fla10.news/materia",
        published_at=NOW,
        confirmation="Confirmado no painel do site.",
    )

    with pytest.raises(PublicationError, match="publicado"):
        export_package(database, package.package_id, tmp_path / "exports")


def test_export_requires_existing_package(tmp_path) -> None:
    database = approved_draft(tmp_path)

    with pytest.raises(KeyError):
        export_package(database, "inexistente", tmp_path / "exports")


def test_register_requires_timezone() -> None:
    with pytest.raises(PublicationError, match="fuso"):
        register_publication(
            "unused.db",
            "package",
            url="https://fla10.news/materia",
            published_at=datetime(2026, 11, 10, 12, 0),
            confirmation="ok",
        )


def test_register_requires_confirmation(tmp_path) -> None:
    database = approved_draft(tmp_path)
    package = prepare_package(database, "draft-1", now=NOW)

    with pytest.raises(PublicationError, match="confirmação"):
        register_publication(
            database,
            package.package_id,
            url="https://fla10.news/materia",
            published_at=NOW,
            confirmation="   ",
        )


def test_register_requires_valid_url(tmp_path) -> None:
    database = approved_draft(tmp_path)
    package = prepare_package(database, "draft-1", now=NOW)

    with pytest.raises(PublicationError, match="URL"):
        register_publication(
            database,
            package.package_id,
            url="não é url",
            published_at=NOW,
            confirmation="ok",
        )


def test_register_marks_package_and_feeds_redundancy(tmp_path) -> None:
    database = approved_draft(tmp_path)
    package = prepare_package(database, "draft-1", now=NOW)

    updated = register_publication(
        database,
        package.package_id,
        url="https://fla10.news/materia",
        published_at=NOW,
        confirmation="Confirmado no painel do site.",
    )

    assert updated.status == "published"
    assert str(updated.url) == "https://fla10.news/materia"
    assert updated.confirmation == "Confirmado no painel do site."

    with EditorialRepository(database) as store:
        assert store.list_published_titles() == [package.title]
        stored = store.get_package(package.package_id)

    assert stored is not None
    assert stored.status == "published"

    with pytest.raises(PublicationError, match="já registrado"):
        register_publication(
            database,
            package.package_id,
            url="https://fla10.news/materia",
            published_at=NOW,
            confirmation="Repetido.",
        )
