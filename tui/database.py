import aiosqlite
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "agent_runner.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Create all database tables if they do not already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_definitions (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT,
                prompt          TEXT NOT NULL,
                tools           TEXT NOT NULL,
                max_turns       INTEGER DEFAULT 20,
                permission_mode TEXT DEFAULT 'acceptEdits',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id                  TEXT PRIMARY KEY,
                agent_id            TEXT NOT NULL,
                session_id          TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                prompt              TEXT NOT NULL,
                result              TEXT,
                stop_reason         TEXT,
                error               TEXT,
                total_input_tokens  INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                started_at          TEXT NOT NULL,
                finished_at         TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS run_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL,
                sequence   INTEGER NOT NULL,
                msg_type   TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def get_setting(key: str, default: str = "") -> str:
    """Return the value for a settings key, or default if not set."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else default


async def set_setting(key: str, value: str) -> None:
    """Upsert a settings key/value pair."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, _now()),
        )
        await db.commit()


async def create_agent(
    name: str,
    description: str | None,
    prompt: str,
    tools: list,
    max_turns: int,
    permission_mode: str,
) -> dict:
    """Insert a new agent definition and return it as a dict."""
    agent_id = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO agent_definitions
                (id, name, description, prompt, tools, max_turns, permission_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (agent_id, name, description, prompt, json.dumps(tools), max_turns, permission_mode, now, now),
        )
        await db.commit()
        async with db.execute("SELECT * FROM agent_definitions WHERE id = ?", (agent_id,)) as cursor:
            row = await cursor.fetchone()
    result = dict(row)
    result["tools"] = json.loads(result["tools"])
    return result


async def get_agents() -> list[dict]:
    """Return all agent definitions ordered by creation date descending."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_definitions ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
    agents = [dict(r) for r in rows]
    for agent in agents:
        agent["tools"] = json.loads(agent["tools"])
    return agents


async def get_agent(id: str) -> dict | None:
    """Return a single agent definition by id, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_definitions WHERE id = ?", (id,)) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    result = dict(row)
    result["tools"] = json.loads(result["tools"])
    return result


async def update_agent(id: str, **kwargs) -> dict:
    """Update the specified fields on an agent and return the updated record."""
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [id]
    if "tools" in kwargs and isinstance(kwargs["tools"], list):
        idx = list(kwargs.keys()).index("tools")
        values[idx] = json.dumps(kwargs["tools"])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            f"UPDATE agent_definitions SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()
        async with db.execute("SELECT * FROM agent_definitions WHERE id = ?", (id,)) as cursor:
            row = await cursor.fetchone()
    result = dict(row)
    result["tools"] = json.loads(result["tools"])
    return result


async def delete_agent(id: str) -> None:
    """Delete an agent definition by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM agent_definitions WHERE id = ?", (id,))
        await db.commit()


async def create_run(agent_id: str, prompt: str) -> dict:
    """Create a new agent run record with status 'pending' and return it."""
    run_id = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO agent_runs
                (id, agent_id, status, prompt, total_input_tokens, total_output_tokens, started_at)
            VALUES (?, ?, 'pending', ?, 0, 0, ?)
            """,
            (run_id, agent_id, prompt, now),
        )
        await db.commit()
        async with db.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row)


async def get_runs(agent_id: str) -> list[dict]:
    """Return all runs for an agent ordered by start time descending."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_runs WHERE agent_id = ? ORDER BY started_at DESC",
            (agent_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_run(id: str) -> dict | None:
    """Return a single run by id, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_runs WHERE id = ?", (id,)) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def update_run(id: str, **kwargs) -> None:
    """Update the specified fields on a run record."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE agent_runs SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()


async def append_message(run_id: str, sequence: int, msg_type: str, content: dict) -> None:
    """Append a message record for a run, storing content as JSON."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO run_messages (run_id, sequence, msg_type, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, sequence, msg_type, json.dumps(content), _now()),
        )
        await db.commit()


async def get_messages(run_id: str) -> list[dict]:
    """Return all messages for a run ordered by sequence ascending, with content parsed."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM run_messages WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["content"] = json.loads(record["content"])
        results.append(record)
    return results
