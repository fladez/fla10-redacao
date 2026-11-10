"""Componentes do agente de agenda esportiva."""

from fla10_agents.calendar.agent import (
    CalendarAgent,
    EventUpdateResult,
    UpdateAction,
)
from fla10_agents.calendar.comparator import (
    EventDifference,
    compare_events,
)
from fla10_agents.calendar.repository import (
    CalendarRepository,
    EventIdentityConflictError,
    EventIdentityResolution,
    IdentityResolutionStatus,
)

__all__ = [
    "CalendarAgent",
    "CalendarRepository",
    "EventDifference",
    "EventIdentityConflictError",
    "EventIdentityResolution",
    "EventUpdateResult",
    "IdentityResolutionStatus",
    "UpdateAction",
    "compare_events",
]
