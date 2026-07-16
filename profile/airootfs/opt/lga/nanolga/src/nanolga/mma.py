"""MMA: auditable event log and curated semantic memory."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    utc_now,
)


CORE_WRITER_ROLE = "lga_core"


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """Conservative provisional policy; thresholds remain configurable."""

    confirmation_threshold: int = 3
    activation_confidence: float = 0.80
    contradiction_threshold: int = 2
    retrieval_limit: int = 8
    context_budget_chars: int = 6_000


class MemoryManager:
    def __init__(self, database_path: str | Path, policy: MemoryPolicy | None = None):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.policy = policy or MemoryPolicy()
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_task
                    ON event_log(task_id, id);

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    source_task_id TEXT NOT NULL,
                    importance REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    relations_json TEXT NOT NULL,
                    confirmations INTEGER NOT NULL,
                    contradictions INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_confirmed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memory_retrieval
                    ON semantic_memory(status, domain, importance, confidence);
                """
            )

    def append_event(
        self, task_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> int:
        """Append immutable telemetry. This is not semantic-memory curation."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO event_log(task_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    task_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    utc_now(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an event row id")
            return int(cursor.lastrowid)

    def store_semantic(
        self, memory: MemoryRecord, *, writer_role: str
    ) -> str:
        """Persist curated memory and reject direct writes from AGPs."""
        if writer_role != CORE_WRITER_ROLE:
            raise PermissionError("only the LGA Core may curate semantic memory")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO semantic_memory(
                    memory_id, content, kind, domain, source_task_id,
                    importance, confidence, status, origin, relations_json,
                    confirmations, contradictions, created_at, last_confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.memory_id,
                    memory.content,
                    memory.kind.value,
                    memory.domain,
                    memory.source_task_id,
                    memory.importance,
                    memory.confidence,
                    memory.status.value,
                    memory.origin,
                    json.dumps(memory.relations, ensure_ascii=False),
                    memory.confirmations,
                    memory.contradictions,
                    memory.created_at,
                    memory.last_confirmed_at,
                ),
            )
        return memory.memory_id

    def retrieve(
        self,
        query: str,
        *,
        domain: str = "general",
        limit: int | None = None,
        context_budget_chars: int | None = None,
    ) -> list[MemoryRecord]:
        limit = limit or self.policy.retrieval_limit
        budget = context_budget_chars or self.policy.context_budget_chars
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM semantic_memory
                WHERE status = ? AND (domain = ? OR domain = 'general')
                ORDER BY importance DESC, confidence DESC, created_at DESC
                LIMIT 200
                """,
                (MemoryStatus.ACTIVE.value, domain),
            ).fetchall()

        terms = set(re.findall(r"[\wÀ-ÿ]{3,}", query.lower()))

        def score(row: sqlite3.Row) -> float:
            content = str(row["content"]).lower()
            overlap = sum(1 for term in terms if term in content)
            return overlap * 2.0 + float(row["importance"]) + float(row["confidence"])

        selected: list[MemoryRecord] = []
        used_chars = 0
        for row in sorted(rows, key=score, reverse=True):
            if terms and score(row) < 1.0:
                continue
            record = self._row_to_memory(row)
            if used_chars + len(record.content) > budget:
                continue
            selected.append(record)
            used_chars += len(record.content)
            if len(selected) >= limit:
                break
        return selected

    def list_memories(
        self, *, status: MemoryStatus | None = None, limit: int = 100
    ) -> list[MemoryRecord]:
        query = "SELECT * FROM semantic_memory"
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (max(1, min(limit, 1_000)),)
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def record_feedback(self, memory_id: str, *, confirmed: bool) -> MemoryRecord:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM semantic_memory WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown memory: {memory_id}")
            confirmations = int(row["confirmations"]) + (1 if confirmed else 0)
            contradictions = int(row["contradictions"]) + (0 if confirmed else 1)
            confidence = float(row["confidence"])
            confidence = min(1.0, confidence + 0.07) if confirmed else max(0.0, confidence - 0.20)
            status = MemoryStatus(str(row["status"]))
            if (
                confirmations >= self.policy.confirmation_threshold
                and contradictions == 0
                and confidence >= self.policy.activation_confidence
            ):
                status = MemoryStatus.ACTIVE
            elif contradictions >= self.policy.contradiction_threshold:
                status = MemoryStatus.STALE
            self._connection.execute(
                """
                UPDATE semantic_memory
                SET confirmations = ?, contradictions = ?, confidence = ?,
                    status = ?, last_confirmed_at = ?
                WHERE memory_id = ?
                """,
                (
                    confirmations,
                    contradictions,
                    confidence,
                    status.value,
                    utc_now() if confirmed else row["last_confirmed_at"],
                    memory_id,
                ),
            )
            updated = self._connection.execute(
                "SELECT * FROM semantic_memory WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        return self._row_to_memory(updated)

    def idle_learning(self) -> Mapping[str, int]:
        """Conservative delta pass: identify, but never auto-promote, candidates."""
        with self._lock:
            candidate_count = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM semantic_memory WHERE status = ?",
                    (MemoryStatus.CANDIDATE.value,),
                ).fetchone()[0]
            )
            stale_count = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM semantic_memory WHERE status = ?",
                    (MemoryStatus.STALE.value,),
                ).fetchone()[0]
            )
        return {
            "candidates_awaiting_evidence": candidate_count,
            "stale_memories": stale_count,
            "auto_promoted": 0,
        }

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=str(row["memory_id"]),
            content=str(row["content"]),
            kind=MemoryKind(str(row["kind"])),
            domain=str(row["domain"]),
            source_task_id=str(row["source_task_id"]),
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
            status=MemoryStatus(str(row["status"])),
            origin=str(row["origin"]),
            relations=tuple(json.loads(row["relations_json"])),
            confirmations=int(row["confirmations"]),
            contradictions=int(row["contradictions"]),
            created_at=str(row["created_at"]),
            last_confirmed_at=row["last_confirmed_at"],
        )
