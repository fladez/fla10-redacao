import json
import sys
from datetime import UTC, datetime

from fla10_agents.cli import main


def event_payload() -> dict[str, object]:
    return {
        "sport": "futebol",
        "category": "profissional masculino",
        "competition": "Campeonato Brasileiro",
        "season": "2026",
        "stage": "rodada 33",
        "home_team": "Flamengo",
        "away_team": "Palmeiras",
        "starts_at_local": "2026-11-10T19:00:00",
        "timezone": "America/Sao_Paulo",
        "venue": "Maracanã",
        "event_status": "confirmed",
        "sources": [],
        "last_verified_at": datetime(2026, 11, 10, 12, 0, tzinfo=UTC).isoformat(),
    }


def test_calendar_cli_processes_and_lists_event(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "event.json"
    database_path = tmp_path / "calendar.db"
    input_path.write_text(
        json.dumps({
            "provider": "cbf",
            "external_id": "fixture-123",
            "event": event_payload(),
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["fla10", "calendar", "process", "--input", str(input_path),
         "--database", str(database_path)],
    )
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0

    processed = json.loads(capsys.readouterr().out)
    assert processed["action"] == "created"
    assert processed["identity_status"] == "new"

    monkeypatch.setattr(
        sys,
        "argv",
        ["fla10", "calendar", "list", "--database", str(database_path)],
    )
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0

    events = json.loads(capsys.readouterr().out)
    assert len(events) == 1
    assert events[0]["home_team"] == "Flamengo"
