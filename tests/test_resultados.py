"""Testes do coletor de resultado oficial (Cartola/ge.globo)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import resultados

CLUBES = {
    "262": {"nome": "FLA", "nome_fantasia": "FLA", "url_editoria": "https://ge.globo.com/rj/futebol/times/flamengo/"},
    "284": {"nome": "GRE", "nome_fantasia": "GRE", "url_editoria": "https://ge.globo.com/rs/futebol/times/gremio/"},
}


def _partida(casa, visitante, gols_casa, gols_visitante, local="Maracanã"):
    return {
        "clube_casa_id": casa,
        "clube_visitante_id": visitante,
        "placar_oficial_mandante": gols_casa,
        "placar_oficial_visitante": gols_visitante,
        "partida_data": "2026-11-04 19:30:00",
        "local": local,
        "clube_casa_posicao": 3,
        "clube_visitante_posicao": 12,
    }


def _fetcher(rodada_atual, rodadas):
    def buscar(url: str):
        if url.endswith("/partidas"):
            return {"rodada": rodada_atual}
        if url.endswith("/clubes"):
            return CLUBES
        numero = int(url.rsplit("/", 1)[-1])
        return {"partidas": rodadas.get(numero, [])}

    return buscar


def test_acha_ultimo_jogo_encerrado_do_flamengo():
    rodadas = {
        35: [_partida(262, 277, None, None)],
        34: [_partida(262, 284, 3, 1)],
    }
    jogo = resultados.buscar_ultimo_jogo(_fetcher(36, rodadas))

    assert jogo is not None
    assert jogo["rodada"] == 34
    assert jogo["mandante"] == "Flamengo"
    assert jogo["visitante"] == "Grêmio"
    assert jogo["gols_mandante"] == 3
    assert jogo["gols_visitante"] == 1


def test_ignora_jogo_sem_placar():
    rodadas = {35: [_partida(262, 277, None, None)]}
    assert resultados.buscar_ultimo_jogo(_fetcher(36, rodadas)) is None


def test_ignora_jogo_sem_o_flamengo():
    rodadas = {35: [_partida(284, 277, 1, 0)]}
    assert resultados.buscar_ultimo_jogo(_fetcher(36, rodadas)) is None


def test_formatar_monta_ficha_legivel():
    jogo = {
        "rodada": 34,
        "quando": "04/11/2026 19:30",
        "mandante": "Flamengo",
        "visitante": "Grêmio",
        "gols_mandante": 3,
        "gols_visitante": 1,
        "estadio": "Maracanã",
    }
    assert resultados.formatar(jogo) == (
        "Rodada 34 — 04/11/2026 19:30\n"
        "Flamengo 3 x 1 Grêmio\n"
        "Estádio: Maracanã"
    )


def test_coletar_devolve_erro_sem_derrubar():
    def falha(_url: str):
        raise OSError("rede fora do ar")

    ficha, erro = resultados.coletar(falha)

    assert ficha == ""
    assert "resultado oficial indisponível" in erro


def test_coletar_devolve_erro_quando_nao_ha_jogo():
    ficha, erro = resultados.coletar(_fetcher(36, {}))

    assert ficha == ""
    assert "nenhum jogo do Flamengo" in erro


def test_nome_desconhecido_usa_slug():
    clubes = {"999": {"nome": "XYZ", "url_editoria": "https://ge.globo.com/sp/futebol/times/novo-horizonte/"}}
    assert resultados._nome_do_clube(clubes, 999) == "Novo Horizonte"


def test_scouts_agregam_gols_assistencias_cartoes_e_ignoram_tecnico():
    dados = {
        "atletas": {
            "1": {"clube_id": 262, "apelido": "Pedro", "posicao_id": 5, "entrou_em_campo": True,
                  "scout": {"G": 2}},
            "2": {"clube_id": 262, "apelido": "Lino", "posicao_id": 5, "entrou_em_campo": True,
                  "scout": {"G": 1, "A": 1}},
            "3": {"clube_id": 264, "apelido": "Zag", "posicao_id": 3, "entrou_em_campo": True,
                  "scout": {"CA": 1}},
            "4": {"clube_id": 262, "apelido": "Técnico", "posicao_id": 6, "entrou_em_campo": True,
                  "scout": {"V": 1}},
            "5": {"clube_id": 262, "apelido": "Reserva", "posicao_id": 5, "entrou_em_campo": False,
                  "scout": {}},
        }
    }

    scouts = resultados.buscar_scouts(34, lambda _url: dados)

    assert scouts[262]["gols"] == [("Pedro", 2), ("Lino", 1)]
    assert scouts[262]["assistencias"] == [("Lino", 1)]
    assert scouts[262]["cartoes"] == []
    assert "Técnico" not in scouts[262]["entraram"]
    assert "Reserva" not in scouts[262]["entraram"]
    assert scouts[264]["cartoes"] == ["Zag (amarelo)"]


def test_formatar_inclui_detalhes_da_sumula():
    jogo = {
        "rodada": 34,
        "quando": "04/11/2026 19:30",
        "mandante": "Flamengo",
        "visitante": "Grêmio",
        "gols_mandante": 3,
        "gols_visitante": 1,
        "estadio": "Maracanã",
        "detalhes": ["Gols do Flamengo: Pedro (2), Samuel Lino"],
    }

    texto = resultados.formatar(jogo)

    assert texto.startswith("Rodada 34 — 04/11/2026 19:30\nFlamengo 3 x 1 Grêmio")
    assert texto.endswith("Gols do Flamengo: Pedro (2), Samuel Lino")
