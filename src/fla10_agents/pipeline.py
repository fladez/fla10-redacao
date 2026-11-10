"""Orquestração da fase 1: agenda, monitoramento, pautas e dossiês."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fla10_agents.calendar import CalendarRepository
from fla10_agents.editorial.pautas import parse_pauta_documents
from fla10_agents.editorial.proposals import (
    DEFAULT_EVENT_DAYS,
    DEFAULT_SIGNAL_DAYS,
    build_proposals,
)
from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.editorial.vault import LocalVaultReader
from fla10_agents.models import ClaimEvidence
from fla10_agents.research import build_dossier


def run_pauta_pipeline(
    calendar_database: str | Path,
    editorial_database: str | Path,
    *,
    vault_root: Path | None = None,
    event_days: int = DEFAULT_EVENT_DAYS,
    signal_days: int = DEFAULT_SIGNAL_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Gera propostas a partir da agenda e dos sinais, sem decidir publicação."""
    reference = now or datetime.now(UTC)
    reader = LocalVaultReader(vault_root)
    vault = reader.read_pautas()
    pautas = parse_pauta_documents(vault.files)

    with CalendarRepository(calendar_database) as calendar, \
            EditorialRepository(editorial_database) as store:
        run_id = store.start_run("pautas")

        try:
            events = calendar.list_events()
            signals = store.list_signals(limit=200)
            published = store.list_published_titles()

            proposals = build_proposals(
                events,
                signals,
                pautas,
                published,
                now=reference,
                event_days=event_days,
                signal_days=signal_days,
            )

            created = 0
            skipped = 0
            created_ids: list[str] = []

            with store.transaction():
                for proposal in proposals:
                    saved = store.save_proposal(proposal)
                    if saved.created:
                        created += 1
                        created_ids.append(proposal.proposal_id)
                    else:
                        skipped += 1
        except Exception as exc:
            store.finish_run(run_id, "failed", error=type(exc).__name__)
            raise

        store.finish_run(run_id, "completed", created=created, skipped=skipped)

    return {
        "run_id": run_id,
        "status": "completed",
        "vault_root": str(vault.root),
        "vault_commit": vault.commit,
        "pautas": len(pautas),
        "events": len(events),
        "signals": len(signals),
        "created": created,
        "skipped": skipped,
        "created_ids": created_ids,
    }


def build_and_save_dossier(
    editorial_database: str | Path,
    proposal_id: str,
    *,
    claims: list[ClaimEvidence] | None = None,
    contradictions: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Monta o dossiê de uma pauta e registra o resultado."""
    with EditorialRepository(editorial_database) as store:
        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Pauta não encontrada: {proposal_id}")

        if proposal.editorial_decision != "approved":
            raise ValueError(
                "A pauta precisa estar aprovada antes da apuração. "
                f"Estado atual: {proposal.editorial_decision}."
            )

        dossier = build_dossier(
            proposal,
            claims or [],
            contradictions or [],
            researched_at=now,
        )
        store.save_dossier(dossier)

    return {
        "proposal_id": dossier.proposal_id,
        "recommendation": dossier.recommendation,
        "usable_facts": len(dossier.usable_facts),
        "gaps": len(dossier.gaps),
        "attribution_required": len(dossier.attribution_required),
        "excluded_claims": len(dossier.excluded_claims),
    }
