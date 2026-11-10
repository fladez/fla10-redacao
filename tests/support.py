"""Apoio compartilhado dos testes de produção, revisão e publicação."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fla10_agents.models import (
    ClaimClassification,
    ClaimEvidence,
    DraftArticle,
    EditorialProposal,
    EvidenceSource,
    ResearchDossier,
    SeoPackage,
)
from fla10_agents.writing.context import COMMON_DOCUMENTS, format_document
from fla10_agents.writing.draft import render_site_html
from fla10_agents.writing.provider import LLMResponse

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class FakeProvider:
    def __init__(self, text: str, served_model: str = "fake/model") -> None:
        self.text = text
        self.served_model = served_model
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> LLMResponse:
        self.calls.append({
            "prompt": prompt,
            "model": model,
            "system": system,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "json_mode": json_mode,
        })
        return LLMResponse(
            text=self.text,
            model=model,
            served_model=self.served_model,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            elapsed_seconds=0.1,
            finish_reason="stop",
        )


def make_writing_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    paths = {*COMMON_DOCUMENTS, format_document("onde_assistir")}
    for relative in paths:
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n\nRegra editorial de teste.\n", encoding="utf-8")
    return vault


def make_proposal(
    proposal_id: str = "p1",
    *,
    decision: str = "approved",
    format_name: str = "onde_assistir",
) -> EditorialProposal:
    return EditorialProposal(
        proposal_id=proposal_id,
        title="Flamengo x Palmeiras: onde assistir",
        format=format_name,
        editorial_question="Como assistir ao jogo?",
        angle="Serviço de jogo.",
        why_now="Jogo na semana.",
        confirmed_facts=["Jogo no Maracanã", "Data e hora: 2026-11-12 às 21:30"],
        questions_to_verify=[],
        initial_sources=[],
        editorial_decision=decision,
        created_at=NOW,
    )


def make_dossier(proposal_id: str = "p1", recommendation: str = "pronto para redação") -> ResearchDossier:
    source = EvidenceSource(
        url="https://example.com/tabela",
        source_type="tabela oficial",
        author_or_institution="CBF",
        accessed_at=NOW,
        supports=["data"],
        supporting_excerpt_or_data="Tabela detalhada",
    )
    return ResearchDossier(
        proposal_id=proposal_id,
        editorial_question="Como assistir ao jogo?",
        researched_at=NOW,
        claims=[
            ClaimEvidence(
                claim_id="c1",
                claim_text="Jogo no Maracanã",
                classification=ClaimClassification.CONFIRMED,
                evidence=[source],
            ),
            ClaimEvidence(
                claim_id="c2",
                claim_text="Data e hora: 2026-11-12 às 21:30",
                classification=ClaimClassification.CONFIRMED,
                evidence=[source],
            ),
        ],
        gaps=[],
        usable_facts=["Jogo no Maracanã", "Data e hora: 2026-11-12 às 21:30"],
        recommendation=recommendation,
    )


def writing_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Flamengo x Palmeiras: onde assistir e o que esperar do clássico",
        "subtitle": "Partida no Maracanã reúne times em busca de posição na tabela",
        "body_markdown": (
            "O Flamengo enfrenta o Palmeiras nesta quinta-feira, no Maracanã. "
            "O horário do jogo é 21h30, pela 38ª rodada do Brasileirão.\n\n"
            "## Onde assistir\n\n"
            "A transmissão do jogo ainda não foi divulgada pelos detentores dos "
            "direitos. O estádio confirmado é o Maracanã, no Rio de Janeiro.\n\n"
            "## Arbitragem e escalações\n\n"
            "A arbitragem ainda não foi oficialmente divulgada. As escalações "
            "prováveis não foram confirmadas pelos clubes.\n\n"
            "## Contexto\n\n"
            "O confronto vale posição na tabela e exige atenção ao calendário "
            "das duas equipes."
        ),
        "ai_summary": (
            "Flamengo e Palmeiras se enfrentam às 21h30 no Maracanã, pela 38ª "
            "rodada do Brasileirão. Transmissão e arbitragem ainda não foram divulgadas."
        ),
        "seo": {
            "title": "Flamengo x Palmeiras: onde assistir e horário",
            "meta_description": "Saiba horário, local e contexto do clássico no Maracanã.",
            "primary_keyword": "Flamengo x Palmeiras",
            "secondary_keywords": ["onde assistir", "Brasileirão"],
        },
        "social_posts": ["Flamengo e Palmeiras se enfrentam às 21h30 no Maracanã."],
    }
    payload.update(overrides)
    return payload


def make_draft(**overrides: Any) -> DraftArticle:
    payload = writing_payload()
    data: dict[str, Any] = {
        "draft_id": "draft-1",
        "proposal_id": "p1",
        "format": "onde_assistir",
        "title": payload["title"],
        "subtitle": payload["subtitle"],
        "body_markdown": payload["body_markdown"],
        "body_html": render_site_html(payload["body_markdown"]),
        "ai_summary": payload["ai_summary"],
        "seo": SeoPackage.model_validate(payload["seo"]),
        "social_posts": payload["social_posts"],
        "model": "fake/model",
        "created_at": NOW,
    }
    data.update(overrides)
    return DraftArticle.model_validate(data)


def write_state(
    database_path: Path,
    *,
    proposal: EditorialProposal | None = None,
    dossier: ResearchDossier | None = None,
    draft: DraftArticle | None = None,
) -> None:
    from fla10_agents.editorial.store import EditorialRepository

    with EditorialRepository(database_path) as store:
        if proposal is not None:
            store.save_proposal(proposal)
        if dossier is not None:
            store.save_dossier(dossier)
        if draft is not None:
            store.save_draft(draft)
