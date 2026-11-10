from datetime import UTC, datetime

import pytest

from fla10_agents.calendar.comparator import (
    EventDifference,
    compare_events,
)
from fla10_agents.models import (
    EventStatus,
    EvidenceSource,
    SportsEvent,
)


def make_event(
    event_id: str = "evt-001",
    starts_at: datetime = datetime(2026, 11, 10, 19, 0),
    venue: str | None = "Maracanã",
    status: EventStatus = EventStatus.CONFIRMED,
    verified_at: datetime = datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    sources: list[EvidenceSource] | None = None,
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
        event_status=status,
        sources=sources or [],
        last_verified_at=verified_at,
    )


def make_source(
    excerpt: str,
    accessed_at: datetime = datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
) -> EvidenceSource:
    return EvidenceSource(
        url="https://www.flamengo.com.br/calendario",
        source_type="official",
        author_or_institution="Flamengo",
        accessed_at=accessed_at,
        supports=["data da partida"],
        supporting_excerpt_or_data=excerpt,
    )


def test_identical_events_have_no_differences() -> None:
    event = make_event()

    assert compare_events(event, event) == []


def test_verification_timestamp_is_not_an_event_change() -> None:
    previous = make_event()
    current = make_event(
        verified_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    )

    assert compare_events(previous, current) == []


def test_source_access_timestamp_is_not_a_source_change() -> None:
    previous = make_event(
        sources=[make_source("Partida às 19h.")]
    )
    current = make_event(
        sources=[
            make_source(
                "Partida às 19h.",
                datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
            )
        ]
    )

    assert compare_events(previous, current) == []


def test_detects_date_and_time_change() -> None:
    previous = make_event()
    current = make_event(
        starts_at=datetime(2026, 11, 11, 20, 0)
    )

    differences = compare_events(previous, current)

    assert len(differences) == 1
    assert differences[0].field == "starts_at_local"
    assert differences[0].previous_value == "2026-11-10T19:00:00"
    assert differences[0].current_value == "2026-11-11T20:00:00"


def test_detects_venue_change() -> None:
    differences = compare_events(
        make_event(),
        make_event(venue="Estádio Nilton Santos"),
    )

    assert differences == [
        EventDifference(
            field="venue",
            previous_value="Maracanã",
            current_value="Estádio Nilton Santos",
        )
    ]


def test_detects_event_status_change() -> None:
    differences = compare_events(
        make_event(),
        make_event(status=EventStatus.POSTPONED),
    )

    assert len(differences) == 1
    assert differences[0].field == "event_status"
    assert differences[0].previous_value == "confirmed"
    assert differences[0].current_value == "postponed"


def test_detects_source_content_change() -> None:
    previous = make_event(
        sources=[make_source("Partida às 19h.")]
    )
    current = make_event(
        sources=[make_source("Partida às 20h.")]
    )

    differences = compare_events(previous, current)

    assert len(differences) == 1
    assert differences[0].field == "sources"


def test_detects_multiple_changes() -> None:
    previous = make_event()
    current = make_event(
        starts_at=datetime(2026, 11, 11, 20, 0),
        venue="Estádio Nilton Santos",
        status=EventStatus.POSTPONED,
    )

    differences = compare_events(previous, current)

    assert {difference.field for difference in differences} == {
        "starts_at_local",
        "venue",
        "event_status",
    }


def test_rejects_comparison_between_different_events() -> None:
    with pytest.raises(ValueError, match="mesmo event_id"):
        compare_events(
            make_event("evt-001"),
            make_event("evt-002"),
        )
