"""Preparação, exportação local e registro de publicações confirmadas."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import HttpUrl

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import DraftArticle, PublicationPackage

PUBLISHED_STATUS = "published"
EXPORTED_STATUS = "exported"
PREPARED_STATUS = "prepared"


class PublicationError(RuntimeError):
    """Falha segura na preparação ou no registro de publicação."""


def _write_text_atomic(path: Path, content: str) -> None:
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


def slugify(title: str, *, max_length: int = 80) -> str:
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")
    return (slug[:max_length].rstrip("-") or "materia")


def _require_approved_draft(store: EditorialRepository, draft_id: str) -> DraftArticle:
    draft = store.get_draft(draft_id)
    if draft is None:
        raise KeyError(f"Texto não encontrado: {draft_id}")

    if draft.editorial_decision != "approved":
        raise PublicationError(
            "O texto precisa de aprovação humana antes da publicação. "
            f"Estado atual: {draft.editorial_decision}."
        )

    review = store.get_latest_review(draft_id)
    if review is None:
        raise PublicationError("O texto não tem revisão registrada.")
    if review.verdict == "bloqueado":
        raise PublicationError("O texto está bloqueado pela revisão.")

    return draft


def prepare_package(
    editorial_database: str | Path,
    draft_id: str,
    *,
    now: datetime | None = None,
) -> PublicationPackage:
    """Monta o pacote de CMS sem publicar ou enviar nada."""
    reference = now or datetime.now(UTC)

    with EditorialRepository(editorial_database) as store:
        draft = _require_approved_draft(store, draft_id)

        package = PublicationPackage(
            draft_id=draft.draft_id,
            format=draft.format,
            title=draft.title,
            subtitle=draft.subtitle,
            slug=slugify(draft.title),
            body_html=draft.body_html,
            body_markdown=draft.body_markdown,
            ai_summary=draft.ai_summary,
            seo=draft.seo,
            social_posts=draft.social_posts,
            sources=draft.sources,
            status=PREPARED_STATUS,
            created_at=reference,
        )
        store.save_package(package)

    return package


def export_package(
    editorial_database: str | Path,
    package_id: str,
    output_root: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Exporta arquivos locais em uma pasta própria do pacote."""
    reference = now or datetime.now(UTC)
    root = Path(output_root).expanduser()

    with EditorialRepository(editorial_database) as store:
        package = store.get_package(package_id)
        if package is None:
            raise KeyError(f"Pacote não encontrado: {package_id}")
        if package.status == PUBLISHED_STATUS:
            raise PublicationError("Pacote já registrado como publicado; exportação bloqueada.")

        destination = root / package.package_id
        destination.mkdir(parents=True, exist_ok=True)

        exported = package.model_copy(update={
            "status": EXPORTED_STATUS,
            "exported_at": reference,
        })

        article_markdown = (
            f"# {exported.title}\n\n"
            f"## {exported.subtitle}\n\n"
            f"{exported.body_markdown}\n"
        )

        _write_text_atomic(destination / "article.html", exported.body_html)
        _write_text_atomic(destination / "article.md", article_markdown)
        _write_text_atomic(
            destination / "package.json",
            json.dumps(
                exported.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
        )
        _write_text_atomic(
            destination / "metadata.json",
            json.dumps(
                {
                    "package_id": exported.package_id,
                    "draft_id": exported.draft_id,
                    "title": exported.title,
                    "slug": exported.slug,
                    "status": exported.status,
                    "exported_at": exported.exported_at.isoformat()
                    if exported.exported_at
                    else None,
                    "seo": exported.seo.model_dump(mode="json"),
                    "social_posts": exported.social_posts,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        store.update_package(exported)

    return destination


def register_publication(
    editorial_database: str | Path,
    package_id: str,
    *,
    url: str,
    published_at: datetime,
    confirmation: str,
) -> PublicationPackage:
    """Registra uma publicação já confirmada; não envia conteúdo ao site."""
    if published_at.utcoffset() is None:
        raise PublicationError("A data de publicação precisa incluir fuso horário.")
    if not confirmation.strip():
        raise PublicationError(
            "Informe uma confirmação verificável antes de registrar a publicação."
        )

    try:
        parsed_url = HttpUrl(url)
    except ValueError as exc:
        raise PublicationError("URL de publicação inválida.") from exc

    with EditorialRepository(editorial_database) as store:
        package = store.get_package(package_id)
        if package is None:
            raise KeyError(f"Pacote não encontrado: {package_id}")
        if package.status == PUBLISHED_STATUS:
            raise PublicationError("Pacote já registrado como publicado.")

        updated = package.model_copy(update={
            "status": PUBLISHED_STATUS,
            "url": parsed_url,
            "published_at": published_at,
            "confirmation": confirmation.strip(),
        })

        with store.transaction():
            store.update_package(updated)
            store.register_publication(
                title=updated.title,
                url=str(parsed_url),
                format=updated.format,
                published_at=published_at,
            )

    return updated


def package_summary(package: PublicationPackage) -> dict[str, Any]:
    return {
        "package_id": package.package_id,
        "draft_id": package.draft_id,
        "title": package.title,
        "slug": package.slug,
        "status": package.status,
        "created_at": package.created_at.isoformat(),
        "exported_at": package.exported_at.isoformat() if package.exported_at else None,
        "published_at": package.published_at.isoformat() if package.published_at else None,
        "url": str(package.url) if package.url else None,
    }
