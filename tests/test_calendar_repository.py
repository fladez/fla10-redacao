from datetime import UTC, datetime
from pathlib import Path

import pytest

from fla10_agents.calendar.repository import (
    CalendarRepository,
    EventIdentityConflictError,
)
from fla10_agents.models import EventStatus, SportsEvent


def make_event(
    event_id: str = "evt-001",
    starts_at: datetime = datetime(2026, 11, 10, 19, 0),
    venue: str | None = "Maracanã",
) -> SportsEvent:
    return SportsEvent(
        event_id=event_id,
        sport="futebol",
        category="profissional masculino",
        competition="Campeonato Brasileiro",
        season="2026",
        home_team="Flamengo",
        away_team="Palmeiras",
        starts_at_local=starts_at,
        timezone="America/Sao_Paulo",
        venue=venue,
        event_status=EventStatus.CONFIRMED,
        last_verified_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    )


def test_save_and_retrieve_event(tmp_path: Path) -> None:
    database = tmp_path / "calendar.db"

    with CalendarRepository(database) as repository:
        event = make_event()

        assert repository.save_event(event) is True
        assert repository.get_event("evt-001") == event
        assert repository.list_events() == [event]


def test_unchanged_event_does_not_create_new_version(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event()

        assert repository.save_event(event) is True
        assert repository.save_event(event) is False
        assert len(repository.event_history("evt-001")) == 1


def test_event_update_preserves_previous_version(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event()
        updated = original.model_copy(
            update={
                "starts_at_local": datetime(2026, 11, 11, 20, 0),
                "last_verified_at": datetime(
                    2026, 11, 10, 12, 0, tzinfo=UTC
                ),
            }
        )

        assert repository.save_event(original)
        assert repository.save_event(
            updated,
            change_summary="Partida remarcada para 11 de novembro.",
        )

        history = repository.event_history("evt-001")

        assert len(history) == 2
        assert history[0]["event"] == original
        assert history[1]["event"] == updated
        assert history[1]["change_summary"] == (
            "Partida remarcada para 11 de novembro."
        )
        assert repository.get_event("evt-001") == updated


def test_event_and_history_survive_reopening_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "calendar.db"
    event = make_event()

    with CalendarRepository(database) as repository:
        repository.save_event(event)

    with CalendarRepository(database) as repository:
        assert repository.get_event("evt-001") == event
        assert len(repository.event_history("evt-001")) == 1


def test_external_id_resolves_to_internal_event(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event()
        repository.save_event(event)

        repository.link_external_id("flamengo", "fixture-987", "evt-001")

        assert repository.get_event_by_external_id(
            "flamengo",
            "fixture-987",
        ) == event


def test_external_id_cannot_be_silently_reassigned(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        repository.save_event(make_event("evt-001"))
        repository.save_event(make_event("evt-002"))

        repository.link_external_id("flamengo", "fixture-987", "evt-001")

        with pytest.raises(EventIdentityConflictError):
            repository.link_external_id(
                "flamengo",
                "fixture-987",
                "evt-002",
            )


def test_external_id_requires_existing_internal_event(
    tmp_path: Path,
) -> None:
    with (
        CalendarRepository(tmp_path / "calendar.db") as repository,
        pytest.raises(KeyError, match="Evento interno inexistente"),
    ):
        repository.link_external_id(
            "flamengo",
            "fixture-987",
            "evt-inexistente",
        )


def test_missing_event_returns_none(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        assert repository.get_event("inexistente") is None
        assert repository.get_event_by_external_id(
            "flamengo",
            "inexistente",
        ) is None


def test_audit_timestamp_updates_without_creating_event_version(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event()
        rechecked = original.model_copy(
            update={
                "last_verified_at": datetime(
                    2026, 11, 10, 12, 0, tzinfo=UTC
                )
            }
        )

        assert repository.save_event(original) is True
        assert repository.save_event(rechecked) is False
        assert repository.get_event("evt-001") == rechecked
        assert len(repository.event_history("evt-001")) == 1