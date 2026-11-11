import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from fla10_agents.cli import main

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

PAINEL = """# Painel de Pautas

## Pautas mencionadas para 10 de novembro de 2026

### Flamengo ajusta defesa para o clássico
- **Estado:** aprovada.
- **Janela:** 2026-11-10.
- **Foco:** mudanças na defesa.
"""

RESERVAS = """# Projetos e Pautas Reservadas

## Projetos

### Projeto sobre a base do Flamengo
- **Estado:** ideia.
- **Objetivo:** acompanhar a transição da base.
"""


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    pautas = vault / "06 - Pautas"
    pautas.mkdir(parents=True)
    (pautas / "Painel de Pautas.md").write_text(PAINEL, encoding="utf-8")
    (pautas / "Projetos e Pautas Reservadas.md").write_text(RESERVAS, encoding="utf-8")
    return vault


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


def write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({
            "provider": "teste",
            "external_id": "evt-1",
            "event": {
                "sport": "futebol",
                "category": "profissional",
                "competition": "Brasileirão Série A",
                "season": "2026",
                "stage": "Rodada 38",
                "home_team": "Flamengo",
                "away_team": "Palmeiras",
                "starts_at_local": "2026-11-12T21:30:00",
                "timezone": "America/Sao_Paulo",
                "venue": "Maracanã",
                "event_status": "confirmed",
                "sources": [],
                "last_verified_at": NOW.isoformat(),
            },
        }),
        encoding="utf-8",
    )

    signal_path = tmp_path / "signals.json"
    signal_path.write_text(
        json.dumps({
            "signals": [{
                "provider": "teste",
                "external_id": "sig-1",
                "title": "Flamengo confirma retorno de jogador",
                "published_at": NOW.isoformat(),
                "teams": ["Flamengo"],
            }]
        }),
        encoding="utf-8",
    )

    return event_path, signal_path


def test_vault_commands_read_local_notes(tmp_path, monkeypatch, capsys) -> None:
    vault = make_vault(tmp_path)

    code, out, _ = run_cli(
        monkeypatch,
        ["vault", "status", "--vault", str(vault)],
        capsys,
    )

    assert code == 0
    status = json.loads(out)
    assert status["pautas"] == 2
    assert status["by_kind"] == {"mencionada": 1, "projeto": 1}

    code, out, _ = run_cli(
        monkeypatch,
        ["pautas", "parse", "--vault", str(vault)],
        capsys,
    )

    assert code == 0
    pautas = json.loads(out)
    assert [pauta["title"] for pauta in pautas] == [
        "Flamengo ajusta defesa para o clássico",
        "Projeto sobre a base do Flamengo",
    ]


def test_pautas_pipeline_and_dossie_flow(tmp_path, monkeypatch, capsys) -> None:
    vault = make_vault(tmp_path)
    event_path, signal_path = write_inputs(tmp_path)
    calendar_db = tmp_path / "calendar.db"
    editorial_db = tmp_path / "editorial.db"

    code, out, err = run_cli(
        monkeypatch,
        ["calendar", "process", "--input", str(event_path),
         "--database", str(calendar_db)],
        capsys,
    )
    assert code == 0, err

    code, out, err = run_cli(
        monkeypatch,
        ["sinais", "add", "--input", str(signal_path),
         "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    assert json.loads(out)["created"] == 1

    code, out, err = run_cli(
        monkeypatch,
        ["pipeline", "run", "--calendar-database", str(calendar_db),
         "--database", str(editorial_db), "--vault", str(vault)],
        capsys,
    )
    assert code == 0, err
    pipeline = json.loads(out)
    assert pipeline["created"] == 3

    code, out, err = run_cli(
        monkeypatch,
        ["pautas", "list", "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    proposals = json.loads(out)
    assert "Projeto sobre a base do Flamengo" in {
        item["title"] for item in proposals
    }
    proposal_id = proposals[0]["proposal_id"]

    code, out, err = run_cli(
        monkeypatch,
        ["pautas", "approve", proposal_id, "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    assert json.loads(out)["decision"] == "approved"

    claims_path = tmp_path / "claims.json"
    claims_path.write_text(
        json.dumps({
            "claims": [{
                "claim_id": "c1",
                "claim_text": "O jogo está marcado para 12 de novembro.",
                "classification": "confirmed",
                "evidence": [{
                    "url": "https://example.com/tabela",
                    "source_type": "tabela oficial",
                    "author_or_institution": "CBF",
                    "accessed_at": NOW.isoformat(),
                    "supports": ["data"],
                }],
            }]
        }),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        monkeypatch,
        ["dossie", "build", proposal_id, "--claims", str(claims_path),
         "--contradiction", "Horário divergente.", "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    dossier = json.loads(out)
    assert dossier["proposal_id"] == proposal_id
    assert dossier["contradictions"] == ["Horário divergente."]

    code, out, err = run_cli(
        monkeypatch,
        ["dossie", "mostrar", proposal_id, "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    gravado = json.loads(out)
    assert gravado["proposal_id"] == proposal_id
    assert gravado["contradictions"] == ["Horário divergente."]
    assert gravado["claims"]

    code, out, err = run_cli(
        monkeypatch,
        ["publicacoes", "add", "--title", "Flamengo x Palmeiras: onde assistir",
         "--published-at", "2026-11-11T10:00:00-03:00",
         "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err

    code, out, err = run_cli(
        monkeypatch,
        ["publicacoes", "list", "--database", str(editorial_db)],
        capsys,
    )
    assert code == 0, err
    assert json.loads(out) == ["Flamengo x Palmeiras: onde assistir"]


def test_invalid_signal_returns_error(tmp_path, monkeypatch, capsys) -> None:
    signal_path = tmp_path / "signals.json"
    signal_path.write_text(json.dumps([{"title": "Sem provedor"}]), encoding="utf-8")

    code, _, err = run_cli(
        monkeypatch,
        ["sinais", "add", "--input", str(signal_path),
         "--database", str(tmp_path / "editorial.db")],
        capsys,
    )

    assert code == 1
    assert "provider" in err


def test_publication_requires_timezone(tmp_path, monkeypatch, capsys) -> None:
    code, _, err = run_cli(
        monkeypatch,
        ["publicacoes", "add", "--title", "Matéria",
         "--published-at", "2026-11-11T10:00:00",
         "--database", str(tmp_path / "editorial.db")],
        capsys,
    )

    assert code == 1
    assert "fuso horário" in err
