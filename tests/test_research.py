from datetime import UTC, datetime

from fla10_agents.models import (
    ClaimClassification,
    ClaimEvidence,
    EditorialProposal,
    EvidenceSource,
)
from fla10_agents.research import build_dossier, claims_from_payload

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def make_proposal(
    confirmed_facts: list[str] | None = None,
    questions: list[str] | None = None,
) -> EditorialProposal:
    return EditorialProposal(
        proposal_id="p1",
        title="Flamengo x Palmeiras: onde assistir",
        format="onde_assistir",
        editorial_question="Como assistir ao jogo?",
        angle="Serviço de jogo.",
        why_now="Jogo na semana.",
        confirmed_facts=confirmed_facts or [],
        questions_to_verify=questions or [],
        initial_sources=[
            EvidenceSource(
                url="https://example.com/tabela",
                source_type="tabela oficial",
                author_or_institution="CBF",
                accessed_at=NOW,
            )
        ],
        created_at=NOW,
    )


def make_claim(
    text: str,
    classification: ClaimClassification,
    *,
    author: str | None = None,
) -> ClaimEvidence:
    evidence = []
    if author is not None:
        evidence.append(
            EvidenceSource(
                url="https://example.com/fonte",
                source_type="oficial",
                author_or_institution=author,
                accessed_at=NOW,
            )
        )

    return ClaimEvidence(
        claim_id=text[:8],
        claim_text=text,
        classification=classification,
        evidence=evidence,
    )


def test_confirmed_facts_with_source_become_usable() -> None:
    dossier = build_dossier(
        make_proposal(confirmed_facts=["Jogo no Maracanã"]),
        researched_at=NOW,
    )

    assert dossier.usable_facts == ["Jogo no Maracanã"]
    assert dossier.gaps == []
    assert dossier.recommendation == "pronto para redação"


def test_confirmed_fact_without_source_is_a_critical_gap() -> None:
    proposal = make_proposal(confirmed_facts=["Jogo no Maracanã"])
    proposal.initial_sources = []

    dossier = build_dossier(proposal, researched_at=NOW)

    assert dossier.usable_facts == []
    assert any("sem evidência" in gap for gap in dossier.gaps)
    assert dossier.recommendation == "apuração insuficiente"


def test_attributed_claim_requires_named_author() -> None:
    dossier = build_dossier(
        make_proposal(),
        [make_claim("O técnico confirmou o time.", ClaimClassification.ATTRIBUTED)],
        researched_at=NOW,
    )

    assert any("sem autor identificado" in gap for gap in dossier.gaps)
    assert dossier.attribution_required == ["O técnico confirmou o time."]
    assert dossier.recommendation == "apuração insuficiente"


def test_attributed_claim_with_author_is_kept_and_flagged() -> None:
    dossier = build_dossier(
        make_proposal(),
        [
            make_claim(
                "O técnico confirmou o time.",
                ClaimClassification.ATTRIBUTED,
                author="Assessoria do clube",
            )
        ],
        researched_at=NOW,
    )

    assert dossier.attribution_required == ["O técnico confirmou o time."]
    assert not any("sem autor identificado" in gap for gap in dossier.gaps)


def test_analysis_is_admissible_but_hypothesis_is_excluded() -> None:
    dossier = build_dossier(
        make_proposal(),
        [
            make_claim("O time deve jogar no 4-2-3-1.", ClaimClassification.ANALYSIS),
            make_claim("O técnico pode poupar titulares.", ClaimClassification.HYPOTHESIS),
            make_claim("O jogo pode ser adiado.", ClaimClassification.UNCONFIRMED),
        ],
        researched_at=NOW,
    )

    assert dossier.admissible_analysis == ["O time deve jogar no 4-2-3-1."]
    assert dossier.excluded_claims == [
        "O técnico pode poupar titulares.",
        "O jogo pode ser adiado.",
    ]


def test_contradictions_change_recommendation() -> None:
    dossier = build_dossier(
        make_proposal(confirmed_facts=["Jogo no Maracanã"]),
        contradictions=["Uma fonte informa outro estádio."],
        researched_at=NOW,
    )

    assert dossier.recommendation == "revisar contradições"
    assert len(dossier.contradictions) == 1


def test_questions_to_verify_join_existing_gaps() -> None:
    dossier = build_dossier(
        make_proposal(confirmed_facts=["Jogo no Maracanã"], questions=["Confirmar arbitragem"]),
        researched_at=NOW,
    )

    assert dossier.gaps == ["Confirmar arbitragem"]


def test_dossier_without_facts_or_questions_records_explicit_gap() -> None:
    dossier = build_dossier(make_proposal(), researched_at=NOW)

    assert dossier.usable_facts == []
    assert dossier.gaps == ["Nenhum fato confirmado com evidência disponível."]
    assert dossier.recommendation == "apuração insuficiente"


def test_claims_from_payload_validates_items() -> None:
    claims = claims_from_payload({"claims": [{
        "claim_id": "c1",
        "claim_text": "O jogo é no Maracanã.",
        "classification": "confirmed",
    }]})

    assert len(claims) == 1
    assert claims[0].claim_text == "O jogo é no Maracanã."


def test_claims_from_payload_rejects_invalid_shape() -> None:
    from fla10_agents.research import ResearchInputError

    try:
        claims_from_payload({"itens": []})
    except ResearchInputError as exc:
        assert "afirmações" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("payload inválido deveria falhar")
