"""Comparação determinística de pautas para evitar redundância editorial."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from fla10_agents.editorial.pautas import Pauta

STOPWORDS = frozenset({
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "essa", "esse", "esta", "este", "eu", "mais", "mas",
    "na", "nas", "no", "nos", "o", "os", "ou", "para", "pelo", "pela", "por",
    "que", "se", "sem", "ser", "sobre", "um", "uma", "vai", "nao", "não",
    "reacende", "precisa", "pode", "tem", "ter", "foi", "sao", "são",
})

HIGH_RISK = 0.55
MEDIUM_RISK = 0.35


@dataclass(frozen=True, slots=True)
class RedundancyMatch:
    title: str
    source: str
    score: float
    shared_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RedundancyReport:
    risk: str
    score: float
    matches: tuple[RedundancyMatch, ...]

    @property
    def related_titles(self) -> list[str]:
        return [match.title for match in self.matches]


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return without_accents.casefold()


def tokenize(text: str) -> set[str]:
    terms = re.findall(r"[a-z0-9]+", _normalize(text))
    return {term for term in terms if len(term) > 2 and term not in STOPWORDS}


def _score(candidate: set[str], target: set[str]) -> tuple[float, tuple[str, ...]]:
    if not candidate or not target:
        return 0.0, ()

    shared = candidate & target
    union = candidate | target
    return len(shared) / len(union), tuple(sorted(shared))


def check_redundancy(
    title: str,
    context: str = "",
    pautas: Iterable[Pauta] = (),
    published: Iterable[str] = (),
) -> RedundancyReport:
    """Mede sobreposição de assunto com pautas e matérias já registradas.

    A nota é uma triagem para revisão humana: ela aponta sobreposição de
    termos, não decide sozinha se a pauta deve existir.
    """
    candidate_title = tokenize(title)
    candidate_full = tokenize(f"{title} {context}")
    matches: list[RedundancyMatch] = []

    def _best(target: set[str]) -> tuple[float, tuple[str, ...]]:
        by_title = _score(candidate_title, target)
        by_context = _score(candidate_full, target)
        return by_context if by_context[0] > by_title[0] else by_title

    for pauta in pautas:
        score, shared = _best(tokenize(pauta.context_text))
        title_score, title_shared = _score(candidate_title, tokenize(pauta.title))
        if title_score > score:
            score, shared = title_score, title_shared
        if score > 0:
            matches.append(
                RedundancyMatch(
                    title=pauta.title,
                    source=pauta.source,
                    score=round(score, 3),
                    shared_terms=shared,
                )
            )

    for published_title in published:
        score, shared = _best(tokenize(published_title))
        if score > 0:
            matches.append(
                RedundancyMatch(
                    title=published_title,
                    source="matéria publicada",
                    score=round(score, 3),
                    shared_terms=shared,
                )
            )

    matches.sort(key=lambda item: (-item.score, item.title))
    best = matches[0].score if matches else 0.0

    if best >= HIGH_RISK:
        risk = "alto"
    elif best >= MEDIUM_RISK:
        risk = "medio"
    else:
        risk = "baixo"

    return RedundancyReport(risk=risk, score=best, matches=tuple(matches[:5]))
