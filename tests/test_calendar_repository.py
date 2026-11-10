import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fla10_agents.calendar.repository import (
    SCHEMA_VERSION,
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

def test_transaction_rolls_back_every_write(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        with (
            pytest.raises(RuntimeError, match="interrompe"),
            repository.transaction(),
        ):
            repository.save_event(make_event())
            repository.link_external_id("cbf", "2026:1", "evt-001")
            raise RuntimeError("interrompe a importação")

        assert repository.list_events() == []
        assert repository.get_event_by_external_id("cbf", "2026:1") is None


def test_file_database_uses_wal_and_busy_timeout(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        journal_mode = repository._connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = repository._connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert busy_timeout > 0


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    database = tmp_path / "calendar.db"

    with CalendarRepository(database) as repository:
        assert repository.schema_version == SCHEMA_VERSION

    with CalendarRepository(database) as repository:
        assert repository.schema_version == SCHEMA_VERSION


def test_legacy_database_receives_identity_key_on_open(tmp_path: Path) -> None:
    database = tmp_path / "calendar.db"
    event = make_event()

    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE sports_events (
            event_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO sports_events VALUES (?, ?, ?, ?)",
        (event.event_id, event.model_dump_json(), "2026-11-09T12:00:00+00:00",
         "2026-11-09T12:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    with CalendarRepository(database) as repository:
        assert repository.get_event("evt-001") == event
        resolution = repository.resolve_event_identity(event)

    assert resolution.status.value == "matched"


def test_newer_schema_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "calendar.db"

    connection = sqlite3.connect(database)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    connection.close()

    with pytest.raises(RuntimeError, match="mais novo"):
        CalendarRepository(database)


def test_provider_is_normalized_before_linking(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        event = make_event()
        repository.save_event(event)

        repository.link_external_id(" CBF ", "2026:1", "evt-001")

        assert repository.get_event_by_external_id("cbf", "2026:1") == event
        assert repository.get_event_by_external_id("CBF", " 2026:1 ") == event


def test_run_registry_records_start_and_finish(tmp_path: Path) -> None:
    with CalendarRepository(tmp_path / "calendar.db") as repository:
        run_id = repository.start_run("CBF", "https://cbf.example/tabela.pdf")

        running = repository.list_runs()
        assert running[0]["run_id"] == run_id
        assert running[0]["status"] == "running"
        assert running[0]["provider"] == "cbf"

        repository.finish_run(
            run_id,
            "completed",
            created=3,
            updated=1,
            unchanged=2,
        )

        finished = repository.list_runs(limit=5)
        assert finished[0]["status"] == "completed"
        assert finished[0]["created"] == 3
        assert finished[0]["updated"] == 1
        assert finished[0]["unchanged"] == 2
        assert finished[0]["finished_at"] is not None
