"""Ficha oficial do último jogo do Flamengo.

Fonte: API pública do Cartola FC (ge.globo), sem chave de API.
Serve para dar à apuração um placar confiável, já que o RSS do Google News
costuma trazer apenas manchetes e resumos, sem o resultado da partida.
"""

import json
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any

API_CARTOLA = "https://api.cartolafc.globo.com"
FLAMENGO_ID = 262
TIMEOUT_SEGUNDOS = 20
RODADAS_ATRAS = 6
USER_AGENT = "Fla10-Agents/0.1 (+apuracao)"

# A API devolve abreviações como "FLA" e "GRE"; estes são os nomes usados no site.
NOMES_SERIE_A = {
    262: "Flamengo",
    263: "Botafogo",
    264: "Corinthians",
    265: "Bahia",
    266: "Fluminense",
    267: "Vasco",
    275: "Palmeiras",
    276: "São Paulo",
    277: "Santos",
    280: "Red Bull Bragantino",
    282: "Atlético-MG",
    283: "Cruzeiro",
    284: "Grêmio",
    285: "Internacional",
    287: "Vitória",
    293: "Athletico-PR",
    294: "Coritiba",
    315: "Chapecoense",
    364: "Remo",
    2305: "Mirassol",
}

Fetcher = Callable[[str], Any]


def _json(url: str) -> Any:
    requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _nome_do_clube(dados: dict[str, Any], clube_id: int) -> str:
    if clube_id in NOMES_SERIE_A:
        return NOMES_SERIE_A[clube_id]
    clube = dados.get(str(clube_id)) or {}
    slug = (clube.get("url_editoria") or "").rstrip("/").split("/")[-1]
    if slug:
        return slug.replace("-", " ").title()
    nome = clube.get("nome_fantasia") or clube.get("nome")
    return str(nome) if nome else f"clube {clube_id}"


def _data_legivel(texto: str) -> str:
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return texto or "data desconhecida"


def buscar_ultimo_jogo(
    fetcher: Fetcher = _json,
    flamengo_id: int = FLAMENGO_ID,
    rodadas_atras: int = RODADAS_ATRAS,
) -> dict[str, Any] | None:
    """Volta rodada por rodada até achar o último jogo do Flamengo já encerrado."""
    atual = int(fetcher(f"{API_CARTOLA}/partidas")["rodada"])

    for rodada in range(atual, max(atual - rodadas_atras, 1) - 1, -1):
        dados = fetcher(f"{API_CARTOLA}/partidas/{rodada}")
        for partida in dados.get("partidas", []):
            mandante = partida.get("clube_casa_id")
            visitante = partida.get("clube_visitante_id")
            if flamengo_id not in (mandante, visitante):
                continue
            gols_mandante = partida.get("placar_oficial_mandante")
            gols_visitante = partida.get("placar_oficial_visitante")
            if gols_mandante is None or gols_visitante is None:
                continue

            clubes = fetcher(f"{API_CARTOLA}/clubes")
            return {
                "rodada": rodada,
                "quando": _data_legivel(partida.get("partida_data", "")),
                "mandante": _nome_do_clube(clubes, int(mandante)),
                "visitante": _nome_do_clube(clubes, int(visitante)),
                "gols_mandante": int(gols_mandante),
                "gols_visitante": int(gols_visitante),
                "estadio": partida.get("local") or "não informado",
                "posicao_mandante": partida.get("clube_casa_posicao"),
                "posicao_visitante": partida.get("clube_visitante_posicao"),
            }
    return None


def formatar(jogo: dict[str, Any]) -> str:
    """Transforma o jogo em um bloco curto para entrar no prompt de apuração."""
    return (
        f"Rodada {jogo['rodada']} — {jogo['quando']}\n"
        f"{jogo['mandante']} {jogo['gols_mandante']} x {jogo['gols_visitante']} "
        f"{jogo['visitante']}\n"
        f"Estádio: {jogo['estadio']}"
    )


def coletar(fetcher: Fetcher = _json) -> tuple[str, str]:
    """Devolve (ficha pronta, erro). Um dos dois vem vazio."""
    try:
        jogo = buscar_ultimo_jogo(fetcher)
    except Exception as erro:  # noqa: BLE001 - fonte fora do ar não derruba o pipeline
        return "", f"resultado oficial indisponível: {erro}"
    if jogo is None:
        return "", "nenhum jogo do Flamengo encerrado encontrado nas últimas rodadas"
    return formatar(jogo), ""
