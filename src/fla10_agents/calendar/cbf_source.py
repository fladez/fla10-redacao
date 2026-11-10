"""Leitor da tabela detalhada oficial da CBF em PDF."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Self

import httpx
from pydantic import HttpUrl
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from fla10_agents.models import EventStatus, EvidenceSource, SportsEvent
from fla10_agents.net import get_with_retries

MAX_PDF_BYTES = 25 * 1024 * 1024


class CBFSourceError(RuntimeError):
    """Falha ao consultar ou interpretar a tabela oficial da CBF."""


_UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR",
    "SC", "SP", "SE", "TO",
]
_UF = re.compile(r"\b(" + "|".join(_UFS) + r")\b")
_CODE_AND_REST = re.compile(r"^\s*(\d{3})\s+(.+?)\s*$")
_ROUND = re.compile(r"\d{1,2}[ªº]?")
_DATE = re.compile(r"\d{2}/\d{2}")
_TIME = re.compile(r"\d{2}:\d{2}")
_WEEKDAY = re.compile(r"\w{3}")
_SCORED = re.compile(
    r"^(?P<home>.+?)\s+(?P<home_goals>\d+)\s*x\s+(?P<away_goals>\d+)\s+(?P<away>.+)$"
)
_UNSCORED = re.compile(r"^(?P<home>.+?)\s+x\s+(?P<away>.+)$")


def _split_team_and_remainder(value: str) -> tuple[str, str]:
    match = _UF.search(value)
    if match is None:
        raise CBFSourceError(f"Não foi possível identificar a UF na linha: {value}")
    return value[: match.end()].strip(), value[match.end() :].strip()


def _split_fixture(rest: str) -> tuple[str, str]:
    """Separa mandante e visitante, com ou sem placar no meio."""
    scored = _SCORED.match(rest)
    if scored is not None:
        return scored["home"].strip(), scored["away"].strip()

    unscored = _UNSCORED.match(rest)
    if unscored is None:
        raise CBFSourceError(f"Não foi possível separar os times na linha: {rest}")

    return unscored["home"].strip(), unscored["away"].strip()


def _parse_row(line: str) -> tuple[str, str | None, str | None, str | None, str] | None:
    """Extrai código, rodada, data/hora e o trecho com os dois times.

    A tabela real varia: algumas linhas trazem rodada e data, outras só a
    rodada, e as rodadas finais ainda não têm data marcada.
    """
    match = _CODE_AND_REST.match(line)
    if match is None:
        return None

    code, rest = match.groups()
    tokens = rest.split()

    round_number: str | None = None
    if tokens and _ROUND.fullmatch(tokens[0]):
        round_number = tokens.pop(0).rstrip("ªº")

    date_text: str | None = None
    if tokens and _DATE.fullmatch(tokens[0]):
        date_text = tokens.pop(0)
        if tokens and _WEEKDAY.fullmatch(tokens[0]):
            tokens.pop(0)

    time_text: str | None = None
    if tokens and _TIME.fullmatch(tokens[0]):
        time_text = tokens.pop(0)

    if not tokens:
        return None

    return code, round_number, date_text, time_text, " ".join(tokens)


def _remove_trailing_numbers(value: str) -> str:
    """Remove anotações numéricas de transmissão ao fim da linha."""
    return re.sub(r"\s+(?:\d+\s*)+$", "", value).strip()


def parse_cbf_table_text(
    content: str,
    *,
    season: int,
    source_url: str,
    accessed_at: datetime | None = None,
) -> list[tuple[SportsEvent, str]]:
    """Extrai somente partidas do Flamengo, preservando o código oficial do jogo."""
    verified_at = accessed_at or datetime.now(UTC)
    source = EvidenceSource(
        url=HttpUrl(source_url),
        source_type="documento oficial de competição",
        author_or_institution="Confederação Brasileira de Futebol",
        accessed_at=verified_at,
        supports=["data", "horário", "mandante", "visitante", "estádio", "competição"],
        limitations=(
            "Tabela detalhada do Campeonato Brasileiro Série A; "
            "sujeita a retificações da CBF."
        ),
    )
    results: list[tuple[SportsEvent, str]] = []

    for line in content.splitlines():
        row = _parse_row(line.strip())
        if row is None:
            continue

        external_code, round_number, date_text, time_text, rest = row
        home_raw, away_raw = _split_fixture(rest)
        home_team, _ = _split_team_and_remainder(home_raw)
        away_team, venue = _split_team_and_remainder(away_raw)
        venue = _remove_trailing_numbers(venue)

        home_name = re.sub(
            r"\s+(?:" + "|".join(_UFS) + r")$", "", home_team
        ).strip()
        away_name = re.sub(
            r"\s+(?:" + "|".join(_UFS) + r")$", "", away_team
        ).strip()
        if "flamengo" not in (home_name + " " + away_name).casefold():
            continue

        starts_at = None
        event_status = EventStatus.PROVISIONAL

        if date_text and time_text:
            day, month = (int(part) for part in date_text.split("/"))
            starts_at = datetime(
                season, month, day, int(time_text[:2]), int(time_text[3:])
            )
            event_status = EventStatus.CONFIRMED

        event = SportsEvent(
            sport="futebol",
            category="profissional masculino",
            competition="Campeonato Brasileiro Série A",
            season=str(season),
            stage=f"rodada {round_number}" if round_number else None,
            home_team=home_name,
            away_team=away_name,
            starts_at_local=starts_at,
            timezone="America/Sao_Paulo",
            venue=venue or None,
            event_status=event_status,
            sources=[source],
            last_verified_at=verified_at,
        )
        results.append((event, f"{season}:{external_code}"))

    if not results:
        raise CBFSourceError(
            "A tabela foi lida, mas nenhuma partida do Flamengo foi encontrada. "
            "A importação foi interrompida sem gravar eventos."
        )
    return results


class CBFCalendarSource:
    """Baixa e interpreta uma tabela detalhada oficial da CBF."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_events(self, url: str, *, season: int) -> list[tuple[SportsEvent, str]]:
        try:
            response = get_with_retries(
                self._client,
                url,
                headers={"User-Agent": "Fla10-Agents/0.1 (+calendar importer)"},
            )
            response.raise_for_status()

            if len(response.content) > MAX_PDF_BYTES:
                raise CBFSourceError(
                    "O PDF da CBF excede o limite de "
                    f"{MAX_PDF_BYTES // (1024 * 1024)} MB e não foi processado."
                )

            reader = PdfReader(BytesIO(response.content))
            content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except CBFSourceError:
            raise
        except (httpx.HTTPError, OSError, ValueError, PyPdfError) as exc:
            raise CBFSourceError(
                f"Falha ao baixar ou ler o PDF oficial da CBF: {exc}"
            ) from exc

        return parse_cbf_table_text(
            content,
            season=season,
            source_url=url,
        )
