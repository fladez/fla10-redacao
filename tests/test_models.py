import pytest
from pydantic import ValidationError

from fla10_agents.models import EventStatus, SportsEvent


def valid_event() -> dict:
    return {
        "event_id": "flamengo-gremio-2026-11-04",
        "sport": "football",
        "category": "mens_team_first_team",
        "competition": "Brasileirão",
        "season": "2026",
        "stage": "34ª rodada",
        "home_team": "Flamengo",
        "away_team": "Grêmio",
        "starts_at_local": "2026-11-04T19:30:00",
        "timezone": "America/Sao_Paulo",
        "venue": "Maracanã",
        "event_status": EventStatus.CONFIRMED,
        "sources": [],
        "last_verified_at": "2026-11-03T18:00:00Z",
    }


def test_event_accepts_local_time_with_explicit_iana_zone() -> None:
    event = SportsEvent.model_validate(valid_event())
    assert event.timezone == "America/Sao_Paulo"
    assert event.starts_at_local.tzinfo is None


def test_event_rejects_unknown_timezone() -> None:
    data = valid_event()
    data["timezone"] = "America/Unknown_City"
    with pytest.raises(ValidationError):
        SportsEvent.model_validate(data)


def test_event_rejects_offset_in_local_clock_field() -> None:
    data = valid_event()
    data["starts_at_local"] = "2026-11-04T19:30:00-03:00"
    with pytest.raises(ValidationError):
        SportsEvent.model_validate(data)


def test_event_requires_timezone_on_verification_timestamp() -> None:
    data = valid_event()
    data["last_verified_at"] = "2026-11-03T18:00:00"
    with pytest.raises(ValidationError):
        SportsEvent.model_validate(data)
