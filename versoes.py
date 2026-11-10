"""Separação e gravação das versões produzidas pelo revisor.

Fica fora do main.py para poder ser testado sem carregar o CrewAI.
"""

import re
from datetime import datetime
from pathlib import Path

MARCADOR_VERSAO = re.compile(r"<!--\s*VERSAO:(\d+)\s*-->", re.IGNORECASE)
TITULO_VERSAO = re.compile(r"^##\s+Vers[ãa]o\b.*$", re.IGNORECASE | re.MULTILINE)


def separar_versoes(texto: str) -> list[tuple[int, str]]:
    """Divide a saída do revisor em versões numeradas.

    Usa o marcador <!-- VERSAO:n -->; se o modelo esquecer, cai para os títulos
    '## Versão ...' para não perder o trabalho.
    """
    partes = MARCADOR_VERSAO.split(texto)
    versoes: list[tuple[int, str]] = []
    for indice in range(1, len(partes), 2):
        corpo = partes[indice + 1].strip()
        if corpo:
            versoes.append((int(partes[indice]), corpo))

    if len(versoes) >= 2:
        return versoes

    trechos = TITULO_VERSAO.split(texto)
    if len(trechos) > 2:
        return [
            (numero, trecho.strip())
            for numero, trecho in enumerate(trechos[1:], start=1)
            if trecho.strip()
        ]
    return versoes


def salvar_versoes(
    texto: str,
    versoes: list[tuple[int, str]],
    base: Path | str = "exports",
    quando: datetime | None = None,
) -> Path:
    """Grava a saída completa e um arquivo por versão; devolve a pasta usada."""
    pasta = Path(base) / (quando or datetime.now()).strftime("redacao-%Y-%m-%d-%H%M")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "completa.md").write_text(texto + "\n", encoding="utf-8")
    for numero, corpo in versoes:
        (pasta / f"versao-{numero}.md").write_text(corpo + "\n", encoding="utf-8")
    return pasta
