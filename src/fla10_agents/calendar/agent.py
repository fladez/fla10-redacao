"""Fluxo de atualização da agenda esportiva com resolução de identidade."""

from dataclasses import dataclass
from enum import StrEnum

from fla10_agents.calendar.comparator import EventDifference, compare_events
from fla10_agents.calendar.merge import merge_observation
from fla10_agents.calendar.repository import (
    CalendarRepository,
    IdentityResolutionStatus,
)
from fla10_agents.models import SportsEvent


class UpdateAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    IDENTITY_UNRESOLVED = "identity_unresolved"


@dataclass(frozen=True, slots=True)
class EventUpdateResult:
    """Resultado do processamento de uma observação de evento."""

    action: UpdateAction
    event_id: str | None
    differences: tuple[EventDifference, ...]
    identity_status: IdentityResolutionStatus
    reason: str | None = None


class CalendarAgent:
    """Processa observações e mantém o registro local de eventos."""

    def __init__(self, repository: CalendarRepository) -> None:
        self.repository = repository

    def process_observation(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
        provider: str | None = None,
        external_id: str | None = None,
    ) -> EventUpdateResult:
        resolution = self.repository.resolve_event_identity(
            event,
            provider=provider,
            external_id=external_id,
        )

        if resolution.status in (
            IdentityResolutionStatus.AMBIGUOUS,
            IdentityResolutionStatus.CONFLICT,
        ):
            return EventUpdateResult(
                action=UpdateAction.IDENTITY_UNRESOLVED,
                event_id=None,
                differences=(),
                identity_status=resolution.status,
                reason=resolution.reason,
            )

        if resolution.status == IdentityResolutionStatus.NEW:
            existing_by_id = self.repository.get_event(event.event_id)

            if existing_by_id is not None:
                return EventUpdateResult(
                    action=UpdateAction.IDENTITY_UNRESOLVED,
                    event_id=None,
                    differences=(),
                    identity_status=IdentityResolutionStatus.CONFLICT,
                    reason=(
                        "O ID interno recebido já pertence a outro evento "
                        "com identidade esportiva incompatível."
                    ),
                )

            self.repository.save_event_and_link_external_id(
                event,
                change_summary=change_summary or "Primeiro registro do evento.",
                provider=provider,
                external_id=external_id,
            )

            return EventUpdateResult(
                action=UpdateAction.CREATED,
                event_id=event.event_id,
                differences=(),
                identity_status=IdentityResolutionStatus.NEW,
            )

        previous = resolution.event
        if previous is None:
            raise RuntimeError("A resolução MATCHED não retornou o evento correspondente.")

        canonical_event = merge_observation(previous, event)
        differences = tuple(compare_events(previous, canonical_event))

        self.repository.save_event_and_link_external_id(
            canonical_event,
            change_summary=change_summary,
            provider=provider,
            external_id=external_id,
        )

        action = UpdateAction.UPDATED if differences else UpdateAction.UNCHANGED

        return EventUpdateResult(
            action=action,
            event_id=previous.event_id,
            differences=differences,
            identity_status=IdentityResolutionStatus.MATCHED,
        )
