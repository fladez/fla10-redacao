"""Verificações determinísticas das versões antes da aprovação humana.

Não substitui o Revisor: pega falhas mecânicas que passariam batido, como
versão sem título, texto curto, marcador vazado ou duas versões quase iguais.
"""

import re
from dataclasses import dataclass

MIN_CARACTERES = 400
SIMILARIDADE_MAXIMA = 0.9
MARCADORES_RESIDUAIS = ("<!-- VERSAO", "VERSAO:")

_PALAVRA = re.compile(r"[a-z0-9áéíóúâêôãõç]+", re.IGNORECASE)
_TITULO = re.compile(r"^#{1,2}\s+\S")
_DADO_AUSENTE = re.compile(
    r"\bn[ãa]o\s+(?:foi|foram|era|eram)?\s*(?:divulgad|divulgou|informad|informou"
    r"|registrad|registrou|havia informa)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Aviso:
    """Um problema encontrado, com a versão que o originou (se houver)."""

    nivel: str
    mensagem: str
    versao: int | None = None

    @property
    def critico(self) -> bool:
        return self.nivel == "erro"

    def __str__(self) -> str:
        onde = f"versão {self.versao}: " if self.versao else ""
        return f"[{self.nivel}] {onde}{self.mensagem}"


def _palavras(texto: str) -> set[str]:
    return {palavra.lower() for palavra in _PALAVRA.findall(texto)}


def similaridade(a: str, b: str) -> float:
    """Jaccard entre as palavras das duas versões, de 0 a 1."""
    palavras_a, palavras_b = _palavras(a), _palavras(b)
    if not palavras_a or not palavras_b:
        return 0.0
    return len(palavras_a & palavras_b) / len(palavras_a | palavras_b)


def _fechado(texto: str, marcador: str) -> bool:
    return texto.count(marcador) % 2 == 0


def avaliar(versoes: list[tuple[int, str]], esperadas: int = 4) -> list[Aviso]:
    """Lista os problemas das versões; lista vazia significa tudo certo."""
    avisos: list[Aviso] = []

    if len(versoes) != esperadas:
        avisos.append(
            Aviso(
                "atencao",
                f"esperava {esperadas} versões e encontrei {len(versoes)}",
            )
        )

    for numero, corpo in versoes:
        if not _TITULO.match(corpo.lstrip()):
            avisos.append(
                Aviso("erro", "não começa com título Markdown ('# ' ou '## ')", numero)
            )
        if len(corpo) < MIN_CARACTERES:
            avisos.append(
                Aviso(
                    "atencao",
                    f"texto curto: {len(corpo)} caracteres (mínimo {MIN_CARACTERES})",
                    numero,
                )
            )
        if any(marcador in corpo.upper() for marcador in MARCADORES_RESIDUAIS):
            avisos.append(Aviso("erro", "marcador de versão vazou para o texto", numero))
        if not _fechado(corpo, "**"):
            avisos.append(Aviso("atencao", "negrito (**) não fechado", numero))
        if corpo.count("```") % 2 != 0:
            avisos.append(Aviso("atencao", "bloco de código não fechado", numero))
        if re.search(r"\bn[ãa]o encontrad[oa]\b", corpo, re.IGNORECASE):
            avisos.append(
                Aviso(
                    "atencao",
                    "usa 'não encontrado' no corpo; confira se a informação faltou",
                    numero,
                )
            )
        ausentes = len(_DADO_AUSENTE.findall(corpo))
        if ausentes >= 2:
            avisos.append(
                Aviso(
                    "atencao",
                    f"{ausentes} trechos de dado ausente ('não divulgado/informado'); "
                    "confira se a pauta pedia esse dado",
                    numero,
                )
            )

    for indice, (numero_a, corpo_a) in enumerate(versoes):
        for numero_b, corpo_b in versoes[indice + 1 :]:
            taxa = similaridade(corpo_a, corpo_b)
            if taxa > SIMILARIDADE_MAXIMA:
                avisos.append(
                    Aviso(
                        "atencao",
                        f"versões {numero_a} e {numero_b} são quase iguais "
                        f"({taxa:.0%} de vocabulário em comum)",
                    )
                )

    return avisos


def pode_aprovar(avisos: list[Aviso]) -> bool:
    """Só bloqueia o que impediria a leitura; o resto fica como alerta."""
    return not any(aviso.critico for aviso in avisos)
