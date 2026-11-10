"""Parser das notas de pautas do vault editorial."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

PAUTA_FILES = (
    "06 - Pautas/Painel de Pautas.md",
    "06 - Pautas/Projetos e Pautas Reservadas.md",
)

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_HEADING_DATE = re.compile(r"(\d{1,2})\s+de\s+([a-zçãéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_FIELD = re.compile(r"^-\s+\*\*(?P<name>[^*]+):\*\*\s*(?P<value>.*)$")

_STATUS_KEYWORDS = (
    ("publicad", "publicada"),
    ("aprovad", "aprovada"),
    ("reservad", "reservada"),
    ("cancelad", "cancelada"),
    ("adiad", "adiada"),
    ("em apuração", "em_apuracao"),
    ("em apuracao", "em_apuracao"),
    ("em redação", "em_redacao"),
    ("em redacao", "em_redacao"),
    ("em revisão", "em_revisao"),
    ("em revisao", "em_revisao"),
    ("concluíd", "concluida"),
    ("concluid", "concluida"),
    ("ideia", "ideia"),
)

KIND_BY_SECTION = (
    ("reservad", "reservada"),
    ("projeto", "projeto"),
    ("mencionad", "mencionada"),
)


@dataclass(frozen=True, slots=True)
class Pauta:
    title: str
    status: str
    kind: str
    window: date | None
    fields: Mapping[str, str] = field(default_factory=dict)
    source: str = ""

    @property
    def context_text(self) -> str:
        """Texto usado na comparação de redundância."""
        values = [self.title, *self.fields.values()]
        return " ".join(value for value in values if value)


def _parse_date(value: str) -> date | None:
    iso = _ISO_DATE.search(value)
    if iso is not None:
        iso_year, iso_month, iso_day = (int(part) for part in iso.groups())
        try:
            return date(iso_year, iso_month, iso_day)
        except ValueError:
            return None

    long_form = _HEADING_DATE.search(value)
    if long_form is not None:
        long_day, month_name, long_year = long_form.groups()
        month = _MONTHS.get(month_name.casefold())
        if month is None:
            return None
        try:
            return date(int(long_year), month, int(long_day))
        except ValueError:
            return None

    return None


def _normalize_status(value: str) -> str:
    text = value.casefold()
    for keyword, status in _STATUS_KEYWORDS:
        if keyword in text:
            return status
    return "indefinido"


def _kind_for(section: str) -> str:
    text = section.casefold()
    for keyword, kind in KIND_BY_SECTION:
        if keyword in text:
            return kind
    return "mencionada"


def parse_pautas(content: str, source: str) -> list[Pauta]:
    """Extrai pautas de uma nota Markdown do vault."""
    pautas: list[Pauta] = []
    section = ""
    section_date: date | None = None
    current_title: str | None = None
    current_fields: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_title, current_fields
        if current_title is None:
            return

        status = _normalize_status(current_fields.get("Estado", ""))
        window = _parse_date(current_fields.get("Janela", "")) or section_date

        pautas.append(
            Pauta(
                title=current_title.strip(),
                status=status,
                kind=_kind_for(section),
                window=window,
                fields=dict(current_fields),
                source=source,
            )
        )
        current_title = None
        current_fields = {}

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        if line.startswith("## "):
            flush()
            section = line[3:].strip()
            section_date = _parse_date(section)
            continue

        if line.startswith("### "):
            flush()
            current_title = line[4:].strip()
            current_fields = {}
            continue

        if current_title is None:
            continue

        match = _FIELD.match(line.strip())
        if match is not None:
            name = match.group("name").strip()
            current_fields[name] = match.group("value").strip()

    flush()
    return [pauta for pauta in pautas if pauta.title]


def parse_pauta_documents(files: Mapping[str, str]) -> list[Pauta]:
    """Converte os arquivos do vault em uma lista única de pautas.

    A mesma pauta aparece no painel e no registro de reservas; a primeira
    ocorrência é mantida para não duplicar a comparação de redundância.
    """
    pautas: list[Pauta] = []
    seen: set[tuple[str, str | None]] = set()

    for path, content in files.items():
        for pauta in parse_pautas(content, path):
            window = pauta.window.isoformat() if pauta.window else None
            key = (pauta.title.casefold().strip(), window)
            if key in seen:
                continue
            seen.add(key)
            pautas.append(pauta)

    return pautas
