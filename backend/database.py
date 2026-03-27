"""
Async SQLite wrapper for the Claude Agent Runner backend.

Tables:
  - agent_definitions: stored agent configs (prompt, tools, etc.)
  - agent_runs:        individual run records
  - run_messages:      ordered stream of messages emitted during a run
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

DB_PATH = "agent_runner.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Create all tables if they do not already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_definitions (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                description      TEXT,
                prompt           TEXT NOT NULL,
                tools            TEXT NOT NULL DEFAULT '[]',
                max_turns        INTEGER NOT NULL DEFAULT 20,
                permission_mode  TEXT NOT NULL DEFAULT 'acceptEdits',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                id                   TEXT PRIMARY KEY,
                agent_id             TEXT NOT NULL REFERENCES agent_definitions(id),
                session_id           TEXT,
                status               TEXT NOT NULL DEFAULT 'pending',
                prompt               TEXT NOT NULL,
                result               TEXT,
                stop_reason          TEXT,
                error                TEXT,
                total_input_tokens   INTEGER NOT NULL DEFAULT 0,
                total_output_tokens  INTEGER NOT NULL DEFAULT 0,
                started_at           TEXT NOT NULL,
                finished_at          TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS run_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL REFERENCES agent_runs(id),
                sequence   INTEGER NOT NULL,
                msg_type   TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------

async def create_agent(
    name: str,
    description: Optional[str],
    prompt: str,
    tools: list,
    max_turns: int = 20,
    permission_mode: str = "acceptEdits",
) -> dict:
    """Insert a new agent definition and return it as a dict."""
    agent_id = str(uuid.uuid4())
    now = _now_iso()
    tools_json = json.dumps(tools)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agent_definitions
                (id, name, description, prompt, tools, max_turns, permission_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (agent_id, name, description, prompt, tools_json, max_turns, permission_mode, now, now),
        )
        await db.commit()

    return await get_agent(agent_id)


async def get_agents() -> list:
    """Return all agent definitions sorted by created_at DESC."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_definitions ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_agent(agent_id: str) -> Optional[dict]:
    """Return a single agent definition or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_definitions WHERE id = ?", (agent_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def update_agent(agent_id: str, **kwargs: Any) -> dict:
    """Update arbitrary columns on an agent definition."""
    kwargs["updated_at"] = _now_iso()

    # Serialize tools list to JSON if provided
    if "tools" in kwargs and isinstance(kwargs["tools"], list):
        kwargs["tools"] = json.dumps(kwargs["tools"])

    set_clause = ", ".join(f"{col} = ?" for col in kwargs)
    values = list(kwargs.values()) + [agent_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE agent_definitions SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

    return await get_agent(agent_id)


async def delete_agent(agent_id: str) -> None:
    """Delete an agent definition by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM agent_definitions WHERE id = ?", (agent_id,)
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------

async def create_run(agent_id: str, prompt: str) -> dict:
    """Insert a new run record with status='pending' and return it."""
    run_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agent_runs
                (id, agent_id, status, prompt, started_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (run_id, agent_id, prompt, now),
        )
        await db.commit()

    return await get_run(run_id)


async def get_runs(agent_id: str) -> list:
    """Return all runs for an agent sorted by started_at DESC."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_runs WHERE agent_id = ? ORDER BY started_at DESC",
            (agent_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_run(run_id: str) -> Optional[dict]:
    """Return a single run record or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_runs WHERE id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def update_run(run_id: str, **kwargs: Any) -> None:
    """Update arbitrary columns on a run record."""
    if not kwargs:
        return

    set_clause = ", ".join(f"{col} = ?" for col in kwargs)
    values = list(kwargs.values()) + [run_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE agent_runs SET {set_clause} WHERE id = ?", values
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

async def append_message(
    run_id: str, sequence: int, msg_type: str, content_dict: dict
) -> dict:
    """Append a message to a run and return the persisted row."""
    now = _now_iso()
    content_json = json.dumps(content_dict)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            INSERT INTO run_messages (run_id, sequence, msg_type, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, sequence, msg_type, content_json, now),
        )
        await db.commit()
        row_id = cursor.lastrowid
        async with db.execute(
            "SELECT * FROM run_messages WHERE id = ?", (row_id,)
        ) as cursor2:
            row = await cursor2.fetchone()

    return dict(row) if row else {}


async def get_messages(run_id: str) -> list:
    """Return all messages for a run sorted by sequence ASC."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM run_messages WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]
