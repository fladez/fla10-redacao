from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from fla10_agents.calendar import (
    CalendarRepository,
    IdentityResolutionStatus,
)
from fla10_agents.models import EventStatus, SportsEvent


def make_event(
    event_id: str | None = None,
    starts_at: datetime = datetime(2026, 11, 10, 19, 0),
    home_team: str = "Flamengo",
    away_team: str = "Palmeiras",
    stage: str | None = "rodada 33",
) -> SportsEvent:
    event_data = {
        "sport": "futebol",
        "category": "profissional masculino",
        "competition": "Campeonato Brasileiro",
        "season": "2026",
        "stage": stage,
        "home_team": home_team,
        "away_team": away_team,
        "starts_at_local": starts_at,
        "timezone": "America/Sao_Paulo",
        "venue": "Maracanã",
        "event_status": EventStatus.CONFIRMED,
        "last_verified_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    }
    if event_id is not None:
        event_data["event_id"] = event_id

    return SportsEvent.model_validate(event_data)


def test_external_id_resolves_existing_event(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event("evt-001")
        repository.save_event(event)
        repository.link_external_id("cbf", "fixture-123", "evt-001")

        result = repository.resolve_event_identity(
            event,
            provider="cbf",
            external_id="fixture-123",
        )

        assert result.status == IdentityResolutionStatus.MATCHED
        assert result.event == event


def test_unique_match_does_not_link_external_id_during_resolution(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event("evt-001")
        repository.save_event(event)

        result = repository.resolve_event_identity(
            event,
            provider="flamengo",
            external_id="partida-456",
        )

        assert result.status == IdentityResolutionStatus.MATCHED
        assert result.event == event
        assert repository.get_event_by_external_id("flamengo", "partida-456") is None


def test_no_candidate_returns_new_without_creating_event(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        observed = make_event("evt-observed")

        result = repository.resolve_event_identity(
            observed,
            provider="cbf",
            external_id="fixture-789",
        )

        assert result.status == IdentityResolutionStatus.NEW
        assert result.event is None
        assert repository.get_event("evt-observed") is None
        assert repository.get_event_by_external_id("cbf", "fixture-789") is None


def test_multiple_candidates_return_ambiguous(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        repository.save_event(make_event("evt-001"))
        repository.save_event(make_event("evt-002"))

        result = repository.resolve_event_identity(
            make_event("evt-observed"),
            provider="cbf",
            external_id="fixture-999",
        )

        assert result.status == IdentityResolutionStatus.AMBIGUOUS
        assert result.event is None
        assert {event.event_id for event in result.candidates} == {
            "evt-001",
            "evt-002",
        }
        assert repository.get_event_by_external_id("cbf", "fixture-999") is None


def test_known_external_id_with_incompatible_teams_returns_conflict(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event("evt-001")
        repository.save_event(original)
        repository.link_external_id("cbf", "fixture-123", "evt-001")

        incompatible = make_event(
            "evt-observed",
            home_team="Fluminense",
            away_team="Palmeiras",
        )

        result = repository.resolve_event_identity(
            incompatible,
            provider="cbf",
            external_id="fixture-123",
        )

        assert result.status == IdentityResolutionStatus.CONFLICT
        assert result.event == original
        assert repository.get_event("evt-001") == original


def test_rescheduled_event_keeps_internal_identity(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event("evt-001")
        repository.save_event(original)
        repository.link_external_id("cbf", "fixture-123", "evt-001")

        rescheduled = make_event(
            "evt-observed",
            starts_at=datetime(2026, 11, 12, 21, 30),
        )

        result = repository.resolve_event_identity(
            rescheduled,
            provider="cbf",
            external_id="fixture-123",
        )

        assert result.status == IdentityResolutionStatus.MATCHED
        assert result.event.event_id == "evt-001"
        assert result.event.starts_at_local == original.starts_at_local


def test_team_identity_normalizes_case_and_whitespace(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event("evt-001")
        repository.save_event(original)

        observation = make_event(
            "evt-observed",
            home_team="  FLAMENGO  ",
            away_team=" Palmeiras ",
        )

        result = repository.resolve_event_identity(observation)

        assert result.status == IdentityResolutionStatus.MATCHED
        assert result.event == original


def test_different_teams_are_not_matched(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        repository.save_event(make_event("evt-001"))

        observation = make_event(
            "evt-observed",
            home_team="Fluminense",
        )

        result = repository.resolve_event_identity(observation)

        assert result.status == IdentityResolutionStatus.NEW
        assert result.event is None


def test_different_known_stages_are_not_matched(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        repository.save_event(make_event("evt-001", stage="rodada 33"))

        observation = make_event(
            "evt-observed",
            stage="rodada 34",
        )

        result = repository.resolve_event_identity(observation)

        assert result.status == IdentityResolutionStatus.NEW
        assert result.event is None


def test_missing_stage_with_multiple_stage_candidates_is_ambiguous(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        repository.save_event(make_event("evt-001", stage="rodada 33"))
        repository.save_event(make_event("evt-002", stage="rodada 34"))

        observation = make_event("evt-observed", stage=None)

        result = repository.resolve_event_identity(observation)

        assert result.status == IdentityResolutionStatus.AMBIGUOUS
        assert {event.event_id for event in result.candidates} == {"evt-001", "evt-002"}


@pytest.mark.parametrize(
    ("provider", "external_id"),
    [
        ("cbf", None),
        (None, "fixture-123"),
        ("", "fixture-123"),
        ("   ", "fixture-123"),
        ("cbf", ""),
        ("cbf", "   "),
    ],
)
def test_invalid_external_identity_arguments_raise_value_error(
    tmp_path: Path,
    provider: str | None,
    external_id: str | None,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository, pytest.raises(ValueError):
        repository.resolve_event_identity(
            make_event("evt-observed"),
            provider=provider,
            external_id=external_id,
        )


def test_identity_resolution_without_external_id_is_allowed(
    tmp_path: Path,
) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event("evt-001")
        repository.save_event(event)

        result = repository.resolve_event_identity(event)

        assert result.status == IdentityResolutionStatus.MATCHED
        assert result.event == event


def test_new_events_receive_distinct_valid_uuids() -> None:
    first = make_event()
    second = make_event()

    UUID(first.event_id)
    UUID(second.event_id)

    assert first.event_id != second.event_id


def test_explicit_legacy_event_id_survives_serialization() -> None:
    original = make_event("legacy-event-001")

    restored = SportsEvent.model_validate_json(original.model_dump_json())

    assert restored.event_id == "legacy-event-001"
    assert restored == original


def test_identity_ignores_case_accents_and_extra_spaces(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        original = make_event("evt-001", home_team="São Paulo", away_team="Flamengo")
        repository.save_event(original)

        observation = make_event(
            home_team="  sao   paulo ",
            away_team="flamengo",
        )

        result = repository.resolve_event_identity(observation)

    assert result.status == IdentityResolutionStatus.MATCHED
    assert result.event is not None
    assert result.event.event_id == "evt-001"
