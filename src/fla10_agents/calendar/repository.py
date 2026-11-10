"""Persistência SQLite de eventos esportivos e seu histórico."""

import sqlite3
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self
from uuid import uuid4

from fla10_agents.calendar.comparator import compare_events
from fla10_agents.models import SportsEvent

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000


class IdentityResolutionStatus(StrEnum):
    MATCHED = "matched"
    NEW = "new"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class EventIdentityResolution:
    """Resultado da tentativa de identificar um evento observado."""

    status: IdentityResolutionStatus
    event: SportsEvent | None
    candidates: tuple[SportsEvent, ...] = ()
    reason: str | None = None


def _normalize_identity_text(value: str) -> str:
    """Normaliza caixa, acentos e espaços, sem presumir aliases entre nomes."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split()).casefold()


def _identity_key(event: SportsEvent) -> str:
    """Chave indexável formada pelos atributos estáveis da identidade."""
    fields = (
        event.sport,
        event.category,
        event.competition,
        event.season or "",
        event.home_team,
        event.away_team,
    )
    return "|".join(_normalize_identity_text(field) for field in fields)


def _same_event_identity(
    existing: SportsEvent,
    observed: SportsEvent,
) -> bool:
    """Compara atributos estáveis da identidade esportiva."""

    required_fields = (
        "sport",
        "category",
        "competition",
        "season",
        "home_team",
        "away_team",
    )

    for field in required_fields:
        old_value = getattr(existing, field)
        new_value = getattr(observed, field)

        if old_value is None or new_value is None:
            if old_value != new_value:
                return False
            continue

        if _normalize_identity_text(str(old_value)) != (_normalize_identity_text(str(new_value))):
            return False

    return not (
        existing.stage
        and observed.stage
        and _normalize_identity_text(existing.stage) != _normalize_identity_text(observed.stage)
    )


def _normalize_provider(provider: str) -> str:
    """Uniformiza o identificador do provedor para evitar duplicidade."""
    return provider.strip().casefold()


class EventIdentityConflictError(ValueError):
    """Um identificador externo já está associado a outro evento interno."""


class CalendarRepository:
    """Armazena eventos, versões históricas e identificadores externos."""

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
        row = self._connection.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Agrupa escritas em uma transação; chamadas aninhadas são unidas."""
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
                f"Banco com schema {current_version}, mais novo que o suportado "
                f"({SCHEMA_VERSION}). Atualize o Fla10-Agents antes de usá-lo."
            )

        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sports_events (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    identity_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_versions (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    change_summary TEXT,
                    FOREIGN KEY (event_id)
                        REFERENCES sports_events(event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_event_versions_event
                    ON event_versions(event_id, version_id);

                CREATE TABLE IF NOT EXISTS external_event_ids (
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY (provider, external_id),
                    FOREIGN KEY (event_id)
                        REFERENCES sports_events(event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_external_ids_event
                    ON external_event_ids(event_id);

                CREATE TABLE IF NOT EXISTS calendar_runs (
                    run_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_url TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    created INTEGER NOT NULL DEFAULT 0,
                    updated INTEGER NOT NULL DEFAULT 0,
                    unchanged INTEGER NOT NULL DEFAULT 0,
                    rejected INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                """
            )

            self._migrate_identity_key()

            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sports_events_identity
                    ON sports_events(identity_key)
                """
            )

        if current_version < SCHEMA_VERSION:
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate_identity_key(self) -> None:
        """Cria e preenche a chave de identidade em bancos anteriores."""
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(sports_events)")
        }

        if "identity_key" not in columns:
            self._connection.execute(
                "ALTER TABLE sports_events ADD COLUMN identity_key TEXT"
            )

        rows = self._connection.execute(
            "SELECT event_id, payload FROM sports_events WHERE identity_key IS NULL"
        ).fetchall()

        for row in rows:
            event = SportsEvent.model_validate_json(row["payload"])
            self._connection.execute(
                "UPDATE sports_events SET identity_key = ? WHERE event_id = ?",
                (_identity_key(event), row["event_id"]),
            )

    def save_event(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
    ) -> bool:
        """Salva evento; retorna True apenas se criar ou alterar o registro."""
        with self.transaction():
            return self._save_event(event, change_summary)

    def _save_event(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
    ) -> bool:
        """Executa a gravação dentro da transação ativa."""
        payload = event.model_dump_json()
        identity_key = _identity_key(event)
        now = self._now()
        current = self._connection.execute(
            "SELECT payload FROM sports_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()

        if current is not None:
            previous_event = SportsEvent.model_validate_json(current["payload"])
            if not compare_events(previous_event, event):
                self._connection.execute(
                    """
                    UPDATE sports_events
                    SET payload = ?, identity_key = ?, updated_at = ?
                    WHERE event_id = ?
                    """,
                    (payload, identity_key, now, event.event_id),
                )
                return False

        if current is None:
            self._connection.execute(
                """
                INSERT INTO sports_events
                    (event_id, payload, identity_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event.event_id, payload, identity_key, now, now),
            )
        else:
            self._connection.execute(
                """
                UPDATE sports_events
                SET payload = ?, identity_key = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (payload, identity_key, now, event.event_id),
            )

        self._connection.execute(
            """
            INSERT INTO event_versions
                (event_id, payload, recorded_at, change_summary)
            VALUES (?, ?, ?, ?)
            """,
            (event.event_id, payload, now, change_summary),
        )
        return True

    def save_event_and_link_external_id(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
        provider: str | None = None,
        external_id: str | None = None,
    ) -> bool:
        """Salva o evento e seu vínculo externo em uma única transação."""
        if (provider is None) != (external_id is None):
            raise ValueError("provider e external_id devem ser informados em conjunto.")
        if provider is not None and (
            not provider.strip() or not external_id or not external_id.strip()
        ):
            raise ValueError("provider e external_id não podem ser vazios.")

        with self.transaction():
            changed = self._save_event(event, change_summary)
            if provider is not None and external_id is not None:
                self._link_external_id(provider, external_id, event.event_id)
            return changed

    def resolve_event_identity(
        self,
        observation: SportsEvent,
        provider: str | None = None,
        external_id: str | None = None,
    ) -> EventIdentityResolution:
        """Resolve a observação sem criar ou atualizar eventos.

        Uma associação externa só é criada quando há exatamente um
        candidato compatível. A criação do evento permanece a cargo
        do agente.
        """
        if (provider is None) != (external_id is None):
            raise ValueError("provider e external_id devem ser informados em conjunto.")

        if provider is not None and (
            not provider.strip() or not external_id or not external_id.strip()
        ):
            raise ValueError("provider e external_id não podem ser vazios.")

        if provider is not None and external_id is not None:
            linked_event = self.get_event_by_external_id(
                provider,
                external_id,
            )
            if linked_event is not None:
                if not _same_event_identity(linked_event, observation):
                    return EventIdentityResolution(
                        status=IdentityResolutionStatus.CONFLICT,
                        event=linked_event,
                        candidates=(linked_event,),
                        reason=(
                            "O identificador externo já está associado "
                            "a um evento com identidade esportiva incompatível."
                        ),
                    )

                return EventIdentityResolution(
                    status=IdentityResolutionStatus.MATCHED,
                    event=linked_event,
                    candidates=(linked_event,),
                )

        candidates = tuple(
            event for event in self._events_with_identity_key(observation)
            if _same_event_identity(event, observation)
        )

        if len(candidates) > 1:
            return EventIdentityResolution(
                status=IdentityResolutionStatus.AMBIGUOUS,
                event=None,
                candidates=candidates,
                reason="Mais de um evento satisfaz os critérios de identidade.",
            )

        if not candidates:
            return EventIdentityResolution(
                status=IdentityResolutionStatus.NEW,
                event=None,
                reason="Nenhum evento existente corresponde à observação.",
            )

        matched_event = candidates[0]

        return EventIdentityResolution(
            status=IdentityResolutionStatus.MATCHED,
            event=matched_event,
            candidates=candidates,
        )

    def _events_with_identity_key(self, observation: SportsEvent) -> list[SportsEvent]:
        """Busca candidatos usando o índice, sem varrer toda a tabela."""
        rows = self._connection.execute(
            """
            SELECT payload FROM sports_events
            WHERE identity_key = ?
            ORDER BY event_id
            """,
            (_identity_key(observation),),
        ).fetchall()

        return [SportsEvent.model_validate_json(row["payload"]) for row in rows]

    def get_event(self, event_id: str) -> SportsEvent | None:
        row = self._connection.execute(
            "SELECT payload FROM sports_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

        if row is None:
            return None

        return SportsEvent.model_validate_json(row["payload"])

    def list_events(self) -> list[SportsEvent]:
        rows = self._connection.execute(
            "SELECT payload FROM sports_events ORDER BY event_id"
        ).fetchall()

        return [SportsEvent.model_validate_json(row["payload"]) for row in rows]

    def link_external_id(
        self,
        provider: str,
        external_id: str,
        event_id: str,
    ) -> None:
        """Associa ID externo sem permitir remapeamento silencioso."""
        with self.transaction():
            self._link_external_id(provider, external_id, event_id)

    def _link_external_id(
        self,
        provider: str,
        external_id: str,
        event_id: str,
    ) -> None:
        """Executa a associação dentro da transação ativa."""
        event = self._connection.execute(
            "SELECT 1 FROM sports_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if event is None:
            raise KeyError(f"Evento interno inexistente: {event_id}")

        normalized_provider = _normalize_provider(provider)
        normalized_external_id = external_id.strip()

        existing = self._connection.execute(
            """
            SELECT event_id FROM external_event_ids
            WHERE provider = ? AND external_id = ?
            """,
            (normalized_provider, normalized_external_id),
        ).fetchone()

        if existing is not None:
            if existing["event_id"] != event_id:
                raise EventIdentityConflictError(
                    f"O identificador {normalized_provider}:{normalized_external_id} "
                    f"já pertence ao evento {existing['event_id']}."
                )
            return

        self._connection.execute(
            """
            INSERT INTO external_event_ids
                (provider, external_id, event_id, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_provider, normalized_external_id, event_id, self._now()),
        )

    def get_event_by_external_id(
        self,
        provider: str,
        external_id: str,
    ) -> SportsEvent | None:
        row = self._connection.execute(
            """
            SELECT e.payload
            FROM sports_events AS e
            JOIN external_event_ids AS x ON x.event_id = e.event_id
            WHERE x.provider = ? AND x.external_id = ?
            """,
            (_normalize_provider(provider), external_id.strip()),
        ).fetchone()

        if row is None:
            return None

        return SportsEvent.model_validate_json(row["payload"])

    def event_history(self, event_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """
            SELECT version_id, payload, recorded_at, change_summary
            FROM event_versions
            WHERE event_id = ?
            ORDER BY version_id
            """,
            (event_id,),
        ).fetchall()

        return [
            {
                "version_id": row["version_id"],
                "event": SportsEvent.model_validate_json(row["payload"]),
                "recorded_at": row["recorded_at"],
                "change_summary": row["change_summary"],
            }
            for row in rows
        ]

    def start_run(
        self,
        provider: str,
        source_url: str | None = None,
    ) -> str:
        """Registra o início de uma execução de coleta ou importação."""
        run_id = str(uuid4())

        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO calendar_runs
                    (run_id, provider, source_url, started_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, _normalize_provider(provider), source_url, self._now(), "running"),
            )

        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        created: int = 0,
        updated: int = 0,
        unchanged: int = 0,
        rejected: int = 0,
        error: str | None = None,
    ) -> None:
        """Encerra o registro da execução com os totais obtidos."""
        with self.transaction():
            self._connection.execute(
                """
                UPDATE calendar_runs
                SET finished_at = ?, status = ?, created = ?, updated = ?,
                    unchanged = ?, rejected = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    self._now(),
                    status,
                    created,
                    updated,
                    unchanged,
                    rejected,
                    error,
                    run_id,
                ),
            )

    def list_runs(self, limit: int = 20) -> list[dict[str, object]]:
        """Lista as execuções mais recentes, da mais nova para a mais antiga."""
        rows = self._connection.execute(
            """
            SELECT run_id, provider, source_url, started_at, finished_at,
                   status, created, updated, unchanged, rejected, error
            FROM calendar_runs
            ORDER BY started_at DESC, run_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]
