from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProductRepository:
    def __init__(self, database_url: str) -> None:
        if database_url == "sqlite://":
            database = ":memory:"
        elif database_url.startswith("sqlite:///"):
            database = database_url.removeprefix("sqlite:///")
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        else:
            raise ValueError("ProductRepository currently requires SQLite")
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()

    def initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluation_projects (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                    description TEXT NOT NULL, job_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_evaluation_projects_owner
                    ON evaluation_projects(owner, updated_at);
                CREATE TABLE IF NOT EXISTS ai_providers (
                    id TEXT NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
                    base_url TEXT NOT NULL, model TEXT NOT NULL, key_hint TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(id, owner)
                );
                CREATE TABLE IF NOT EXISTS ai_calls (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, provider_id TEXT NOT NULL,
                    model TEXT NOT NULL, status TEXT NOT NULL, prompt_preview TEXT NOT NULL,
                    response_preview TEXT, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ai_calls_owner ON ai_calls(owner, created_at);
                """
            )

    def create_project(self, owner: str, name: str, description: str, job_ids: list[str]) -> dict:
        project_id = f"project-{uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO evaluation_projects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, owner, name, description, json.dumps(job_ids), now, now),
            )
        return self.get_project(owner, project_id)  # type: ignore[return-value]

    def list_projects(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM evaluation_projects WHERE owner=? ORDER BY updated_at DESC", (owner,)
            ).fetchall()
        return [self._project(row) for row in rows]

    def get_project(self, owner: str, project_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM evaluation_projects WHERE owner=? AND id=?", (owner, project_id)
            ).fetchone()
        return None if row is None else self._project(row)

    def upsert_provider(
        self,
        owner: str,
        provider_id: str,
        name: str,
        base_url: str,
        model: str,
        key_hint: str | None,
    ) -> dict:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO ai_providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, owner) DO UPDATE SET name=excluded.name,
                base_url=excluded.base_url, model=excluded.model,
                key_hint=COALESCE(excluded.key_hint, ai_providers.key_hint), updated_at=excluded.updated_at""",
                (provider_id, owner, name, base_url, model, key_hint, now, now),
            )
        return self.get_provider(owner, provider_id)  # type: ignore[return-value]

    def get_provider(self, owner: str, provider_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM ai_providers WHERE owner=? AND id=?", (owner, provider_id)
            ).fetchone()
        return None if row is None else dict(row)

    def list_providers(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_providers WHERE owner=? ORDER BY updated_at DESC", (owner,)
            ).fetchall()
        return [dict(row) for row in rows]

    def add_call(
        self,
        owner: str,
        provider_id: str,
        model: str,
        status: str,
        prompt_preview: str,
        response_preview: str | None,
    ) -> dict:
        record = {
            "id": f"call-{uuid4().hex[:16]}",
            "owner": owner,
            "provider_id": provider_id,
            "model": model,
            "status": status,
            "prompt_preview": prompt_preview,
            "response_preview": response_preview,
            "created_at": _now(),
        }
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ai_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(record.values())
            )
        return record

    def list_calls(self, owner: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_calls WHERE owner=? ORDER BY created_at DESC LIMIT ?",
                (owner, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _project(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["job_ids"] = json.loads(value.pop("job_ids_json"))
        return value
