"""Regras da pauta: consultas de busca e relação com a ficha do último jogo."""

from typing import Any


def consultas_de_busca(tema: str) -> list[str]:
    """Consultas do Google News: o tema, o clube quando falta e o pós-jogo."""
    consultas = [tema]
    if "flamengo" not in tema.lower():
        consultas.append(f"Flamengo {tema}")
    consultas.append("Flamengo escalação e declarações pós-jogo")
    return consultas


def cita_jogo(pauta: str, jogo: dict[str, Any]) -> bool:
    """Diz se a pauta trata daquele jogo, para decidir a prioridade da ficha.

    O Flamengo é sempre um dos lados; quem identifica a partida é o adversário
    ou uma expressão genérica de resultado.
    """
    tema = pauta.lower()
    times = [str(jogo.get("mandante", "")).lower(), str(jogo.get("visitante", "")).lower()]
    if any(time and time != "flamengo" and time in tema for time in times):
        return True
    genericos = ("último jogo", "ultimo jogo", "resultado", "placar", "escalação")
    return any(palavra in tema for palavra in genericos)
