from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

GraphJobStatus = Literal["queued", "running", "completed", "failed"]


class GraphJob(BaseModel):
    id: str
    kind: Literal["rebuild", "publish"]
    status: GraphJobStatus
    payload: dict[str, Any]
    stage: str = "queued"
    progress: float = Field(default=0, ge=0, le=1)
    processed_chunks: int = 0
    total_chunks: int = 0
    attempts: int = 0
    lease_expires_at: datetime | None = None
    result_graph_version: str | None = None
    result_index_version: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class GraphJobRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL,
                    processed_chunks INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    lease_expires_at TEXT,
                    result_graph_version TEXT,
                    result_index_version TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_graph_jobs_queue
                ON graph_jobs(status, created_at);
                """
            )

    async def enqueue(
        self,
        kind: Literal["rebuild", "publish"],
        payload: dict[str, Any],
        *,
        signature: str,
    ) -> GraphJob:
        return await asyncio.to_thread(self._enqueue_sync, kind, payload, signature)

    def _enqueue_sync(self, kind, payload, signature) -> GraphJob:
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM graph_jobs WHERE signature = ? "
                "AND status IN ('queued', 'running') ORDER BY created_at LIMIT 1",
                (signature,),
            ).fetchone()
            if existing:
                return _job(existing)
            job_id = uuid4().hex
            connection.execute(
                "INSERT INTO graph_jobs VALUES (?, ?, 'queued', ?, ?, 'queued', "
                "0, 0, 0, 0, NULL, NULL, NULL, NULL, ?, ?)",
                (job_id, kind, signature, json.dumps(payload), now.isoformat(), now.isoformat()),
            )
            row = connection.execute("SELECT * FROM graph_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row)

    async def get(self, job_id: str) -> GraphJob | None:
        return await asyncio.to_thread(self._get_sync, job_id)

    def _get_sync(self, job_id: str) -> GraphJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM graph_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row) if row else None

    async def claim(self, lease_seconds: int) -> GraphJob | None:
        return await asyncio.to_thread(self._claim_sync, lease_seconds)

    def _claim_sync(self, lease_seconds: int) -> GraphJob | None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=lease_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE graph_jobs SET status = 'queued', stage = 'recovered', "
                "lease_expires_at = NULL, updated_at = ? "
                "WHERE status = 'running' AND lease_expires_at < ?",
                (now.isoformat(), now.isoformat()),
            )
            row = connection.execute(
                "SELECT id FROM graph_jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE graph_jobs SET status = 'running', stage = 'starting', "
                "attempts = attempts + 1, lease_expires_at = ?, updated_at = ? WHERE id = ?",
                (expires.isoformat(), now.isoformat(), row["id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM graph_jobs WHERE id = ?", (row["id"],)
            ).fetchone()
        return _job(claimed)

    async def update(self, job_id: str, **values: Any) -> GraphJob:
        return await asyncio.to_thread(self._update_sync, job_id, values)

    def _update_sync(self, job_id: str, values: dict[str, Any]) -> GraphJob:
        allowed = {
            "status", "stage", "progress", "processed_chunks", "total_chunks",
            "lease_expires_at", "result_graph_version", "result_index_version", "error",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        for key, value in list(updates.items()):
            if isinstance(value, datetime):
                updates[key] = value.isoformat()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE graph_jobs SET {assignments} WHERE id = ?",  # noqa: S608
                (*updates.values(), job_id),
            )
            row = connection.execute("SELECT * FROM graph_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise LookupError("graph job not found")
        return _job(row)


def _job(row: sqlite3.Row) -> GraphJob:
    return GraphJob(
        id=row["id"], kind=row["kind"], status=row["status"],
        payload=json.loads(row["payload_json"]), stage=row["stage"],
        progress=row["progress"], processed_chunks=row["processed_chunks"],
        total_chunks=row["total_chunks"], attempts=row["attempts"],
        lease_expires_at=_date(row["lease_expires_at"]),
        result_graph_version=row["result_graph_version"],
        result_index_version=row["result_index_version"], error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
