import json
import sys
from datetime import UTC, datetime
from typing import Self

import pytest

from fla10_agents.cli import main
from fla10_agents.models import SportsEvent


def make_event(
    home_team: str = "Flamengo",
    away_team: str = "Palmeiras",
    event_id: str | None = None,
) -> SportsEvent:
    data = {
        "sport": "futebol",
        "category": "profissional masculino",
        "competition": "Campeonato Brasileiro",
        "season": "2026",
        "stage": "rodada 33",
        "home_team": home_team,
        "away_team": away_team,
        "starts_at_local": "2026-11-10T19:00:00",
        "timezone": "America/Sao_Paulo",
        "venue": "Maracanã",
        "event_status": "confirmed",
        "last_verified_at": datetime(2026, 11, 10, 12, 0, tzinfo=UTC).isoformat(),
    }
    if event_id is not None:
        data["event_id"] = event_id
    return SportsEvent.model_validate(data)


class StubSource:
    def __init__(self, observations) -> None:
        self.observations = observations

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch_events(self, url: str, *, season: int):
        return self.observations


def run_cli(monkeypatch, argv: list[str], capsys) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["fla10", *argv])
    try:
        main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    else:  # pragma: no cover - main sempre encerra com SystemExit
        code = 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_sync_cbf_imports_events_and_records_run(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "calendar.db"
    observations = [(make_event(event_id="evt-001"), "2026:1")]

    monkeypatch.setattr("fla10_agents.cli.CBFCalendarSource", lambda: StubSource(observations))

    code, out, _ = run_cli(
        monkeypatch,
        [
            "calendar", "sync-cbf",
            "--url", "https://cbf.example/tabela.pdf",
            "--season", "2026",
            "--database", str(database),
        ],
        capsys,
    )

    payload = json.loads(out)
    assert code == 0
    assert payload["status"] == "completed"
    assert payload["totals"]["created"] == 1
    assert payload["totals"]["identity_unresolved"] == 0

    code, out, _ = run_cli(
        monkeypatch,
        ["calendar", "runs", "--database", str(database)],
        capsys,
    )

    runs = json.loads(out)
    assert code == 0
    assert runs[0]["status"] == "completed"
    assert runs[0]["source_url"] == "https://cbf.example/tabela.pdf"
    assert runs[0]["created"] == 1


def test_sync_cbf_conflict_returns_error_and_keeps_event(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "calendar.db"
    original = make_event(event_id="evt-001")
    observations = [(make_event(home_team="Fluminense"), "2026:1")]

    from fla10_agents.calendar import CalendarRepository

    with CalendarRepository(database) as repository:
        repository.save_event(original)
        repository.link_external_id("cbf", "2026:1", "evt-001")

    monkeypatch.setattr("fla10_agents.cli.CBFCalendarSource", lambda: StubSource(observations))

    code, out, _ = run_cli(
        monkeypatch,
        [
            "calendar", "sync-cbf",
            "--url", "https://cbf.example/tabela.pdf",
            "--season", "2026",
            "--database", str(database),
        ],
        capsys,
    )

    payload = json.loads(out)
    assert code == 1
    assert payload["status"] == "completed_with_conflicts"
    assert payload["totals"]["identity_unresolved"] == 1

    code, out, _ = run_cli(
        monkeypatch,
        ["calendar", "list", "--database", str(database)],
        capsys,
    )

    events = json.loads(out)
    assert code == 0
    assert len(events) == 1
    assert events[0]["home_team"] == "Flamengo"


def test_sync_cbf_rolls_back_all_events_on_failure(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "calendar.db"
    observations = [
        (make_event(event_id="evt-001"), "2026:1"),
        (make_event(event_id="evt-002", away_team="Santos"), "2026:2"),
    ]

    from fla10_agents.calendar.agent import CalendarAgent as RealAgent

    class FailingAgent(RealAgent):
        calls = 0

        def process_observation(self, *args, **kwargs):
            FailingAgent.calls += 1
            if FailingAgent.calls == 2:
                raise RuntimeError("falha simulada no meio da importação")
            return super().process_observation(*args, **kwargs)

    monkeypatch.setattr("fla10_agents.cli.CBFCalendarSource", lambda: StubSource(observations))
    monkeypatch.setattr("fla10_agents.cli.CalendarAgent", FailingAgent)

    with pytest.raises(RuntimeError, match="falha simulada"):
        run_cli(
            monkeypatch,
            [
                "calendar", "sync-cbf",
                "--url", "https://cbf.example/tabela.pdf",
                "--season", "2026",
                "--database", str(database),
            ],
            capsys,
        )

    from fla10_agents.calendar import CalendarRepository

    with CalendarRepository(database) as repository:
        assert repository.list_events() == []
        runs = repository.list_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "failed"
        assert runs[0]["error"] == "RuntimeError"


def test_process_reports_invalid_payload_without_traceback(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    input_path = tmp_path / "evento.json"
    input_path.write_text("[]", encoding="utf-8")

    code, _, err = run_cli(
        monkeypatch,
        [
            "calendar", "process",
            "--input", str(input_path),
            "--database", str(tmp_path / "calendar.db"),
        ],
        capsys,
    )

    assert code == 1
    assert err.startswith("Erro:")
    assert "Traceback" not in err


def test_default_database_path_uses_environment(
    monkeypatch,
    tmp_path,
) -> None:
    from fla10_agents.cli import default_database_path

    configured = tmp_path / "custom.db"
    monkeypatch.setenv("FLA10_DATABASE", str(configured))

    assert default_database_path() == str(configured)


def test_default_database_path_falls_back_to_project_root(monkeypatch, tmp_path) -> None:
    from fla10_agents.cli import default_database_path

    monkeypatch.delenv("FLA10_DATABASE", raising=False)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert default_database_path() == str(tmp_path / "data" / "calendar.db")


def test_calendar_process_does_not_write_database_on_invalid_json(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    input_path = tmp_path / "evento.json"
    input_path.write_text("{}", encoding="utf-8")
    database = tmp_path / "calendar.db"

    code, _, err = run_cli(
        monkeypatch,
        [
            "calendar", "process",
            "--input", str(input_path),
            "--database", str(database),
        ],
        capsys,
    )

    assert code == 1
    assert "Erro:" in err
    assert not database.exists()
