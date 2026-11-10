"""Comparação determinística entre versões de eventos esportivos."""

import json
from dataclasses import dataclass
from typing import Any

from fla10_agents.models import SportsEvent


@dataclass(frozen=True, slots=True)
class EventDifference:
    """Representa a alteração de um campo entre duas versões."""

    field: str
    previous_value: Any
    current_value: Any


def _normalized_sources(event: SportsEvent) -> list[str]:
    """Normaliza fontes sem considerar o horário em que foram consultadas."""
    normalized = []

    for source in event.sources:
        data = source.model_dump(mode="json", exclude={"accessed_at"})
        normalized.append(
            json.dumps(data, ensure_ascii=False, sort_keys=True)
        )

    return sorted(normalized)


def compare_events(
    previous: SportsEvent,
    current: SportsEvent,
) -> list[EventDifference]:
    """Identifica diferenças relevantes entre duas versões do mesmo evento.

    Horários de verificação e de acesso às fontes são metadados de auditoria,
    não alterações do evento.
    """
    if previous.event_id != current.event_id:
        raise ValueError(
            "A comparação exige eventos com o mesmo event_id."
        )

    previous_data = previous.model_dump(mode="json")
    current_data = current.model_dump(mode="json")

    ignored_fields = {"event_id", "last_verified_at", "sources"}
    differences = []

    for field in previous_data:
        if field in ignored_fields:
            continue

        old_value = previous_data[field]
        new_value = current_data[field]

        if old_value != new_value:
            differences.append(
                EventDifference(
                    field=field,
                    previous_value=old_value,
                    current_value=new_value,
                )
            )

    old_sources = _normalized_sources(previous)
    new_sources = _normalized_sources(current)

    if old_sources != new_sources:
        differences.append(
            EventDifference(
                field="sources",
                previous_value=old_sources,
                current_value=new_sources,
            )
        )

    return differences
