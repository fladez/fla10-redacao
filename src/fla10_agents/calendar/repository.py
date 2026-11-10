"""Persistência SQLite de eventos esportivos e seu histórico."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from fla10_agents.calendar.comparator import compare_events
from fla10_agents.models import SportsEvent


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
    """Normaliza caixa e espaços, sem presumir aliases entre nomes."""
    return " ".join(value.split()).casefold()


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
        self._connection.execute("PRAGMA foreign_keys = ON")
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

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sports_events (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
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
                """
            )

    def save_event(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
    ) -> bool:
        """Salva evento; retorna True apenas se criar ou alterar o registro."""
        with self._connection:
            return self._save_event(event, change_summary)

    def _save_event(
        self,
        event: SportsEvent,
        change_summary: str | None = None,
    ) -> bool:
        """Executa a gravação dentro da transação ativa."""
        payload = event.model_dump_json()
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
                    SET payload = ?, updated_at = ?
                    WHERE event_id = ?
                    """,
                    (payload, now, event.event_id),
                )
                return False

        if current is None:
            self._connection.execute(
                """
                INSERT INTO sports_events
                    (event_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (event.event_id, payload, now, now),
            )
        else:
            self._connection.execute(
                """
                UPDATE sports_events
                SET payload = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (payload, now, event.event_id),
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

        with self._connection:
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
            event for event in self.list_events() if _same_event_identity(event, observation)
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
        with self._connection:
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

        existing = self._connection.execute(
            """
            SELECT event_id FROM external_event_ids
            WHERE provider = ? AND external_id = ?
            """,
            (provider, external_id),
        ).fetchone()

        if existing is not None:
            if existing["event_id"] != event_id:
                raise EventIdentityConflictError(
                    f"O identificador {provider}:{external_id} "
                    f"já pertence ao evento {existing['event_id']}."
                )
            return

        self._connection.execute(
            """
            INSERT INTO external_event_ids
                (provider, external_id, event_id, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (provider, external_id, event_id, self._now()),
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
            (provider, external_id),
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
