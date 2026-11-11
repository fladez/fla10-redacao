"""Testes da geração de propostas a partir das pautas do vault."""

from __future__ import annotations

from datetime import date

import pytest

from fla10_agents.editorial.pautas import Pauta
from fla10_agents.editorial.proposals import (
    PAUTA_STATUS_ENCERRADOS,
    build_proposals,
    proposals_from_pautas,
)
from tests.support import NOW


def make_pauta(
    title: str = "Coritiba x Flamengo: o que está confirmado",
    *,
    status: str = "reservada",
    kind: str = "reservada",
    window: date | None = date(2026, 11, 29),
    fields: dict[str, str] | None = None,
    source: str = "06 - Pautas/Painel de Pautas.md",
) -> Pauta:
    return Pauta(
        title=title,
        status=status,
        kind=kind,
        window=window,
        fields=fields or {},
        source=source,
    )


def test_pauta_vigente_vira_proposta_com_angulo_e_checagens() -> None:
    pauta = make_pauta(
        kind="mencionada",
        fields={
            "Foco": "impacto das ausências na defesa.",
            "Checagens": "lista oficial e alternativas prováveis.",
        }
    )

    proposals = proposals_from_pautas([pauta], now=NOW)

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.title == pauta.title
    assert proposal.format == "ultimas_noticias"
    assert proposal.angle == "impacto das ausências na defesa."
    assert proposal.questions_to_verify == ["lista oficial e alternativas prováveis."]
    assert proposal.window == "2026-11-29"
    assert proposal.confirmed_facts == []
    assert proposal.initial_sources == []
    assert proposal.priority_recommendation == "normal"
    assert proposal.editorial_decision == "awaiting_human"
    assert proposal.created_at == NOW


def test_angulo_prefere_angulo_sobre_foco() -> None:
    pauta = make_pauta(
        fields={"Ângulo": "ângulo principal", "Foco": "foco secundário"}
    )

    proposal = proposals_from_pautas([pauta], now=NOW)[0]

    assert proposal.angle == "ângulo principal"


def test_pauta_sem_angulo_usa_texto_padrao() -> None:
    proposal = proposals_from_pautas([make_pauta()], now=NOW)[0]

    assert proposal.angle == "Desenvolver a pauta registrada no vault editorial."


def test_pauta_vencida_fica_fora() -> None:
    pauta = make_pauta(window=date(2026, 11, 9))

    assert proposals_from_pautas([pauta], now=NOW) == []


def test_pauta_com_janela_de_hoje_entra() -> None:
    pauta = make_pauta(window=NOW.date())

    assert len(proposals_from_pautas([pauta], now=NOW)) == 1


@pytest.mark.parametrize("status", sorted(PAUTA_STATUS_ENCERRADOS))
def test_estado_encerrado_fica_fora(status: str) -> None:
    pauta = make_pauta(status=status, window=date(2026, 12, 1))

    assert proposals_from_pautas([pauta], now=NOW) == []


def test_pauta_projeto_sem_janela_entra_com_prioridade_baixa() -> None:
    pauta = make_pauta(
        title="Flamengo recusou milhões para manter o elenco",
        kind="projeto",
        status="reservada",
        window=None,
        fields={"Objetivo": "estratégia de mercado.", "Cuidados": "confirmar valores."},
    )

    proposals = proposals_from_pautas([pauta], now=NOW)

    assert len(proposals) == 1
    assert proposals[0].window is None
    assert proposals[0].priority_recommendation == "baixa"
    assert proposals[0].questions_to_verify == ["confirmar valores."]


def test_pauta_nao_concorre_consigo_mesma() -> None:
    pauta = make_pauta(fields={"Foco": "gestão de vantagem no segundo tempo."})

    proposal = proposals_from_pautas([pauta], now=NOW)[0]

    assert proposal.redundancy_risk == "baixo"
    assert proposal.related_reserved == []
    assert proposal.related_published == []


def test_outra_pauta_semelhante_aparece_como_redundancia() -> None:
    primeira = make_pauta(
        title="Flamengo precisa aprender a matar jogos?",
        fields={"Foco": "gestão de vantagem no segundo tempo."},
    )
    segunda = make_pauta(
        title="Flamengo precisa aprender a matar jogos",
        fields={"Foco": "gestão de vantagem no segundo tempo."},
    )

    propostas = proposals_from_pautas([primeira, segunda], now=NOW)

    assert len(propostas) == 2
    for proposta in propostas:
        assert proposta.title not in proposta.related_reserved
        assert proposta.related_reserved


def test_materia_publicada_entra_como_redundancia() -> None:
    pauta = make_pauta(title="Coritiba x Flamengo: onde assistir e horário")

    proposal = proposals_from_pautas(
        [pauta],
        published=["Coritiba x Flamengo: onde assistir, horário e o que esperar"],
        now=NOW,
    )[0]

    assert proposal.related_published
    assert "matéria publicada" not in proposal.related_reserved


def test_identificador_e_estavel_entre_execucoes() -> None:
    pauta = make_pauta()

    primeiro = proposals_from_pautas([pauta], now=NOW)[0]
    segundo = proposals_from_pautas([pauta], now=NOW)[0]

    assert primeiro.proposal_id == segundo.proposal_id
    assert primeiro.dedupe_key == segundo.dedupe_key


def test_build_proposals_soma_agenda_sinais_e_pautas() -> None:
    pauta = make_pauta()

    proposals = build_proposals([], [], [pauta], now=NOW)

    assert len(proposals) == 1
    assert proposals[0].title == pauta.title


def test_mesma_pauta_com_janelas_diferentes_nao_duplica() -> None:
    primeira = make_pauta(window=date(2026, 11, 20))
    segunda = make_pauta(window=date(2026, 11, 29))

    proposals = proposals_from_pautas([primeira, segunda], now=NOW)

    assert len(proposals) == 1
    assert proposals[0].window == "2026-11-20"
    assert proposals[0].related_reserved == []
