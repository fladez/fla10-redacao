"""Testes da área "Pautas e minutas" da interface Streamlit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import ReviewIssue, ReviewReport
from tests.support import (
    NOW,
    make_dossier,
    make_draft,
    make_proposal,
    write_state,
)

APP = Path(__file__).resolve().parents[1] / "app.py"


def _abrir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("FLA10_EDITORIAL_DATABASE", str(tmp_path / "editorial.db"))
    monkeypatch.setenv("FLA10_CALENDAR_DATABASE", str(tmp_path / "calendar.db"))
    monkeypatch.setenv("FLA10_EXPORTS", str(tmp_path / "exports"))
    return AppTest.from_file(str(APP), default_timeout=180).run()


def _salvar_revisao(
    banco: Path,
    *,
    verdict: str,
    severidade: str | None = None,
) -> None:
    issues = []
    if severidade is not None:
        issues.append(
            ReviewIssue(
                severity=severidade,  # type: ignore[arg-type]
                category="factualidade",
                description="Afirmação sem evidência no dossiê.",
                evidence="trecho de teste",
            )
        )
    with EditorialRepository(banco) as store:
        store.save_review(
            ReviewReport(
                draft_id="draft-1",
                verdict=verdict,
                issues=issues,
                reviewer_model="teste",
                reviewed_at=NOW,
            )
        )


def _painel_com_minuta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    decisao_pauta: str = "approved",
    severidade: str | None = None,
) -> AppTest:
    banco = tmp_path / "editorial.db"
    write_state(
        banco,
        proposal=make_proposal(decision=decisao_pauta),
        dossier=make_dossier(),
        draft=make_draft(),
    )
    _salvar_revisao(banco, verdict="ajustes_necessarios", severidade=severidade)
    return _abrir(tmp_path, monkeypatch)


def test_area_padrao_mostra_as_cinco_etapas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)

    assert not list(at.exception)
    assert [header.value for header in at.header] == ["Pautas e minutas"]
    assert [sub.value for sub in at.subheader] == [
        "1. Propostas",
        "2. Dossiê",
        "3. Minuta",
        "4. Revisão",
        "5. Decisão",
    ]
    assert {"Gerar propostas", "Gerar minuta", "Aprovar minuta"} <= {
        botao.label for botao in at.button
    }


def test_minuta_revisao_e_decisao_aparecem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)

    assert not list(at.exception)
    assert any("Flamengo x Palmeiras" in markdown.value for markdown in at.markdown)
    assert any("ajustes_necessarios" in aviso.value for aviso in at.warning)
    assert [aba.label for aba in at.tabs] == [
        "Corpo",
        "SEO",
        "Redes",
        "Fontes",
        "Ficha técnica",
    ]


def test_problema_grave_gera_alerta_vermelho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch, severidade="alto")

    assert not list(at.exception)
    assert any("severidade alta" in erro.value for erro in at.error)


def test_aprovacao_registra_decisao_sem_publicar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)
    botoes = {botao.label: botao for botao in at.button}

    botoes["Aprovar minuta"].click().run()

    assert not list(at.exception)
    assert any("Decisão registrada: **approved**" in info.value for info in at.info)
    assert any("Nada foi publicado" in sucesso.value for sucesso in at.success)

    with EditorialRepository(tmp_path / "editorial.db") as store:
        texto = store.get_draft("draft-1")
    assert texto is not None
    assert texto.editorial_decision == "approved"


def test_pauta_nao_aprovada_bloqueia_dossie_e_minuta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch, decisao_pauta="awaiting_human")

    assert not list(at.exception)
    botoes = {botao.label: botao for botao in at.button}
    assert botoes["Refazer dossiê"].disabled
    assert botoes["Gerar minuta"].disabled
    assert "Aprovar pauta" in botoes


def test_base_vazia_orienta_a_gerar_propostas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with EditorialRepository(tmp_path / "editorial.db"):
        pass

    at = _abrir(tmp_path, monkeypatch)

    assert not list(at.exception)
    assert any("Nenhuma proposta registrada" in info.value for info in at.info)
    assert [botao.label for botao in at.button] == ["Gerar propostas"]


def test_modelo_de_afirmacoes_tem_claims_e_data_em_branco() -> None:
    from painel_editorial import modelo_claims_json

    modelo = json.loads(modelo_claims_json())

    assert isinstance(modelo["claims"], list)
    assert modelo["claims"][0]["evidence"][0]["accessed_at"] == ""


def test_preparar_claims_preenche_accessed_at_no_envio() -> None:
    from datetime import UTC, datetime

    from painel_editorial import preparar_claims

    agora = datetime(2026, 11, 11, 9, 30, tzinfo=UTC)
    payload = preparar_claims(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "claim_text": "Horário confirmado.",
                    "classification": "confirmed",
                    "evidence": [
                        {"url": "https://example.com/a", "accessed_at": ""},
                        {"url": "https://example.com/b", "accessed_at": "PREENCHER"},
                        {"url": "https://example.com/c"},
                    ],
                }
            ]
        },
        agora=agora,
    )

    datas = [
        evidencia["accessed_at"]
        for evidencia in payload["claims"][0]["evidence"]
    ]
    assert datas == [agora.isoformat()] * 3
    assert payload["claims"][0]["claim_text"] == "Horário confirmado."


def test_preparar_claims_preserva_data_informada() -> None:
    from painel_editorial import preparar_claims

    payload = preparar_claims(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "claim_text": "Fato.",
                    "classification": "confirmed",
                    "evidence": [
                        {
                            "url": "https://example.com/a",
                            "accessed_at": "2026-11-10T08:00:00-03:00",
                        }
                    ],
                }
            ]
        }
    )

    assert (
        payload["claims"][0]["evidence"][0]["accessed_at"]
        == "2026-11-10T08:00:00-03:00"
    )


def test_preparar_claims_recusa_formato_invalido() -> None:
    from painel_editorial import preparar_claims

    with pytest.raises(TypeError):
        preparar_claims({"claims": "não é lista"})
    with pytest.raises(TypeError):
        preparar_claims("texto")


def test_painel_oferece_modelo_e_campo_de_afirmacoes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)

    assert not list(at.exception)
    assert any(
        botao.label == "Baixar modelo JSON"
        for botao in at.get("download_button")
    )
    assert at.text_area(key="painel-claims-texto") is not None
    assert at.text_area(key="painel-contradicoes") is not None


def test_painel_grava_afirmacoes_no_dossie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)
    at.text_area(key="painel-claims-texto").input(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "c-extra",
                        "claim_text": "O jogo começa às 21h30.",
                        "classification": "confirmed",
                        "evidence": [
                            {
                                "url": "https://example.com/tabela",
                                "source_type": "tabela oficial",
                                "author_or_institution": "CBF",
                                "accessed_at": "",
                                "supports": ["horário"],
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )
    ).run()

    botoes = {botao.label: botao for botao in at.button}
    botoes["Refazer dossiê"].click().run()

    assert not list(at.exception)
    with EditorialRepository(tmp_path / "editorial.db") as store:
        dossie = store.get_dossier("p1")

    assert dossie is not None
    extra = next(
        claim for claim in dossie.claims if claim.claim_id == "c-extra"
    )
    assert extra.evidence[0].accessed_at is not None


def test_painel_recusa_afirmacoes_invalidas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _painel_com_minuta(tmp_path, monkeypatch)
    at.text_area(key="painel-claims-texto").input("{invalido").run()

    botoes = {botao.label: botao for botao in at.button}
    botoes["Refazer dossiê"].click().run()

    assert not list(at.exception)
    assert any("JSON inválido" in erro.value for erro in at.error)
