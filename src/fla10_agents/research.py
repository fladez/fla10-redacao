"""Montagem e validação de dossiês de apuração."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from fla10_agents.models import (
    ClaimClassification,
    ClaimEvidence,
    EditorialProposal,
    EvidenceSource,
    ResearchDossier,
)


class ResearchInputError(ValueError):
    """Afirmação ou evidência de apuração inválida."""


def claims_from_payload(payload: Any) -> list[ClaimEvidence]:
    """Valida uma lista de afirmações com evidências."""
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        items = payload["claims"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ResearchInputError(
            "O arquivo deve conter uma lista de afirmações ou o campo 'claims'."
        )

    claims: list[ClaimEvidence] = []

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ResearchInputError(f"Afirmação {index}: esperado um objeto JSON.")

        try:
            claims.append(ClaimEvidence.model_validate(item))
        except ValueError as exc:
            raise ResearchInputError(f"Afirmação {index}: {exc}") from exc

    return claims


def _claim_from_fact(
    fact: str,
    sources: list[EvidenceSource],
) -> ClaimEvidence:
    evidence = [source.model_copy(deep=True) for source in sources]

    return ClaimEvidence(
        claim_id="fato-" + hashlib.sha1(fact.encode("utf-8")).hexdigest()[:12],
        claim_text=fact,
        classification=ClaimClassification.CONFIRMED,
        evidence=evidence,
        independent_corroboration="unknown",
    )


def build_dossier(
    proposal: EditorialProposal,
    claims: Iterable[ClaimEvidence] = (),
    contradictions: Iterable[str] = (),
    *,
    researched_at: datetime | None = None,
) -> ResearchDossier:
    """Organiza fatos e evidências em um dossiê com lacunas explícitas.

    Afirmação confirmada sem evidência é lacuna crítica: o dossiê não pode
    recomendar redação nesse caso.
    """
    now = researched_at or datetime.now(UTC)
    contradiction_list = list(contradictions)
    collected = [
        _claim_from_fact(fact, proposal.initial_sources)
        for fact in proposal.confirmed_facts
    ]
    collected.extend(claims)

    usable_facts: list[str] = []
    attribution_required: list[str] = []
    admissible_analysis: list[str] = []
    excluded_claims: list[str] = []
    critical_gaps: list[str] = []

    for claim in collected:
        if claim.classification == ClaimClassification.CONFIRMED:
            if not claim.evidence:
                critical_gaps.append(
                    f"Afirmação confirmada sem evidência: {claim.claim_text}"
                )
                continue
            usable_facts.append(claim.claim_text)
            continue

        if claim.classification == ClaimClassification.ATTRIBUTED:
            named = [
                item for item in claim.evidence
                if item.author_or_institution
            ]
            if not named:
                critical_gaps.append(
                    f"Atribuição sem autor identificado: {claim.claim_text}"
                )
            attribution_required.append(claim.claim_text)
            continue

        if claim.classification == ClaimClassification.ANALYSIS:
            admissible_analysis.append(claim.claim_text)
            continue

        if claim.classification in (
            ClaimClassification.HYPOTHESIS,
            ClaimClassification.UNCONFIRMED,
        ):
            excluded_claims.append(claim.claim_text)

    gap_list = [*critical_gaps, *proposal.questions_to_verify]

    if not usable_facts and not gap_list:
        gap_list.append("Nenhum fato confirmado com evidência disponível.")

    if critical_gaps or not usable_facts:
        recommendation = "apuração insuficiente"
    elif contradiction_list:
        recommendation = "revisar contradições"
    else:
        recommendation = "pronto para redação"

    return ResearchDossier(
        proposal_id=proposal.proposal_id,
        editorial_question=proposal.editorial_question,
        researched_at=now,
        claims=collected,
        contradictions=contradiction_list,
        gaps=gap_list,
        usable_facts=usable_facts,
        attribution_required=attribution_required,
        admissible_analysis=admissible_analysis,
        excluded_claims=excluded_claims,
        recommendation=recommendation,
    )
