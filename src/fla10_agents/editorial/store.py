"""Persistência do estado operacional editorial (sinais, pautas, dossiês)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from fla10_agents.models import EditorialProposal, MonitoringSignal, ResearchDossier

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
PROPOSAL_DECISIONS = ("awaiting_human", "approved", "rejected", "published")


@dataclass(frozen=True, slots=True)
class SavedProposal:
    proposal: EditorialProposal
    created: bool


class EditorialRepository:
    """Armazena sinais monitorados, propostas de pauta e dossiês."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)

        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        self._connection.execute("PRAGMA foreign_keys = ON")

        if self.database_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = NORMAL")

        self._transaction_depth = 0
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @property
    def schema_version(self) -> int:
        return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._transaction_depth:
            self._transaction_depth += 1
            try:
                yield
            finally:
                self._transaction_depth -= 1
            return

        self._connection.execute("BEGIN IMMEDIATE")
        self._transaction_depth = 1

        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()
        finally:
            self._transaction_depth = 0

    def _create_schema(self) -> None:
        current_version = self.schema_version
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Banco editorial com schema {current_version}, mais novo que o "
                f"suportado ({SCHEMA_VERSION}). Atualize o Fla10-Agents."
            )

        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitoring_signals (
                    signal_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE (provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS editorial_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    dedupe_key TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_dossiers (
                    proposal_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    researched_at TEXT NOT NULL,
                    FOREIGN KEY (proposal_id)
                        REFERENCES editorial_proposals(proposal_id)
                );

                CREATE TABLE IF NOT EXISTS published_articles (
                    article_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT,
                    format TEXT,
                    angle TEXT,
                    published_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS editorial_runs (
                    run_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    created INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                """
            )

        if current_version < SCHEMA_VERSION:
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # --- sinais de monitoramento -------------------------------------

    def save_signal(self, signal: MonitoringSignal) -> bool:
        """Insere sinal novo ou atualiza o já conhecido; retorna se é novo."""
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        payload = signal.model_copy(update={"last_seen_at": now_dt}).model_dump_json()

        with self.transaction():
            existing = self._connection.execute(
                """
                SELECT signal_id FROM monitoring_signals
                WHERE provider = ? AND external_id = ?
                """,
                (signal.provider.strip().casefold(), signal.external_id.strip()),
            ).fetchone()

            if existing is not None:
                self._connection.execute(
                    """
                    UPDATE monitoring_signals
                    SET payload = ?, last_seen_at = ?
                    WHERE signal_id = ?
                    """,
                    (payload, now, existing["signal_id"]),
                )
                return False

            self._connection.execute(
                """
                INSERT INTO monitoring_signals
                    (signal_id, provider, external_id, payload,
                     first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.provider.strip().casefold(),
                    signal.external_id.strip(),
                    payload,
                    now,
                    now,
                ),
            )
            return True

    def list_signals(self, limit: int = 100) -> list[MonitoringSignal]:
        rows = self._connection.execute(
            """
            SELECT payload FROM monitoring_signals
            ORDER BY last_seen_at DESC, signal_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [MonitoringSignal.model_validate_json(row["payload"]) for row in rows]

    # --- propostas de pauta ------------------------------------------

    def save_proposal(self, proposal: EditorialProposal) -> SavedProposal:
        """Grava a proposta uma única vez por chave de deduplicação."""
        payload = proposal.model_dump_json()
        now = self._now()

        with self.transaction():
            if proposal.dedupe_key:
                existing = self._connection.execute(
                    "SELECT proposal_id FROM editorial_proposals WHERE dedupe_key = ?",
                    (proposal.dedupe_key,),
                ).fetchone()
                if existing is not None:
                    row = self._connection.execute(
                        """
                        SELECT payload, status FROM editorial_proposals
                        WHERE proposal_id = ?
                        """,
                        (existing["proposal_id"],),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError(
                            "Proposta existente não encontrada ao atualizar: "
                            f"{existing['proposal_id']}"
                        )
                    previous = EditorialProposal.model_validate_json(row["payload"])
                    merged = proposal.model_copy(update={
                        "proposal_id": previous.proposal_id,
                        "editorial_decision": previous.editorial_decision,
                        "created_at": previous.created_at or proposal.created_at,
                    })
                    self._connection.execute(
                        """
                        UPDATE editorial_proposals
                        SET payload = ?, updated_at = ?
                        WHERE proposal_id = ?
                        """,
                        (merged.model_dump_json(), now, previous.proposal_id),
                    )
                    return SavedProposal(proposal=merged, created=False)

            self._connection.execute(
                """
                INSERT INTO editorial_proposals
                    (proposal_id, dedupe_key, payload, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.dedupe_key,
                    payload,
                    proposal.editorial_decision,
                    now,
                    now,
                ),
            )

        return SavedProposal(proposal=proposal, created=True)

    def get_proposal(self, proposal_id: str) -> EditorialProposal | None:
        row = self._connection.execute(
            "SELECT payload FROM editorial_proposals WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()

        if row is None:
            return None

        return EditorialProposal.model_validate_json(row["payload"])

    def list_proposals(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EditorialProposal]:
        query = "SELECT payload FROM editorial_proposals"
        parameters: list[object] = []

        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)

        query += " ORDER BY created_at DESC, proposal_id LIMIT ?"
        parameters.append(limit)

        rows = self._connection.execute(query, parameters).fetchall()
        return [EditorialProposal.model_validate_json(row["payload"]) for row in rows]

    def decide_proposal(self, proposal_id: str, decision: str) -> EditorialProposal:
        if decision not in PROPOSAL_DECISIONS:
            raise ValueError(
                "Decisão inválida. Use: " + ", ".join(PROPOSAL_DECISIONS)
            )

        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Pauta não encontrada: {proposal_id}")

        updated = proposal.model_copy(update={"editorial_decision": decision})

        with self.transaction():
            self._connection.execute(
                """
                UPDATE editorial_proposals
                SET payload = ?, status = ?, updated_at = ?
                WHERE proposal_id = ?
                """,
                (updated.model_dump_json(), decision, self._now(), proposal_id),
            )

        return updated

    # --- dossiês ------------------------------------------------------

    def save_dossier(self, dossier: ResearchDossier) -> None:
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO research_dossiers
                    (proposal_id, payload, recommendation, researched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (proposal_id) DO UPDATE SET
                    payload = excluded.payload,
                    recommendation = excluded.recommendation,
                    researched_at = excluded.researched_at
                """,
                (
                    dossier.proposal_id,
                    dossier.model_dump_json(),
                    dossier.recommendation,
                    dossier.researched_at.isoformat(),
                ),
            )

    def get_dossier(self, proposal_id: str) -> ResearchDossier | None:
        row = self._connection.execute(
            "SELECT payload FROM research_dossiers WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()

        if row is None:
            return None

        return ResearchDossier.model_validate_json(row["payload"])

    # --- matérias publicadas -----------------------------------------

    def register_publication(
        self,
        title: str,
        url: str | None = None,
        format: str | None = None,
        angle: str | None = None,
        published_at: datetime | None = None,
    ) -> str:
        """Registra matéria publicada para alimentar a checagem de redundância."""
        article_id = str(uuid4())
        published = (published_at or datetime.now(UTC)).isoformat()

        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO published_articles
                    (article_id, title, url, format, angle, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (article_id, title, url, format, angle, published),
            )

        return article_id

    def list_published_titles(self, limit: int = 200) -> list[str]:
        rows = self._connection.execute(
            """
            SELECT title FROM published_articles
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [row["title"] for row in rows]

    # --- execuções ----------------------------------------------------

    def start_run(self, kind: str) -> str:
        run_id = str(uuid4())

        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO editorial_runs (run_id, kind, started_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, kind, self._now(), "running"),
            )

        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        created: int = 0,
        skipped: int = 0,
        error: str | None = None,
    ) -> None:
        with self.transaction():
            self._connection.execute(
                """
                UPDATE editorial_runs
                SET finished_at = ?, status = ?, created = ?, skipped = ?, error = ?
                WHERE run_id = ?
                """,
                (self._now(), status, created, skipped, error, run_id),
            )

    def list_runs(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """
            SELECT run_id, kind, started_at, finished_at, status,
                   created, skipped, error
            FROM editorial_runs
            ORDER BY started_at DESC, run_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]
