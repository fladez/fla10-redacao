"""Leitor da tabela detalhada oficial da CBF em PDF."""
from __future__ import annotations
import re
from datetime import UTC, datetime
from io import BytesIO
import httpx
from pypdf import PdfReader
from fla10_agents.models import EvidenceSource, EventStatus, SportsEvent

class CBFSourceError(RuntimeError):
    """Falha ao consultar ou interpretar a tabela oficial da CBF."""

_UFS = "AC AL AP AM BA CE DF GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
_ROW = re.compile(r"^\s*(\d{3})\s+(\d{1,2})[ªº]?\s+(\d{2}/\d{2})\s+\w+\s+(\d{2}:\d{2})\s+(.+?)\s+x\s+(.+?)\s*$", re.IGNORECASE)
_UF = re.compile(r"\b(" + "|".join(_UFS) + r")\b")

def _split_team_and_remainder(value: str) -> tuple[str, str]:
    match = _UF.search(value)
    if match is None:
        raise CBFSourceError(f"Não foi possível identificar a UF na linha: {value}")
    return value[:match.end()].strip(), value[match.end():].strip()

def parse_cbf_table_text(content: str, *, season: int, source_url: str, accessed_at: datetime | None = None) -> list[tuple[SportsEvent, str]]:
    """Extrai somente partidas do Flamengo, preservando o código oficial do jogo."""
    verified_at = accessed_at or datetime.now(UTC)
    source = EvidenceSource(url=source_url, source_type="documento oficial de competição", author_or_institution="Confederação Brasileira de Futebol", accessed_at=verified_at, supports=["data", "horário", "mandante", "visitante", "estádio", "competição"], limitations="Tabela detalhada do Campeonato Brasileiro Série A; sujeita a retificações da CBF.")
    results: list[tuple[SportsEvent, str]] = []
    for line in content.splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue
        external_id, round_number, date_text, time_text, home_raw, away_raw = match.groups()
        home_team, _ = _split_team_and_remainder(home_raw)
        away_team, venue = _split_team_and_remainder(away_raw)
        venue = re.sub(r"\s+(?:\d+\s*)+$", "", venue).strip()
        home_name = re.sub(r"\s+(?:" + "|".join(_UFS) + r")$", "", home_team).strip()
        away_name = re.sub(r"\s+(?:" + "|".join(_UFS) + r")$", "", away_team).strip()
        if "flamengo" not in (home_name + " " + away_name).casefold():
            continue
        day, month = (int(part) for part in date_text.split("/"))
        starts_at = datetime(season, month, day, int(time_text[:2]), int(time_text[3:]))
        event = SportsEvent(sport="futebol", category="profissional masculino", competition="Campeonato Brasileiro Série A", season=str(season), stage=f"rodada {round_number}", home_team=home_name, away_team=away_name, starts_at_local=starts_at, timezone="America/Sao_Paulo", venue=venue or None, event_status=EventStatus.CONFIRMED, sources=[source], last_verified_at=verified_at)
        results.append((event, external_id))
    if not results:
        raise CBFSourceError("A tabela foi lida, mas nenhuma partida do Flamengo foi encontrada. A importação foi interrompida sem gravar eventos.")
    return results

class CBFCalendarSource:
    """Baixa e interpreta uma tabela detalhada oficial da CBF."""
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self._owns_client = client is None
    def close(self) -> None:
        if self._owns_client:
            self._client.close()
    def __enter__(self) -> CBFCalendarSource:
        return self
    def __exit__(self, *_: object) -> None:
        self.close()
    def fetch_events(self, url: str, *, season: int) -> list[tuple[SportsEvent, str]]:
        try:
            response = self._client.get(url, headers={"User-Agent": "Fla10-Agents/0.1 (+calendar importer)"})
            response.raise_for_status()
            reader = PdfReader(BytesIO(response.content))
            content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise CBFSourceError(f"Falha ao baixar ou ler o PDF oficial da CBF: {exc}") from exc
        return parse_cbf_table_text(content, season=season, source_url=url)
