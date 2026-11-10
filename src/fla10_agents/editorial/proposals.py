"""Geração determinística de propostas de pauta a partir da agenda e de sinais."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from fla10_agents.editorial.pautas import Pauta
from fla10_agents.editorial.redundancy import (
    MEDIUM_RISK,
    RedundancyReport,
    check_redundancy,
)
from fla10_agents.models import (
    EditorialProposal,
    EvidenceSource,
    MonitoringSignal,
    SportsEvent,
)

DEFAULT_EVENT_DAYS = 7
DEFAULT_SIGNAL_DAYS = 3


def _is_flamengo(name: str) -> bool:
    return "flamengo" in name.casefold()


def _dedupe_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _apply_redundancy(
    proposal: EditorialProposal,
    report: RedundancyReport,
) -> EditorialProposal:
    relevant = [match for match in report.matches if match.score >= MEDIUM_RISK]
    related_published = [
        match.title for match in relevant if match.source == "matéria publicada"
    ]
    related_reserved = [
        match.title for match in relevant if match.source != "matéria publicada"
    ]

    return proposal.model_copy(
        update={
            "redundancy_risk": report.risk,
            "related_published": related_published,
            "related_reserved": related_reserved,
        }
    )


def proposals_from_events(
    events: Iterable[SportsEvent],
    pautas: Iterable[Pauta] = (),
    published: Iterable[str] = (),
    *,
    now: datetime | None = None,
    days: int = DEFAULT_EVENT_DAYS,
) -> list[EditorialProposal]:
    """Cria propostas de serviço para jogos do Flamengo na janela indicada."""
    reference = now or datetime.now(UTC)
    limit = reference.date() + timedelta(days=days)
    proposals: list[EditorialProposal] = []

    for event in events:
        if event.starts_at_local is None:
            continue

        match_date = event.starts_at_local.date()
        if match_date < reference.date() or match_date > limit:
            continue

        if not (_is_flamengo(event.home_team) or _is_flamengo(event.away_team)):
            continue

        opponent = event.away_team if _is_flamengo(event.home_team) else event.home_team
        title = f"Flamengo x {opponent}: onde assistir, horário e o que esperar"
        if not _is_flamengo(event.home_team):
            title = f"{opponent} x Flamengo: onde assistir, horário e o que esperar"

        angle = (
            "Serviço de jogo com transmissão, horário, estádio e contexto imediato, "
            "sem antecipar escalação não confirmada."
        )
        question = (
            f"Como o torcedor assiste a {event.home_team} x {event.away_team} "
            "e o que muda no time antes da partida?"
        )

        confirmed_facts = [
            f"{event.competition}"
            + (f" — {event.stage}" if event.stage else ""),
            f"Data e hora: {match_date.isoformat()} às {event.starts_at_local:%H:%M}",
        ]
        if event.venue:
            confirmed_facts.append(f"Local: {event.venue}")

        proposal = EditorialProposal(
            proposal_id=_dedupe_key("proposal", "event", event.event_id)[:32],
            title=title,
            event_id=event.event_id,
            format="onde_assistir",
            editorial_question=question,
            angle=angle,
            why_now=f"Partida marcada para {match_date.isoformat()}.",
            confirmed_facts=confirmed_facts,
            questions_to_verify=[
                "Emissora e plataformas de transmissão",
                "Arbitragem escalada",
                "Desfalques e suspensos confirmados",
            ],
            initial_sources=list(event.sources),
            window=match_date.isoformat(),
            dedupe_key=_dedupe_key("onde_assistir", event.event_id),
            priority_recommendation=(
                "alta" if (match_date - reference.date()).days <= 2 else "normal"
            ),
            created_at=reference,
        )

        report = check_redundancy(title, angle, pautas, published)
        proposals.append(_apply_redundancy(proposal, report))

    return proposals


def proposals_from_signals(
    signals: Iterable[MonitoringSignal],
    pautas: Iterable[Pauta] = (),
    published: Iterable[str] = (),
    *,
    now: datetime | None = None,
    days: int = DEFAULT_SIGNAL_DAYS,
) -> list[EditorialProposal]:
    """Transforma sinais novos sobre o Flamengo em propostas de última notícia."""
    reference = now or datetime.now(UTC)
    limit = reference.date() + timedelta(days=1)
    earliest = reference - timedelta(days=days)
    proposals: list[EditorialProposal] = []

    for signal in signals:
        if signal.published_at < earliest or signal.published_at.date() > limit:
            continue

        haystack = " ".join(
            [
                signal.title,
                signal.summary or "",
                *signal.teams,
                *signal.topics,
                *signal.players,
            ]
        )
        if "flamengo" not in haystack.casefold():
            continue

        question = "Qual é o fato novo e o que ele muda para o Flamengo?"
        angle = signal.summary or (
            "Fato novo reportado pelo monitoramento; confirmar em fonte primária "
            "antes de tratar como notícia."
        )

        sources: list[EvidenceSource] = []
        if signal.url is not None:
            sources.append(
                EvidenceSource(
                    url=signal.url,
                    source_type="sinal de monitoramento",
                    accessed_at=reference,
                    supports=["pauta"],
                    limitations="Sinal de monitoramento; exige confirmação em fonte primária.",
                )
            )

        proposal = EditorialProposal(
            proposal_id=_dedupe_key("proposal", "signal", signal.signal_id)[:32],
            title=signal.title,
            format="ultimas_noticias",
            editorial_question=question,
            angle=angle,
            why_now=f"Sinal publicado em {signal.published_at.isoformat()}.",
            confirmed_facts=[],
            questions_to_verify=[
                "Confirmar o fato em fonte primária",
                "Levantar precedente e reação do clube",
            ],
            initial_sources=sources,
            window=signal.published_at.date().isoformat(),
            dedupe_key=_dedupe_key("ultimas_noticias", signal.signal_id),
            priority_recommendation="alta",
            created_at=reference,
        )

        report = check_redundancy(signal.title, angle, pautas, published)
        proposals.append(_apply_redundancy(proposal, report))

    return proposals


def build_proposals(
    events: Iterable[SportsEvent],
    signals: Iterable[MonitoringSignal],
    pautas: Iterable[Pauta] = (),
    published: Iterable[str] = (),
    *,
    now: datetime | None = None,
    event_days: int = DEFAULT_EVENT_DAYS,
    signal_days: int = DEFAULT_SIGNAL_DAYS,
) -> list[EditorialProposal]:
    pauta_list = list(pautas)
    published_list = list(published)

    return [
        *proposals_from_events(
            events,
            pauta_list,
            published_list,
            now=now,
            days=event_days,
        ),
        *proposals_from_signals(
            signals,
            pauta_list,
            published_list,
            now=now,
            days=signal_days,
        ),
    ]
