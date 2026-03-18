from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_message_id INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    UNIQUE(document_path, chunk_index)
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    chunk_id INTEGER PRIMARY KEY,
                    vector_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_run_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    artifact_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, step_index)
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def ensure_conversation(self, conversation_id: str, title: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (conversation_id, title, now, now),
            )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        attachments = attachments or []
        metadata = metadata or {}
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages(conversation_id, role, content, attachments_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, json.dumps(attachments), json.dumps(metadata), now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now, conversation_id),
            )
            return int(cur.lastrowid)

    def list_messages(self, conversation_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    def list_conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*,
                    (SELECT content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS last_message
                FROM conversations c
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def save_memory(self, kind: str, content: str, source_message_id: int | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memories(kind, content, source_message_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (kind, content, source_message_id, utc_now()),
            )

    def list_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_document(self, path: str, sha256: str, size_bytes: int, chunks: list[str]) -> None:
        with self.connect() as conn:
            old_chunk_rows = conn.execute("SELECT id FROM chunks WHERE document_path=?", (path,)).fetchall()
            for row in old_chunk_rows:
                conn.execute("DELETE FROM embeddings WHERE chunk_id=?", (row["id"],))
            conn.execute("DELETE FROM chunks WHERE document_path=?", (path,))
            conn.execute(
                """
                INSERT INTO documents(path, sha256, size_bytes, indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    indexed_at=excluded.indexed_at
                """,
                (path, sha256, size_bytes, utc_now()),
            )
            for index, chunk in enumerate(chunks):
                conn.execute(
                    """
                    INSERT INTO chunks(document_path, chunk_index, content, token_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (path, index, chunk, len(chunk.split())),
                )

    def get_documents(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY path").fetchall()
        return [dict(row) for row in rows]

    def get_chunks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM chunks").fetchall()
        return [dict(row) for row in rows]

    def save_embedding(self, chunk_id: int, vector: list[float], model: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings(chunk_id, vector_json, model, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    vector_json=excluded.vector_json,
                    model=excluded.model,
                    created_at=excluded.created_at
                """,
                (chunk_id, json.dumps(vector), model, utc_now()),
            )

    def get_chunks_with_embeddings(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, e.vector_json, e.model AS embedding_model
                FROM chunks c
                LEFT JOIN embeddings e ON e.chunk_id = c.id
                """
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            vector_json = item.pop("vector_json", None)
            item["vector"] = json.loads(vector_json) if vector_json else None
            items.append(item)
        return items

    def add_telemetry(self, kind: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO telemetry(kind, payload_json, created_at) VALUES (?, ?, ?)",
                (kind, json.dumps(payload), utc_now()),
            )

    def list_telemetry(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM telemetry ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            results.append(item)
        return results

    def upsert_task_run(
        self,
        run_id: str,
        conversation_id: str,
        mode: str,
        title: str,
        status: str,
        progress: float,
        summary: str,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO task_runs(id, conversation_id, mode, title, status, progress, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    progress=excluded.progress,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                (run_id, conversation_id, mode, title, status, progress, summary, now, now),
            )

    def replace_task_steps(self, run_id: str, steps: list[dict[str, Any]]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute("DELETE FROM task_run_steps WHERE run_id=?", (run_id,))
            for index, step in enumerate(steps):
                conn.execute(
                    """
                    INSERT INTO task_run_steps(run_id, step_index, title, status, details, artifact_path, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        index,
                        step["title"],
                        step.get("status", "pending"),
                        step.get("details", ""),
                        step.get("artifact_path"),
                        now,
                        now,
                    ),
                )

    def list_task_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as conn:
            runs = conn.execute(
                "SELECT * FROM task_runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for run in runs:
                item = dict(run)
                steps = conn.execute(
                    "SELECT * FROM task_run_steps WHERE run_id=? ORDER BY step_index",
                    (item["id"],),
                ).fetchall()
                item["steps"] = [dict(step) for step in steps]
                results.append(item)
            return results

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (key, json.dumps(value), utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key=?",
                (key,),
            ).fetchone()
        if not row:
            return default
        return json.loads(row["value_json"])

    def get_all_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value_json FROM app_settings ORDER BY key").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["attachments"] = json.loads(item.pop("attachments_json"))
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item
