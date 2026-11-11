from datetime import UTC, datetime
from pathlib import Path

from fla10_agents.calendar import CalendarAgent, CalendarRepository
from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import MonitoringSignal, SportsEvent
from fla10_agents.pipeline import build_and_save_dossier, run_pauta_pipeline

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


def make_event() -> SportsEvent:
    return SportsEvent.model_validate({
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
    })


def make_signal() -> MonitoringSignal:
    return MonitoringSignal(
        provider="teste",
        external_id="sig-1",
        title="Flamengo confirma retorno de jogador",
        summary="Atleta voltou aos treinos com o grupo.",
        url="https://example.com/noticia",
        published_at=NOW,
        teams=["Flamengo"],
        last_seen_at=NOW,
    )


def prepare_databases(tmp_path: Path) -> tuple[Path, Path]:
    calendar_db = tmp_path / "calendar.db"
    editorial_db = tmp_path / "editorial.db"

    with CalendarRepository(calendar_db) as calendar:
        CalendarAgent(calendar).process_observation(
            make_event(),
            provider="teste",
            external_id="evt-1",
        )

    with EditorialRepository(editorial_db) as store:
        store.save_signal(make_signal())

    return calendar_db, editorial_db


def test_pipeline_creates_event_and_signal_proposals(tmp_path) -> None:
    vault = make_vault(tmp_path)
    calendar_db, editorial_db = prepare_databases(tmp_path)

    result = run_pauta_pipeline(
        calendar_db,
        editorial_db,
        vault_root=vault,
        now=NOW,
    )

    assert result["status"] == "completed"
    assert result["pautas"] == 2
    assert result["events"] == 1
    assert result["signals"] == 1
    assert result["created"] == 3
    assert result["skipped"] == 0

    with EditorialRepository(editorial_db) as store:
        proposals = store.list_proposals()
        runs = store.list_runs()

    formats = {proposal.format for proposal in proposals}
    assert formats == {"onde_assistir", "ultimas_noticias"}
    titles = {proposal.title for proposal in proposals}
    assert "Projeto sobre a base do Flamengo" in titles
    assert runs[0]["status"] == "completed"
    assert runs[0]["created"] == 3


def test_pipeline_is_idempotent_and_preserves_decisions(tmp_path) -> None:
    vault = make_vault(tmp_path)
    calendar_db, editorial_db = prepare_databases(tmp_path)

    run_pauta_pipeline(calendar_db, editorial_db, vault_root=vault, now=NOW)

    with EditorialRepository(editorial_db) as store:
        event_proposal = next(
            proposal
            for proposal in store.list_proposals()
            if proposal.format == "onde_assistir"
        )
        store.decide_proposal(event_proposal.proposal_id, "approved")

    second = run_pauta_pipeline(calendar_db, editorial_db, vault_root=vault, now=NOW)

    assert second["created"] == 0
    assert second["skipped"] == 3

    with EditorialRepository(editorial_db) as store:
        stored = store.get_proposal(event_proposal.proposal_id)

    assert stored is not None
    assert stored.editorial_decision == "approved"


def test_pipeline_marks_redundancy_against_registered_publication(tmp_path) -> None:
    vault = make_vault(tmp_path)
    calendar_db, editorial_db = prepare_databases(tmp_path)

    with EditorialRepository(editorial_db) as store:
        store.register_publication(
            "Flamengo x Palmeiras: onde assistir",
            published_at=NOW,
        )

    run_pauta_pipeline(calendar_db, editorial_db, vault_root=vault, now=NOW)

    with EditorialRepository(editorial_db) as store:
        proposal = next(
            item
            for item in store.list_proposals()
            if item.format == "onde_assistir"
        )

    assert proposal.redundancy_risk == "alto"
    assert proposal.related_published == ["Flamengo x Palmeiras: onde assistir"]


def test_build_and_save_dossier_requires_approval(tmp_path) -> None:
    vault = make_vault(tmp_path)
    calendar_db, editorial_db = prepare_databases(tmp_path)
    run_pauta_pipeline(calendar_db, editorial_db, vault_root=vault, now=NOW)

    with EditorialRepository(editorial_db) as store:
        proposal = next(
            item
            for item in store.list_proposals()
            if item.format == "onde_assistir"
        )

    try:
        build_and_save_dossier(editorial_db, proposal.proposal_id, now=NOW)
    except ValueError as exc:
        assert "aprovada" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("dossiê sem aprovação deveria falhar")


def test_build_and_save_dossier_records_result(tmp_path) -> None:
    vault = make_vault(tmp_path)
    calendar_db, editorial_db = prepare_databases(tmp_path)
    run_pauta_pipeline(calendar_db, editorial_db, vault_root=vault, now=NOW)

    with EditorialRepository(editorial_db) as store:
        proposal = next(
            item
            for item in store.list_proposals()
            if item.format == "onde_assistir"
        )
        store.decide_proposal(proposal.proposal_id, "approved")
        result = build_and_save_dossier(
            editorial_db,
            proposal.proposal_id,
            contradictions=["Horário divergente em fonte secundária."],
            now=NOW,
        )
        dossier = store.get_dossier(proposal.proposal_id)

    assert result["proposal_id"] == proposal.proposal_id
    assert result["recommendation"] == "apuração insuficiente"
    assert dossier is not None
    assert dossier.contradictions == ["Horário divergente em fonte secundária."]
    assert any("sem evidência" in gap for gap in dossier.gaps)
