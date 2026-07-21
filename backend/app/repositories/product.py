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
                CREATE TABLE IF NOT EXISTS ai_provider_models (
                    provider_id TEXT NOT NULL, owner TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, owner, model),
                    FOREIGN KEY(provider_id, owner) REFERENCES ai_providers(id, owner)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_ai_provider_models_owner
                    ON ai_provider_models(owner, provider_id, created_at);
                CREATE TABLE IF NOT EXISTS ai_calls (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, provider_id TEXT NOT NULL,
                    model TEXT NOT NULL, status TEXT NOT NULL, prompt_preview TEXT NOT NULL,
                    response_preview TEXT, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ai_calls_owner ON ai_calls(owner, created_at);
                CREATE TABLE IF NOT EXISTS ai_prompt_templates (
                    id TEXT NOT NULL, owner TEXT NOT NULL, system_prompt TEXT NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY(id, owner)
                );
                CREATE TABLE IF NOT EXISTS ai_custom_prompt_templates (
                    id TEXT NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
                    description TEXT NOT NULL, system_prompt TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(id, owner)
                );
                CREATE TABLE IF NOT EXISTS ai_chat_sessions (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                    provider_id TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ai_chat_sessions_owner
                    ON ai_chat_sessions(owner, updated_at);
                CREATE TABLE IF NOT EXISTS ai_chat_messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL,
                    evidence_job_ids_json TEXT NOT NULL,
                    evidence_repository_ids_json TEXT NOT NULL,
                    template_id TEXT, created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES ai_chat_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_ai_chat_messages_session
                    ON ai_chat_messages(owner, session_id, created_at);
                INSERT OR IGNORE INTO ai_provider_models(provider_id, owner, model, created_at)
                    SELECT id, owner, model, created_at FROM ai_providers;
                """
            )

    def list_prompt_templates(self, owner: str) -> dict[str, str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, system_prompt FROM ai_prompt_templates WHERE owner=?", (owner,)
            ).fetchall()
        return {str(row["id"]): str(row["system_prompt"]) for row in rows}

    def upsert_prompt_template(self, owner: str, template_id: str, system_prompt: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO ai_prompt_templates VALUES (?, ?, ?, ?)
                ON CONFLICT(id, owner) DO UPDATE SET
                system_prompt=excluded.system_prompt, updated_at=excluded.updated_at""",
                (template_id, owner, system_prompt, _now()),
            )

    def delete_prompt_template(self, owner: str, template_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM ai_prompt_templates WHERE owner=? AND id=?", (owner, template_id)
            )

    def list_custom_prompt_templates(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_custom_prompt_templates WHERE owner=? ORDER BY updated_at DESC",
                (owner,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_custom_prompt_template(self, owner: str, template_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM ai_custom_prompt_templates WHERE owner=? AND id=?",
                (owner, template_id),
            ).fetchone()
        return None if row is None else dict(row)

    def create_custom_prompt_template(self, owner: str, template_id: str, name: str, description: str, system_prompt: str) -> dict:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ai_custom_prompt_templates VALUES (?, ?, ?, ?, ?, ?, ?)",
                (template_id, owner, name, description, system_prompt, now, now),
            )
        return self.get_custom_prompt_template(owner, template_id)  # type: ignore[return-value]

    def update_custom_prompt_template(self, owner: str, template_id: str, system_prompt: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE ai_custom_prompt_templates SET system_prompt=?, updated_at=? WHERE owner=? AND id=?",
                (system_prompt, _now(), owner, template_id),
            )
        return cursor.rowcount == 1

    def delete_custom_prompt_template(self, owner: str, template_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM ai_custom_prompt_templates WHERE owner=? AND id=?", (owner, template_id)
            )
        return cursor.rowcount == 1

    def create_chat_session(self, owner: str, title: str, provider_id: str, model: str) -> dict:
        session_id = f"session-{uuid4().hex[:24]}"
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ai_chat_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, owner, title, provider_id, model, now, now),
            )
        return self.get_chat_session(owner, session_id)  # type: ignore[return-value]

    def get_chat_session(self, owner: str, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM ai_chat_sessions WHERE owner=? AND id=?", (owner, session_id)
            ).fetchone()
        return None if row is None else dict(row)

    def list_chat_sessions(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT s.*, COUNT(m.id) AS message_count FROM ai_chat_sessions s
                LEFT JOIN ai_chat_messages m ON m.session_id=s.id AND m.owner=s.owner
                WHERE s.owner=? GROUP BY s.id ORDER BY s.updated_at DESC""", (owner,)
            ).fetchall()
        return [dict(row) for row in rows]

    def add_chat_message(self, owner: str, session_id: str, role: str, content: str, job_ids: list[str], repository_ids: list[str], template_id: str | None) -> dict:
        message_id = f"message-{uuid4().hex[:24]}"
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ai_chat_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (message_id, session_id, owner, role, content, json.dumps(job_ids), json.dumps(repository_ids), template_id, now),
            )
            self._connection.execute(
                "UPDATE ai_chat_sessions SET updated_at=? WHERE owner=? AND id=?",
                (now, owner, session_id),
            )
        return self.list_chat_messages(owner, session_id)[-1]

    def list_chat_messages(self, owner: str, session_id: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_chat_messages WHERE owner=? AND session_id=? ORDER BY created_at, id",
                (owner, session_id),
            ).fetchall()
        return [{**dict(row), "evidence_job_ids": json.loads(row["evidence_job_ids_json"]), "evidence_repository_ids": json.loads(row["evidence_repository_ids_json"])} for row in rows]

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
            self._connection.execute(
                "INSERT OR IGNORE INTO ai_provider_models VALUES (?, ?, ?, ?)",
                (provider_id, owner, model, now),
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

    def list_provider_models(self, owner: str, provider_id: str) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT model FROM ai_provider_models
                WHERE owner=? AND provider_id=? ORDER BY created_at, model""",
                (owner, provider_id),
            ).fetchall()
        return [str(row["model"]) for row in rows]

    def add_provider_model(self, owner: str, provider_id: str, model: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO ai_provider_models VALUES (?, ?, ?, ?)",
                (provider_id, owner, model, _now()),
            )

    def set_default_provider_model(self, owner: str, provider_id: str, model: str) -> bool:
        with self._lock, self._connection:
            exists = self._connection.execute(
                """SELECT 1 FROM ai_provider_models
                WHERE owner=? AND provider_id=? AND model=?""",
                (owner, provider_id, model),
            ).fetchone()
            if exists is None:
                return False
            self._connection.execute(
                "UPDATE ai_providers SET model=?, updated_at=? WHERE owner=? AND id=?",
                (model, _now(), owner, provider_id),
            )
        return True

    def delete_provider_model(self, owner: str, provider_id: str, model: str) -> str | None:
        with self._lock, self._connection:
            provider = self._connection.execute(
                "SELECT model FROM ai_providers WHERE owner=? AND id=?",
                (owner, provider_id),
            ).fetchone()
            models = self.list_provider_models(owner, provider_id)
            if provider is None or model not in models:
                return None
            if len(models) == 1:
                raise ValueError("provider must keep at least one model")
            self._connection.execute(
                "DELETE FROM ai_provider_models WHERE owner=? AND provider_id=? AND model=?",
                (owner, provider_id, model),
            )
            default_model = str(provider["model"])
            if default_model == model:
                default_model = next(item for item in models if item != model)
                self._connection.execute(
                    "UPDATE ai_providers SET model=?, updated_at=? WHERE owner=? AND id=?",
                    (default_model, _now(), owner, provider_id),
                )
        return default_model

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
