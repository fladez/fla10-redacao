"""Comandos de diagnóstico e avaliação para o MVP."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from fla10_agents.calendar import CalendarAgent, CalendarRepository
from fla10_agents.calendar.cbf_source import CBFCalendarSource, CBFSourceError
from fla10_agents.config import Settings
from fla10_agents.editorial.github_reader import EditorialSourceError, GitHubEditorialReader
from fla10_agents.editorial.pautas import Pauta, parse_pauta_documents
from fla10_agents.editorial.store import PROPOSAL_DECISIONS, EditorialRepository
from fla10_agents.editorial.vault import LocalVaultReader, VaultError
from fla10_agents.evaluation import ModelEvaluationError, run_report_test
from fla10_agents.models import SportsEvent
from fla10_agents.monitoring import SignalInputError, signals_from_payload
from fla10_agents.pipeline import build_and_save_dossier, run_pauta_pipeline
from fla10_agents.publication import (
    PublicationError,
    export_package,
    package_summary,
    prepare_package,
    register_publication,
)
from fla10_agents.research import ResearchInputError, claims_from_payload
from fla10_agents.writing import (
    LLMProvider,
    ProviderError,
    ReviewError,
    WritingError,
    build_provider,
    decide_draft,
    default_review_model,
    default_writing_model,
    generate_draft,
    review_draft,
)
from fla10_agents.writing.context import WritingContextError

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


def default_editorial_database_path() -> str:
    """Resolve o banco editorial a partir do projeto, não do diretório atual."""
    configured = os.getenv("FLA10_EDITORIAL_DATABASE", "").strip()
    if configured:
        return configured

    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / "pyproject.toml").is_file() or (directory / ".git").exists():
            return str(directory / "data" / "editorial.db")

    return str(Path.cwd() / "data" / "editorial.db")


def _pauta_to_dict(pauta: Pauta) -> dict[str, object]:
    return {
        "title": pauta.title,
        "status": pauta.status,
        "kind": pauta.kind,
        "window": pauta.window.isoformat() if pauta.window else None,
        "fields": dict(pauta.fields),
        "source": pauta.source,
    }


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def build_llm_provider() -> LLMProvider:
    """Constrói o provedor real; testes substituem esta função."""
    return build_provider()


def _parse_aware_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{label} inválida; use ISO 8601, por exemplo 2026-11-10T18:00:00-03:00."
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(f"{label} precisa incluir fuso horário.")

    return parsed



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


def vault_status(vault_root: str | None) -> int:
    """Mostra o commit do vault e as pautas que o parser reconhece."""
    reader = LocalVaultReader(Path(vault_root) if vault_root else None)
    context = reader.read_pautas()
    pautas = parse_pauta_documents(context.files)

    _print_json({
        "vault_root": str(context.root),
        "commit": context.commit,
        "documents": sorted(context.files),
        "pautas": len(pautas),
        "by_kind": {
            kind: sum(1 for pauta in pautas if pauta.kind == kind)
            for kind in sorted({pauta.kind for pauta in pautas})
        },
    })
    return 0


def pautas_parse(vault_root: str | None) -> int:
    """Extrai as pautas das notas do vault, sem gravar nada."""
    reader = LocalVaultReader(Path(vault_root) if vault_root else None)
    context = reader.read_pautas()
    pautas = parse_pauta_documents(context.files)
    _print_json([_pauta_to_dict(pauta) for pauta in pautas])
    return 0


def pautas_list(database_path: str, status: str | None, limit: int) -> int:
    """Lista as propostas de pauta registradas no banco editorial."""
    with EditorialRepository(database_path) as store:
        proposals = store.list_proposals(status=status, limit=limit)

    _print_json([
        {
            "proposal_id": proposal.proposal_id,
            "title": proposal.title,
            "format": proposal.format,
            "window": proposal.window,
            "priority": proposal.priority_recommendation,
            "redundancy_risk": proposal.redundancy_risk,
            "decision": proposal.editorial_decision,
            "related_reserved": proposal.related_reserved,
            "related_published": proposal.related_published,
        }
        for proposal in proposals
    ])
    return 0


def pautas_decide(database_path: str, proposal_id: str, decision: str) -> int:
    """Registra a decisão humana sobre uma proposta de pauta."""
    with EditorialRepository(database_path) as store:
        proposal = store.decide_proposal(proposal_id, decision)

    _print_json({
        "proposal_id": proposal.proposal_id,
        "title": proposal.title,
        "decision": proposal.editorial_decision,
    })
    return 0


def sinais_add(database_path: str, input_path: str, provider: str | None) -> int:
    """Valida e grava sinais de monitoramento em arquivo JSON."""
    try:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o arquivo {input_path}: {exc}") from exc

    signals = signals_from_payload(payload, default_provider=provider)

    created = 0
    updated = 0
    with EditorialRepository(database_path) as store:
        for signal in signals:
            if store.save_signal(signal):
                created += 1
            else:
                updated += 1

    _print_json({
        "received": len(signals),
        "created": created,
        "updated": updated,
    })
    return 0


def sinais_list(database_path: str, limit: int) -> int:
    """Lista os sinais de monitoramento mais recentes."""
    with EditorialRepository(database_path) as store:
        signals = store.list_signals(limit=limit)

    _print_json([
        {
            "signal_id": signal.signal_id,
            "provider": signal.provider,
            "external_id": signal.external_id,
            "title": signal.title,
            "url": str(signal.url) if signal.url else None,
            "published_at": signal.published_at.isoformat(),
            "last_seen_at": signal.last_seen_at.isoformat(),
        }
        for signal in signals
    ])
    return 0


def dossie_build(
    database_path: str,
    proposal_id: str,
    claims_path: str | None,
    contradictions: list[str],
) -> int:
    """Monta e grava o dossiê de apuração de uma proposta."""
    claims = []
    if claims_path:
        try:
            payload = json.loads(Path(claims_path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(
                f"Não foi possível ler o arquivo {claims_path}: {exc}"
            ) from exc
        claims = claims_from_payload(payload)

    result = build_and_save_dossier(
        database_path,
        proposal_id,
        claims=claims,
        contradictions=contradictions,
    )

    with EditorialRepository(database_path) as store:
        dossier = store.get_dossier(proposal_id)

    _print_json({
        **result,
        "gaps": dossier.gaps if dossier else [],
        "contradictions": dossier.contradictions if dossier else [],
    })
    return 0


def publicacoes_add(
    database_path: str,
    title: str,
    url: str | None,
    format: str | None,
    angle: str | None,
    published_at: str | None,
) -> int:
    """Registra uma matéria já publicada para a checagem de redundância."""
    moment = None
    if published_at:
        try:
            moment = datetime.fromisoformat(published_at)
        except ValueError as exc:
            raise ValueError(
                "Data de publicação inválida; use ISO 8601, por exemplo "
                "2026-11-10T18:00:00-03:00."
            ) from exc
        if moment.tzinfo is None:
            raise ValueError("A data de publicação precisa incluir fuso horário.")

    with EditorialRepository(database_path) as store:
        article_id = store.register_publication(
            title=title,
            url=url,
            format=format,
            angle=angle,
            published_at=moment,
        )

    _print_json({"article_id": article_id, "title": title})
    return 0


def publicacoes_list(database_path: str, limit: int) -> int:
    """Lista os títulos publicados usados na checagem de redundância."""
    with EditorialRepository(database_path) as store:
        titles = store.list_published_titles(limit=limit)

    _print_json(titles)
    return 0


def pipeline_run(
    calendar_database: str,
    editorial_database: str,
    vault_root: str | None,
    event_days: int,
    signal_days: int,
) -> int:
    """Executa a geração de propostas da Fase 1 sobre agenda e sinais."""
    result = run_pauta_pipeline(
        calendar_database,
        editorial_database,
        vault_root=Path(vault_root) if vault_root else None,
        event_days=event_days,
        signal_days=signal_days,
    )
    _print_json(result)
    return 0



def redacao_gerar(
    database_path: str,
    proposal_id: str,
    model: str,
    max_tokens: int,
    vault_root: str | None,
) -> int:
    """Gera um texto a partir de pauta aprovada e dossiê suficiente."""
    provider = build_llm_provider()
    draft = generate_draft(
        database_path,
        proposal_id,
        provider,
        model=model,
        vault_root=Path(vault_root) if vault_root else None,
        max_tokens=max_tokens,
    )

    _print_json({
        "draft_id": draft.draft_id,
        "proposal_id": draft.proposal_id,
        "title": draft.title,
        "model": draft.model,
        "decision": draft.editorial_decision,
    })
    return 0


def redacao_revisar(
    database_path: str,
    draft_id: str,
    model: str,
    deterministic_only: bool,
    vault_root: str | None,
) -> int:
    """Revisa um texto de forma independente."""
    provider = None if deterministic_only else build_llm_provider()
    report = review_draft(
        database_path,
        draft_id,
        provider,
        model=model,
        vault_root=Path(vault_root) if vault_root else None,
    )

    _print_json({
        "review_id": report.review_id,
        "draft_id": report.draft_id,
        "verdict": report.verdict,
        "reviewer_model": report.reviewer_model,
        "summary": report.summary,
        "issues": [
            {
                "severity": issue.severity,
                "category": issue.category,
                "description": issue.description,
                "evidence": issue.evidence,
            }
            for issue in report.issues
        ],
    })
    return 0


def redacao_list(database_path: str, proposal_id: str | None, limit: int) -> int:
    """Lista textos gerados e o parecer da revisão mais recente."""
    with EditorialRepository(database_path) as store:
        drafts = store.list_drafts(proposal_id=proposal_id, limit=limit)
        items = []
        for draft in drafts:
            review = store.get_latest_review(draft.draft_id)
            items.append({
                "draft_id": draft.draft_id,
                "proposal_id": draft.proposal_id,
                "title": draft.title,
                "format": draft.format,
                "decision": draft.editorial_decision,
                "review_verdict": review.verdict if review else None,
                "created_at": draft.created_at.isoformat(),
            })

    _print_json(items)
    return 0


def redacao_mostrar(database_path: str, draft_id: str) -> int:
    """Mostra o texto completo e a revisão mais recente."""
    with EditorialRepository(database_path) as store:
        draft = store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"Texto não encontrado: {draft_id}")
        review = store.get_latest_review(draft_id)

    _print_json({
        "draft": draft.model_dump(mode="json"),
        "review": review.model_dump(mode="json") if review else None,
    })
    return 0


def redacao_decidir(database_path: str, draft_id: str, decision: str) -> int:
    """Registra aprovação ou rejeição humana do texto."""
    draft = decide_draft(database_path, draft_id, decision)
    _print_json({
        "draft_id": draft.draft_id,
        "title": draft.title,
        "decision": draft.editorial_decision,
    })
    return 0


def publicacao_preparar(database_path: str, draft_id: str) -> int:
    """Monta o pacote de CMS sem publicar."""
    package = prepare_package(database_path, draft_id)
    _print_json(package_summary(package))
    return 0


def publicacao_exportar(database_path: str, package_id: str, output: str) -> int:
    """Exporta o pacote para uma pasta local."""
    destination = export_package(database_path, package_id, output)
    _print_json({
        "output": str(destination),
        "files": [
            "article.html",
            "article.md",
            "package.json",
            "metadata.json",
        ],
    })
    return 0


def publicacao_list(database_path: str, status: str | None, limit: int) -> int:
    """Lista pacotes de publicação."""
    with EditorialRepository(database_path) as store:
        packages = store.list_packages(status=status, limit=limit)

    _print_json([package_summary(package) for package in packages])
    return 0


def publicacao_registrar(
    database_path: str,
    package_id: str,
    url: str,
    published_at: str,
    confirmation: str,
) -> int:
    """Registra uma publicação externa já confirmada; não publica nada."""
    package = register_publication(
        database_path,
        package_id,
        url=url,
        published_at=_parse_aware_datetime(published_at, "Data de publicação"),
        confirmation=confirmation,
    )
    _print_json(package_summary(package))
    return 0


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
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
        help="Executa a comparação paga legada, se explicitamente autorizada.",
    )
    report_parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="Retoma uma execução interrompida pelo identificador da rodada.",
    )

    vault_parser = subparsers.add_parser(
        "vault",
        help="Consulta o vault editorial local (somente leitura).",
    )
    vault_commands = vault_parser.add_subparsers(dest="vault_command", required=True)
    vault_status_parser = vault_commands.add_parser(
        "status",
        help="Mostra commit do vault e pautas reconhecidas.",
    )
    vault_status_parser.add_argument(
        "--vault",
        default=None,
        help="Raiz do vault (padrão: EDITORIAL_VAULT_PATH ou ~/Documents/Redacao-Fla10).",
    )

    pautas_parser = subparsers.add_parser(
        "pautas",
        help="Extrai pautas do vault e administra as propostas geradas.",
    )
    pautas_commands = pautas_parser.add_subparsers(dest="pautas_command", required=True)
    pautas_parse_parser = pautas_commands.add_parser(
        "parse",
        help="Extrai as pautas das notas do vault, sem gravar nada.",
    )
    pautas_parse_parser.add_argument(
        "--vault",
        default=None,
        help="Raiz do vault (padrão: EDITORIAL_VAULT_PATH ou ~/Documents/Redacao-Fla10).",
    )
    pautas_list_parser = pautas_commands.add_parser(
        "list",
        help="Lista as propostas de pauta registradas.",
    )
    pautas_list_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    pautas_list_parser.add_argument(
        "--status",
        choices=PROPOSAL_DECISIONS,
        default=None,
        help="Filtra pelo estado da decisão editorial.",
    )
    pautas_list_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Quantidade de propostas exibidas (padrão: 100).",
    )
    for name, help_text in (
        ("approve", "Aprova uma proposta para apuração."),
        ("reject", "Rejeita uma proposta."),
    ):
        decision_parser = pautas_commands.add_parser(name, help=help_text)
        decision_parser.add_argument("proposal_id", help="Identificador da proposta.")
        decision_parser.add_argument(
            "--database",
            default=default_editorial_database_path(),
            help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
        )

    sinais_parser = subparsers.add_parser(
        "sinais",
        help="Carrega e lista sinais de monitoramento.",
    )
    sinais_commands = sinais_parser.add_subparsers(dest="sinais_command", required=True)
    sinais_add_parser = sinais_commands.add_parser(
        "add",
        help="Valida e grava sinais de um arquivo JSON.",
    )
    sinais_add_parser.add_argument("--input", required=True, help="Arquivo JSON com os sinais.")
    sinais_add_parser.add_argument(
        "--provider",
        default=None,
        help="Provedor padrão para sinais sem o campo 'provider'.",
    )
    sinais_add_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    sinais_list_parser = sinais_commands.add_parser(
        "list",
        help="Lista os sinais de monitoramento mais recentes.",
    )
    sinais_list_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    sinais_list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Quantidade de sinais exibidos (padrão: 50).",
    )

    dossie_parser = subparsers.add_parser(
        "dossie",
        help="Monta o dossiê de apuração de uma proposta.",
    )
    dossie_commands = dossie_parser.add_subparsers(dest="dossie_command", required=True)
    dossie_build_parser = dossie_commands.add_parser(
        "build",
        help="Valida afirmações e grava o dossiê da proposta.",
    )
    dossie_build_parser.add_argument("proposal_id", help="Identificador da proposta.")
    dossie_build_parser.add_argument(
        "--claims",
        default=None,
        help="Arquivo JSON com afirmações e evidências.",
    )
    dossie_build_parser.add_argument(
        "--contradiction",
        action="append",
        default=[],
        help="Contradição identificada na apuração (pode repetir).",
    )
    dossie_build_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Executa a geração de pautas da Fase 1.",
    )
    pipeline_commands = pipeline_parser.add_subparsers(
        dest="pipeline_command",
        required=True,
    )
    pipeline_run_parser = pipeline_commands.add_parser(
        "run",
        help="Gera propostas a partir da agenda, sinais e vault.",
    )
    pipeline_run_parser.add_argument(
        "--calendar-database",
        default=default_database_path(),
        help="Banco do calendário (padrão: data/calendar.db na raiz do projeto).",
    )
    pipeline_run_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    pipeline_run_parser.add_argument(
        "--vault",
        default=None,
        help="Raiz do vault (padrão: EDITORIAL_VAULT_PATH ou ~/Documents/Redacao-Fla10).",
    )
    pipeline_run_parser.add_argument(
        "--event-days",
        type=int,
        default=7,
        help="Janela de jogos em dias (padrão: 7).",
    )
    pipeline_run_parser.add_argument(
        "--signal-days",
        type=int,
        default=3,
        help="Janela de sinais em dias (padrão: 3).",
    )

    publicacoes_parser = subparsers.add_parser(
        "publicacoes",
        help="Registra matérias publicadas para a checagem de redundância.",
    )
    publicacoes_commands = publicacoes_parser.add_subparsers(
        dest="publicacoes_command",
        required=True,
    )
    publicacoes_add_parser = publicacoes_commands.add_parser(
        "add",
        help="Registra uma matéria já publicada.",
    )
    publicacoes_add_parser.add_argument("--title", required=True, help="Título da matéria.")
    publicacoes_add_parser.add_argument("--url", default=None, help="URL da matéria.")
    publicacoes_add_parser.add_argument("--format", default=None, help="Formato editorial.")
    publicacoes_add_parser.add_argument("--angle", default=None, help="Ângulo da matéria.")
    publicacoes_add_parser.add_argument(
        "--published-at",
        default=None,
        help="Data ISO 8601 com fuso horário.",
    )
    publicacoes_add_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    publicacoes_list_parser = publicacoes_commands.add_parser(
        "list",
        help="Lista os títulos publicados registrados.",
    )
    publicacoes_list_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    publicacoes_list_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Quantidade de títulos exibidos (padrão: 200).",
    )

    redacao_parser = subparsers.add_parser(
        "redacao",
        help="Gera, revisa e decide textos a partir de pautas aprovadas.",
    )
    redacao_commands = redacao_parser.add_subparsers(
        dest="redacao_command",
        required=True,
    )
    redacao_gerar_parser = redacao_commands.add_parser(
        "gerar",
        help="Gera um texto com base em pauta aprovada e dossiê suficiente.",
    )
    redacao_gerar_parser.add_argument("proposal_id", help="Identificador da pauta.")
    redacao_gerar_parser.add_argument(
        "--model",
        default=default_writing_model(),
        help=(
            "Modelo do motor (padrão: FLA10_WRITING_MODEL ou "
            "opencode/deepseek-v4.1-flash-free)."
        ),
    )
    redacao_gerar_parser.add_argument(
        "--max-tokens",
        type=int,
        default=8000,
        help=(
            "Limite de tokens de saída no OpenRouter (padrão: 8000). "
            "No motor OpenCode, o runtime controla a geração."
        ),
    )
    redacao_gerar_parser.add_argument(
        "--vault",
        default=None,
        help="Raiz do vault (padrão: EDITORIAL_VAULT_PATH ou ~/Documents/Redacao-Fla10).",
    )
    redacao_gerar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    redacao_revisar_parser = redacao_commands.add_parser(
        "revisar",
        help="Revisa um texto de forma independente.",
    )
    redacao_revisar_parser.add_argument("draft_id", help="Identificador do texto.")
    redacao_revisar_parser.add_argument(
        "--model",
        default=default_review_model(),
        help="Modelo revisor (padrão: FLA10_REVIEW_MODEL ou o modelo de redação).",
    )
    redacao_revisar_parser.add_argument(
        "--deterministico",
        action="store_true",
        help="Executa apenas as checagens automáticas, sem chamar modelo.",
    )
    redacao_revisar_parser.add_argument(
        "--vault",
        default=None,
        help="Raiz do vault (padrão: EDITORIAL_VAULT_PATH ou ~/Documents/Redacao-Fla10).",
    )
    redacao_revisar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    redacao_list_parser = redacao_commands.add_parser(
        "list",
        help="Lista textos gerados e o parecer mais recente.",
    )
    redacao_list_parser.add_argument(
        "--proposal-id",
        default=None,
        help="Filtra por pauta.",
    )
    redacao_list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Quantidade de textos exibidos (padrão: 50).",
    )
    redacao_list_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    redacao_mostrar_parser = redacao_commands.add_parser(
        "mostrar",
        help="Mostra o texto completo e a revisão mais recente.",
    )
    redacao_mostrar_parser.add_argument("draft_id", help="Identificador do texto.")
    redacao_mostrar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    for name, help_text in (
        ("aprovar", "Aprova um texto revisado."),
        ("rejeitar", "Rejeita um texto."),
    ):
        decision_parser = redacao_commands.add_parser(name, help=help_text)
        decision_parser.add_argument("draft_id", help="Identificador do texto.")
        decision_parser.add_argument(
            "--database",
            default=default_editorial_database_path(),
            help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
        )

    publicacao_parser = subparsers.add_parser(
        "publicacao",
        help="Prepara, exporta e registra publicações confirmadas.",
    )
    publicacao_commands = publicacao_parser.add_subparsers(
        dest="publicacao_command",
        required=True,
    )
    publicacao_preparar_parser = publicacao_commands.add_parser(
        "preparar",
        help="Monta o pacote de CMS de um texto aprovado.",
    )
    publicacao_preparar_parser.add_argument("draft_id", help="Identificador do texto.")
    publicacao_preparar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    publicacao_exportar_parser = publicacao_commands.add_parser(
        "exportar",
        help="Exporta o pacote para uma pasta local.",
    )
    publicacao_exportar_parser.add_argument("package_id", help="Identificador do pacote.")
    publicacao_exportar_parser.add_argument(
        "--output",
        required=True,
        help="Pasta de saída; cada pacote recebe uma subpasta própria.",
    )
    publicacao_exportar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    publicacao_list_parser = publicacao_commands.add_parser(
        "list",
        help="Lista pacotes de publicação.",
    )
    publicacao_list_parser.add_argument(
        "--status",
        choices=("prepared", "exported", "published"),
        default=None,
        help="Filtra pelo estado do pacote.",
    )
    publicacao_list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Quantidade de pacotes exibidos (padrão: 50).",
    )
    publicacao_list_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
    )
    publicacao_registrar_parser = publicacao_commands.add_parser(
        "registrar",
        help="Registra uma publicação externa já confirmada.",
    )
    publicacao_registrar_parser.add_argument("package_id", help="Identificador do pacote.")
    publicacao_registrar_parser.add_argument(
        "--url",
        required=True,
        help="URL pública da matéria publicada.",
    )
    publicacao_registrar_parser.add_argument(
        "--published-at",
        required=True,
        help="Data ISO 8601 com fuso horário.",
    )
    publicacao_registrar_parser.add_argument(
        "--confirmar",
        required=True,
        help="Evidência ou confirmação explícita de que a publicação ocorreu.",
    )
    publicacao_registrar_parser.add_argument(
        "--database",
        default=default_editorial_database_path(),
        help="Banco editorial SQLite (padrão: data/editorial.db na raiz do projeto).",
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
        if args.command == "vault" and args.vault_command == "status":
            raise SystemExit(vault_status(args.vault))
        if args.command == "pautas":
            if args.pautas_command == "parse":
                raise SystemExit(pautas_parse(args.vault))
            if args.pautas_command == "list":
                raise SystemExit(pautas_list(args.database, args.status, args.limit))
            if args.pautas_command == "approve":
                raise SystemExit(pautas_decide(args.database, args.proposal_id, "approved"))
            if args.pautas_command == "reject":
                raise SystemExit(pautas_decide(args.database, args.proposal_id, "rejected"))
        if args.command == "sinais":
            if args.sinais_command == "add":
                raise SystemExit(sinais_add(args.database, args.input, args.provider))
            if args.sinais_command == "list":
                raise SystemExit(sinais_list(args.database, args.limit))
        if args.command == "dossie" and args.dossie_command == "build":
            raise SystemExit(dossie_build(
                args.database,
                args.proposal_id,
                args.claims,
                args.contradiction,
            ))
        if args.command == "pipeline" and args.pipeline_command == "run":
            raise SystemExit(pipeline_run(
                args.calendar_database,
                args.database,
                args.vault,
                args.event_days,
                args.signal_days,
            ))
        if args.command == "publicacoes":
            if args.publicacoes_command == "add":
                raise SystemExit(publicacoes_add(
                    args.database,
                    args.title,
                    args.url,
                    args.format,
                    args.angle,
                    args.published_at,
                ))
            if args.publicacoes_command == "list":
                raise SystemExit(publicacoes_list(args.database, args.limit))
        if args.command == "redacao":
            if args.redacao_command == "gerar":
                raise SystemExit(redacao_gerar(
                    args.database,
                    args.proposal_id,
                    args.model,
                    args.max_tokens,
                    args.vault,
                ))
            if args.redacao_command == "revisar":
                raise SystemExit(redacao_revisar(
                    args.database,
                    args.draft_id,
                    args.model,
                    args.deterministico,
                    args.vault,
                ))
            if args.redacao_command == "list":
                raise SystemExit(redacao_list(
                    args.database,
                    args.proposal_id,
                    args.limit,
                ))
            if args.redacao_command == "mostrar":
                raise SystemExit(redacao_mostrar(args.database, args.draft_id))
            if args.redacao_command == "aprovar":
                raise SystemExit(redacao_decidir(args.database, args.draft_id, "approved"))
            if args.redacao_command == "rejeitar":
                raise SystemExit(redacao_decidir(args.database, args.draft_id, "rejected"))
        if args.command == "publicacao":
            if args.publicacao_command == "preparar":
                raise SystemExit(publicacao_preparar(args.database, args.draft_id))
            if args.publicacao_command == "exportar":
                raise SystemExit(publicacao_exportar(
                    args.database,
                    args.package_id,
                    args.output,
                ))
            if args.publicacao_command == "list":
                raise SystemExit(publicacao_list(
                    args.database,
                    args.status,
                    args.limit,
                ))
            if args.publicacao_command == "registrar":
                raise SystemExit(publicacao_registrar(
                    args.database,
                    args.package_id,
                    args.url,
                    args.published_at,
                    args.confirmar,
                ))
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
        VaultError,
        SignalInputError,
        ResearchInputError,
        ProviderError,
        WritingError,
        WritingContextError,
        ReviewError,
        PublicationError,
    ) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
