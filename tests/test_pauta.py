"""Testes das regras de pauta."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pauta

JOGO = {"mandante": "Flamengo", "visitante": "Grêmio"}


def test_consultas_incluem_o_tema_e_o_pos_jogo():
    consultas = pauta.consultas_de_busca("Flamengo x Palmeiras")

    assert consultas[0] == "Flamengo x Palmeiras"
    assert "Flamengo x Palmeiras" in consultas
    assert not any(c.startswith("Flamengo Flamengo") for c in consultas)
    assert consultas[-1] == "Flamengo escalação e declarações pós-jogo"


def test_consulta_prefixa_flamengo_quando_ausente():
    consultas = pauta.consultas_de_busca("final da Copa do Brasil")

    assert consultas[1] == "Flamengo final da Copa do Brasil"


def test_pauta_fora_do_jogo_nao_busca_escalacao():
    consultas = pauta.consultas_de_busca("Flamengo feminino na final", sobre_jogo=False)

    assert "Flamengo escalação e declarações pós-jogo" not in consultas
    assert consultas == ["Flamengo feminino na final"]


def test_pauta_do_jogo_tem_prioridade():
    assert pauta.cita_jogo("Flamengo x Grêmio — destaques", JOGO)
    assert pauta.cita_jogo("Análise do último jogo do Mengão", JOGO)


def test_pauta_de_outro_assunto_nao_tem_prioridade():
    assert not pauta.cita_jogo("Flamengo feminino na final da Copa do Brasil", JOGO)
    assert not pauta.cita_jogo("Mercado da bola: reforços para 2027", JOGO)
