from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.knowledge_gap.models import KnowledgeGap, KnowledgeGapAuditEvent


class KnowledgeGapRepositoryError(Exception):
    """Safe persistence error used by the chat orchestration boundary."""


class KnowledgeGapRepository(ABC):
    @abstractmethod
    async def create(self, gap: KnowledgeGap) -> KnowledgeGap: ...


class JsonlKnowledgeGapRepository(KnowledgeGapRepository):
    """Append-only local candidate store; it has no publication capability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def create(self, gap: KnowledgeGap) -> KnowledgeGap:
        async with self._lock:
            try:
                await asyncio.to_thread(self._append_atomically, gap)
            except OSError as exc:
                raise KnowledgeGapRepositoryError(
                    "knowledge-gap candidate persistence failed"
                ) from exc
        return gap

    def _append_atomically(self, gap: KnowledgeGap) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._path.read_bytes() if self._path.exists() else b""
        serialized = json.dumps(
            gap.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        temporary = self._path.with_name(f".{self._path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(existing + serialized)
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)


class KnowledgeGapNotFoundError(KnowledgeGapRepositoryError):
    pass


class KnowledgeGapConflictError(KnowledgeGapRepositoryError):
    pass


class SqliteKnowledgeGapRepository(KnowledgeGapRepository):
    """SQLite materialized records plus append-only audit events for the MVP."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_gaps (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_status_created
                ON knowledge_gaps(status, created_at DESC);
                CREATE TABLE IF NOT EXISTS knowledge_gap_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gap_id TEXT NOT NULL REFERENCES knowledge_gaps(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    async def create(self, gap: KnowledgeGap) -> KnowledgeGap:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._create_sync, gap)
            except sqlite3.Error as exc:
                raise KnowledgeGapRepositoryError("knowledge-gap persistence failed") from exc

    def _create_sync(self, gap: KnowledgeGap) -> KnowledgeGap:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO knowledge_gaps VALUES (?, ?, ?, ?, ?, ?)",
                (
                    gap.id,
                    self._dump(gap.model_dump(mode="json")),
                    gap.status,
                    gap.version,
                    gap.created_at.isoformat(),
                    now,
                ),
            )
            self._insert_event(connection, gap.id, "created", "system", {})
        return gap

    async def get(self, gap_id: str) -> KnowledgeGap:
        try:
            return await asyncio.to_thread(self._get_sync, gap_id)
        except sqlite3.Error as exc:
            raise KnowledgeGapRepositoryError("knowledge-gap read failed") from exc

    def _get_sync(self, gap_id: str) -> KnowledgeGap:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM knowledge_gaps WHERE id = ?", (gap_id,)
            ).fetchone()
        if row is None:
            raise KnowledgeGapNotFoundError("knowledge gap not found")
        return KnowledgeGap.model_validate(json.loads(row["payload_json"]))

    async def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeGap], int]:
        try:
            return await asyncio.to_thread(
                self._list_sync, status=status, query=query, limit=limit, offset=offset
            )
        except sqlite3.Error as exc:
            raise KnowledgeGapRepositoryError("knowledge-gap list failed") from exc

    def _list_sync(
        self, *, status: str | None, query: str | None, limit: int, offset: int
    ) -> tuple[list[KnowledgeGap], int]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status = ?")
            values.append(status)
        if query:
            clauses.append("payload_json LIKE ?")
            values.append(f"%{query}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM knowledge_gaps{where}", values  # noqa: S608
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT payload_json FROM knowledge_gaps{where} "  # noqa: S608
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return [KnowledgeGap.model_validate(json.loads(row[0])) for row in rows], total

    async def update(
        self,
        gap: KnowledgeGap,
        *,
        expected_version: int,
        allowed_statuses: set[str],
        event_type: str,
        actor: str,
        details: dict[str, object] | None = None,
    ) -> KnowledgeGap:
        async with self._lock:
            try:
                return await asyncio.to_thread(
                    self._update_sync,
                    gap,
                    expected_version,
                    allowed_statuses,
                    event_type,
                    actor,
                    details or {},
                )
            except sqlite3.Error as exc:
                raise KnowledgeGapRepositoryError("knowledge-gap update failed") from exc

    def _update_sync(
        self,
        gap: KnowledgeGap,
        expected_version: int,
        allowed_statuses: set[str],
        event_type: str,
        actor: str,
        details: dict[str, object],
    ) -> KnowledgeGap:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT status, version FROM knowledge_gaps WHERE id = ?", (gap.id,)
            ).fetchone()
            if current is None:
                raise KnowledgeGapNotFoundError("knowledge gap not found")
            version_changed = int(current["version"]) != expected_version
            status_changed = current["status"] not in allowed_statuses
            if version_changed or status_changed:
                raise KnowledgeGapConflictError("knowledge gap state changed")
            updated = gap.model_copy(update={"version": expected_version + 1})
            cursor = connection.execute(
                "UPDATE knowledge_gaps SET payload_json = ?, status = ?, version = ?, "
                "updated_at = ? WHERE id = ? AND version = ?",
                (
                    self._dump(updated.model_dump(mode="json")),
                    updated.status,
                    updated.version,
                    datetime.now(timezone.utc).isoformat(),
                    updated.id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise KnowledgeGapConflictError("knowledge gap state changed")
            self._insert_event(connection, updated.id, event_type, actor, details)
        return updated

    async def audit_events(self, gap_id: str) -> list[KnowledgeGapAuditEvent]:
        return await asyncio.to_thread(self._audit_events_sync, gap_id)

    def _audit_events_sync(self, gap_id: str) -> list[KnowledgeGapAuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_gap_audit_events WHERE gap_id = ? ORDER BY id",
                (gap_id,),
            ).fetchall()
        return [
            KnowledgeGapAuditEvent(
                id=row["id"],
                gap_id=row["gap_id"],
                event_type=row["event_type"],
                actor=row["actor"],
                details=json.loads(row["details_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        gap_id: str,
        event_type: str,
        actor: str,
        details: dict[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO knowledge_gap_audit_events "
            "(gap_id, event_type, actor, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                gap_id,
                event_type,
                actor,
                self._dump(details),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
