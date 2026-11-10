from datetime import UTC, datetime
from pathlib import Path

from fla10_agents.calendar import (
    CalendarAgent,
    CalendarRepository,
    UpdateAction,
)
from fla10_agents.models import EventStatus, SportsEvent


def make_event(
    starts_at: datetime = datetime(2026, 11, 10, 19, 0),
    status: EventStatus = EventStatus.CONFIRMED,
    verified_at: datetime = datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
) -> SportsEvent:
    return SportsEvent(
        event_id="evt-001",
        sport="futebol",
        category="profissional masculino",
        competition="Campeonato Brasileiro",
        season="2026",
        home_team="Flamengo",
        away_team="Palmeiras",
        starts_at_local=starts_at,
        timezone="America/Sao_Paulo",
        venue="Maracanã",
        event_status=status,
        last_verified_at=verified_at,
    )


def test_first_observation_creates_event(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)

        result = agent.process_observation(make_event())

        assert result.action == UpdateAction.CREATED
        assert result.event_id == "evt-001"
        assert result.differences == ()
        assert repository.get_event("evt-001") == make_event()


def test_changed_observation_updates_event_and_reports_differences(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        agent.process_observation(make_event())

        updated = make_event(
            starts_at=datetime(2026, 11, 11, 20, 0),
            status=EventStatus.POSTPONED,
        )
        result = agent.process_observation(
            updated,
            change_summary="Partida adiada e remarcada.",
        )

        assert result.action == UpdateAction.UPDATED
        assert {item.field for item in result.differences} == {
            "starts_at_local",
            "event_status",
        }
        assert repository.get_event("evt-001") == updated
        assert len(repository.event_history("evt-001")) == 2


def test_repeated_observation_is_unchanged(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        event = make_event()
        agent.process_observation(event)

        result = agent.process_observation(event)

        assert result.action == UpdateAction.UNCHANGED
        assert result.differences == ()
        assert len(repository.event_history("evt-001")) == 1


def test_reverification_updates_audit_without_event_change(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        agent.process_observation(make_event())

        rechecked = make_event(verified_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
        result = agent.process_observation(rechecked)

        assert result.action == UpdateAction.UNCHANGED
        assert result.differences == ()
        assert repository.get_event("evt-001") == rechecked
        assert len(repository.event_history("evt-001")) == 1


def test_matching_observation_uses_existing_internal_id(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        original = make_event()
        repository.save_event(original)

        observation = make_event(
            starts_at=datetime(2026, 11, 11, 20, 0),
        ).model_copy(update={"event_id": "source-event-456"})

        result = agent.process_observation(observation)

        assert result.action == UpdateAction.UPDATED
        assert result.event_id == "evt-001"
        assert result.identity_status.value == "matched"
        assert repository.get_event("evt-001").starts_at_local == datetime(2026, 11, 11, 20, 0)
        assert repository.get_event("source-event-456") is None
        assert len(repository.event_history("evt-001")) == 2


def test_ambiguous_identity_does_not_write_event(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        first = make_event()
        second = make_event().model_copy(update={"event_id": "evt-002"})
        repository.save_event(first)
        repository.save_event(second)

        observation = make_event().model_copy(update={"event_id": "source-event-789"})

        result = agent.process_observation(observation)

        assert result.action == UpdateAction.IDENTITY_UNRESOLVED
        assert result.event_id is None
        assert result.identity_status.value == "ambiguous"
        assert repository.get_event("source-event-789") is None
        assert len(repository.event_history("evt-001")) == 1
        assert len(repository.event_history("evt-002")) == 1


def test_conflicting_external_identity_does_not_update_event(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        original = make_event()
        repository.save_event(original)
        repository.link_external_id("cbf", "fixture-123", "evt-001")

        observation = make_event().model_copy(
            update={
                "event_id": "source-event-123",
                "home_team": "Fluminense",
            }
        )

        result = agent.process_observation(
            observation,
            provider="cbf",
            external_id="fixture-123",
        )

        assert result.action == UpdateAction.IDENTITY_UNRESOLVED
        assert result.event_id is None
        assert result.identity_status.value == "conflict"
        assert repository.get_event("evt-001") == original
        assert repository.get_event("source-event-123") is None
        assert len(repository.event_history("evt-001")) == 1


def test_new_event_with_external_id_is_saved_and_linked(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        observation = make_event().model_copy(update={"event_id": "evt-new"})

        result = agent.process_observation(
            observation,
            provider="cbf",
            external_id="fixture-new",
        )

        assert result.action == UpdateAction.CREATED
        assert result.event_id == "evt-new"
        assert result.identity_status.value == "new"
        assert repository.get_event("evt-new") == observation
        assert repository.get_event_by_external_id("cbf", "fixture-new") == observation


def test_internal_id_collision_does_not_overwrite_another_event(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        agent = CalendarAgent(repository)
        original = make_event()
        repository.save_event(original)

        incompatible = make_event().model_copy(update={"home_team": "Fluminense"})

        result = agent.process_observation(incompatible)

        assert result.action == UpdateAction.IDENTITY_UNRESOLVED
        assert result.event_id is None
        assert result.identity_status.value == "conflict"
        assert result.reason is not None
        assert repository.get_event("evt-001") == original
        assert len(repository.event_history("evt-001")) == 1
