"""Comandos de diagnóstico e avaliação para o MVP."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from fla10_agents.calendar import CalendarAgent, CalendarRepository
from fla10_agents.calendar.cbf_source import CBFCalendarSource, CBFSourceError
from fla10_agents.config import Settings
from fla10_agents.editorial.github_reader import EditorialSourceError, GitHubEditorialReader
from fla10_agents.evaluation import ModelEvaluationError, run_report_test
from fla10_agents.models import SportsEvent

RUN_ACTIONS = ("created", "updated", "unchanged", "identity_unresolved")


def default_database_path() -> str:
    """Resolve o banco padrão a partir do projeto, não do diretório atual."""
    configured = os.getenv("FLA10_DATABASE", "").strip()
    if configured:
        return configured

    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / "pyproject.toml").is_file() or (directory / ".git").exists():
            return str(directory / "data" / "calendar.db")

    return str(Path.cwd() / "data" / "calendar.db")


def check_editorial() -> int:
    settings = Settings.from_env()
    with GitHubEditorialReader(settings) as reader:
        context = reader.read_bootstrap_context()
    print(f"Repositório: {context.repository}")
    print(f"Branch: {context.branch}")
    print(f"Commit editorial: {context.commit_sha}")
    print("Documentos lidos:")
    for path in context.files:
        print(f"- {path}")
    return 0


def calendar_process(input_path: str, database_path: str) -> int:
    """Importa uma observação normalizada e atualiza o calendário local."""
    try:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o arquivo {input_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError("O arquivo deve conter um objeto JSON.")

    event_data = payload.get("event", payload)
    if not isinstance(event_data, dict):
        raise TypeError("O campo 'event' deve conter um objeto JSON.")

    event = SportsEvent.model_validate(event_data)
    provider = payload.get("provider")
    external_id = payload.get("external_id")

    with CalendarRepository(database_path) as repository:
        result = CalendarAgent(repository).process_observation(
            event,
            provider=provider,
            external_id=external_id,
        )

    print(json.dumps({
        "action": result.action.value,
        "event_id": result.event_id,
        "identity_status": result.identity_status.value,
        "reason": result.reason,
        "differences": [
            {
                "field": item.field,
                "previous_value": item.previous_value,
                "current_value": item.current_value,
            }
            for item in result.differences
        ],
    }, ensure_ascii=False, indent=2))

    return 1 if result.action.value == "identity_unresolved" else 0


def calendar_sync_cbf(url: str, season: int, database_path: str) -> int:
    """Baixa uma tabela detalhada da CBF e atualiza os jogos do Flamengo."""
    with CBFCalendarSource() as source:
        observations = source.fetch_events(url, season=season)

    results = []
    totals = {action: 0 for action in RUN_ACTIONS}

    with CalendarRepository(database_path) as repository:
        run_id = repository.start_run("cbf", url)
        agent = CalendarAgent(repository)

        try:
            with repository.transaction():
                for event, external_id in observations:
                    result = agent.process_observation(
                        event,
                        provider="cbf",
                        external_id=external_id,
                    )
                    results.append({
                        "external_id": external_id,
                        "action": result.action.value,
                        "event_id": result.event_id,
                        "identity_status": result.identity_status.value,
                        "reason": result.reason,
                    })
        except Exception as exc:
            repository.finish_run(run_id, "failed", error=type(exc).__name__)
            raise

        for item in results:
            totals[str(item["action"])] += 1

        status = "completed_with_conflicts" if totals["identity_unresolved"] else "completed"
        repository.finish_run(
            run_id,
            status,
            created=totals["created"],
            updated=totals["updated"],
            unchanged=totals["unchanged"],
            rejected=totals["identity_unresolved"],
        )

    print(json.dumps({
        "run_id": run_id,
        "status": status,
        "totals": totals,
        "events": results,
    }, ensure_ascii=False, indent=2))

    return 1 if totals["identity_unresolved"] else 0


def calendar_list(database_path: str) -> int:
    """Lista os eventos registrados no calendário local."""
    with CalendarRepository(database_path) as repository:
        events = repository.list_events()
    print(json.dumps(
        [event.model_dump(mode="json") for event in events],
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def calendar_runs(database_path: str, limit: int) -> int:
    """Lista as execuções de importação registradas."""
    with CalendarRepository(database_path) as repository:
        runs = repository.list_runs(limit=limit)
    print(json.dumps(runs, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="fla10")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-editorial", help="Testa a leitura do vault editorial.")
    calendar_parser = subparsers.add_parser(
        "calendar",
        help="Importa observações e consulta o calendário esportivo local.",
    )
    calendar_commands = calendar_parser.add_subparsers(
        dest="calendar_command",
        required=True,
    )
    process_parser = calendar_commands.add_parser(
        "process",
        help="Processa um evento normalizado em arquivo JSON.",
    )
    process_parser.add_argument("--input", required=True, help="Arquivo JSON da observação.")
    process_parser.add_argument(
        "--database",
        default=default_database_path(),
        help="Banco SQLite local (padrão: data/calendar.db na raiz do projeto).",
    )
    sync_parser = calendar_commands.add_parser(
        "sync-cbf",
        help="Importa jogos do Flamengo de uma tabela detalhada oficial da CBF em PDF.",
    )
    sync_parser.add_argument("--url", required=True, help="URL do PDF oficial da tabela detalhada.")
    sync_parser.add_argument("--season", required=True, type=int, help="Ano da temporada.")
    sync_parser.add_argument(
        "--database",
        default=default_database_path(),
        help="Banco SQLite local (padrão: data/calendar.db na raiz do projeto).",
    )
    list_parser = calendar_commands.add_parser(
        "list",
        help="Lista os eventos já registrados.",
    )
    list_parser.add_argument(
        "--database",
        default=default_database_path(),
        help="Banco SQLite local (padrão: data/calendar.db na raiz do projeto).",
    )
    runs_parser = calendar_commands.add_parser(
        "runs",
        help="Lista as execuções de importação registradas.",
    )
    runs_parser.add_argument(
        "--database",
        default=default_database_path(),
        help="Banco SQLite local (padrão: data/calendar.db na raiz do projeto).",
    )
    runs_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Quantidade de execuções exibidas (padrão: 20).",
    )
    report_parser = subparsers.add_parser(
        "run-report-test",
        help="Executa ou retoma a comparação cega dos quatro modelos.",
    )
    report_parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="Retoma uma execução interrompida pelo identificador da rodada.",
    )
    args = parser.parse_args()

    try:
        if args.command == "check-editorial":
            raise SystemExit(check_editorial())
        if args.command == "calendar":
            if args.calendar_command == "process":
                raise SystemExit(calendar_process(args.input, args.database))
            if args.calendar_command == "list":
                raise SystemExit(calendar_list(args.database))
            if args.calendar_command == "runs":
                raise SystemExit(calendar_runs(args.database, args.limit))
            if args.calendar_command == "sync-cbf":
                raise SystemExit(calendar_sync_cbf(args.url, args.season, args.database))
        if args.command == "run-report-test":
            output_dir = run_report_test(resume_run_id=args.resume)
            print("Teste concluído. Arquivos salvos localmente em:")
            print(output_dir)
            print("Não publique os resultados nem a chave de cegamento antes da avaliação.")
            raise SystemExit(0)
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        sqlite3.Error,
        CBFSourceError,
        EditorialSourceError,
        ModelEvaluationError,
    ) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
