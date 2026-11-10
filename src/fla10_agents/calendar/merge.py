"""Fusão de observações parciais em um evento já registrado."""

from fla10_agents.models import EvidenceSource, SportsEvent

# Campos opcionais da identidade esportiva: quando a nova observação não os
# informa, o valor já conhecido é preservado em vez de ser apagado.
_PRESERVED_WHEN_MISSING = ("season", "stage", "venue")


def _merge_sources(
    previous: list[EvidenceSource],
    observed: list[EvidenceSource],
) -> list[EvidenceSource]:
    """Acumula fontes por URL; a ocorrência mais recente prevalece."""
    merged: dict[str, EvidenceSource] = {}

    for source in (*previous, *observed):
        merged[str(source.url)] = source

    return list(merged.values())


def merge_observation(
    previous: SportsEvent,
    observed: SportsEvent,
) -> SportsEvent:
    """Combina a observação nova com o evento existente, sem perder dados.

    O identificador interno é preservado. Campos opcionais ausentes na
    observação mantêm o valor anterior, e as fontes são somadas em vez de
    substituídas, para que cada evidência continue rastreável.
    """
    updates = {
        field: getattr(previous, field)
        for field in _PRESERVED_WHEN_MISSING
        if getattr(observed, field) is None and getattr(previous, field) is not None
    }

    if observed.starts_at_local is None and previous.starts_at_local is not None:
        # Uma fonte sem data não pode rebaixar um jogo já confirmado.
        updates["starts_at_local"] = previous.starts_at_local
        updates["event_status"] = previous.event_status

    updates["event_id"] = previous.event_id
    updates["sources"] = _merge_sources(previous.sources, observed.sources)

    return observed.model_copy(update=updates)
