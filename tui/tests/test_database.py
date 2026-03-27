"""
Integration tests for database.py — runs against a real (temporary) SQLite DB.
Each test is async (pytest-asyncio auto mode) and gets an isolated temp DB.
"""
import sys
import asyncio
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import database as db_module


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))


# ── init_db ────────────────────────────────────────────────────────────────────

async def test_init_db_creates_tables():
    import aiosqlite
    await db_module.init_db()
    async with aiosqlite.connect(db_module.DB_PATH) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
    assert "agent_definitions" in tables
    assert "agent_runs" in tables
    assert "run_messages" in tables
    assert "settings" in tables


async def test_init_db_idempotent():
    await db_module.init_db()
    await db_module.init_db()  # should not raise


# ── helpers ────────────────────────────────────────────────────────────────────

async def _make_agent(**overrides):
    await db_module.init_db()
    defaults = dict(
        name="Test Agent",
        description="Does testing",
        prompt="Run the tests",
        tools=["Read", "Glob"],
        max_turns=10,
        permission_mode="acceptEdits",
    )
    defaults.update(overrides)
    return await db_module.create_agent(**defaults)


# ── agent CRUD ─────────────────────────────────────────────────────────────────

async def test_create_agent_returns_dict():
    agent = await _make_agent()
    assert agent["name"] == "Test Agent"
    assert agent["tools"] == ["Read", "Glob"]
    assert agent["max_turns"] == 10
    assert "id" in agent
    assert "created_at" in agent


async def test_create_agent_tools_roundtrip():
    tools = ["Read", "Write", "Edit", "Bash"]
    agent = await _make_agent(tools=tools)
    assert agent["tools"] == tools


async def test_get_agent_existing():
    created = await _make_agent()
    fetched = await db_module.get_agent(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Test Agent"


async def test_get_agent_missing():
    await db_module.init_db()
    assert await db_module.get_agent("nonexistent-id") is None


async def test_get_agents_empty():
    await db_module.init_db()
    assert await db_module.get_agents() == []


async def test_get_agents_multiple():
    await _make_agent(name="Alpha")
    await _make_agent(name="Beta")
    agents = await db_module.get_agents()
    assert len(agents) == 2
    names = {a["name"] for a in agents}
    assert names == {"Alpha", "Beta"}


async def test_get_agents_ordered_by_created_desc():
    await _make_agent(name="First")
    await asyncio.sleep(0.01)
    await _make_agent(name="Second")
    agents = await db_module.get_agents()
    assert agents[0]["name"] == "Second"


async def test_update_agent():
    agent = await _make_agent()
    updated = await db_module.update_agent(agent["id"], name="Renamed", max_turns=50)
    assert updated["name"] == "Renamed"
    assert updated["max_turns"] == 50


async def test_update_agent_tools():
    agent = await _make_agent(tools=["Read"])
    updated = await db_module.update_agent(agent["id"], tools=["Read", "Write"])
    assert updated["tools"] == ["Read", "Write"]


async def test_update_agent_updates_updated_at():
    agent = await _make_agent()
    original_ts = agent["updated_at"]
    await asyncio.sleep(0.01)
    updated = await db_module.update_agent(agent["id"], name="New")
    assert updated["updated_at"] >= original_ts


async def test_delete_agent():
    agent = await _make_agent()
    await db_module.delete_agent(agent["id"])
    assert await db_module.get_agent(agent["id"]) is None


async def test_delete_agent_not_in_list():
    agent = await _make_agent()
    await db_module.delete_agent(agent["id"])
    assert await db_module.get_agents() == []


# ── run CRUD ───────────────────────────────────────────────────────────────────

async def test_create_run_pending():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "Do things")
    assert r["status"] == "pending"
    assert r["agent_id"] == agent["id"]
    assert r["prompt"] == "Do things"
    assert r["total_input_tokens"] == 0
    assert r["total_output_tokens"] == 0
    assert r["finished_at"] is None


async def test_get_run_existing():
    agent = await _make_agent()
    created = await db_module.create_run(agent["id"], "task")
    fetched = await db_module.get_run(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]


async def test_get_run_missing():
    await db_module.init_db()
    assert await db_module.get_run("no-such-run") is None


async def test_get_runs_empty():
    agent = await _make_agent()
    assert await db_module.get_runs(agent["id"]) == []


async def test_get_runs_for_agent():
    a1 = await _make_agent(name="A1")
    a2 = await _make_agent(name="A2")
    await db_module.create_run(a1["id"], "task 1")
    await db_module.create_run(a1["id"], "task 2")
    await db_module.create_run(a2["id"], "other task")
    runs = await db_module.get_runs(a1["id"])
    assert len(runs) == 2


async def test_update_run_status():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    await db_module.update_run(r["id"], status="running")
    updated = await db_module.get_run(r["id"])
    assert updated["status"] == "running"


async def test_update_run_multiple_fields():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    await db_module.update_run(
        r["id"],
        status="done",
        result="All done",
        total_input_tokens=100,
        total_output_tokens=50,
    )
    fetched = await db_module.get_run(r["id"])
    assert fetched["status"] == "done"
    assert fetched["result"] == "All done"
    assert fetched["total_input_tokens"] == 100
    assert fetched["total_output_tokens"] == 50


async def test_update_run_no_kwargs():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    await db_module.update_run(r["id"])  # no-op
    fetched = await db_module.get_run(r["id"])
    assert fetched["status"] == "pending"


# ── messages ───────────────────────────────────────────────────────────────────

async def test_append_and_get_messages():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    content = {"type": "assistant", "content": [{"type": "text", "text": "hello"}]}
    await db_module.append_message(r["id"], 0, "assistant", content)
    msgs = await db_module.get_messages(r["id"])
    assert len(msgs) == 1
    assert msgs[0]["msg_type"] == "assistant"
    assert msgs[0]["content"]["type"] == "assistant"


async def test_get_messages_ordered_by_sequence():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    for i in [2, 0, 1]:
        await db_module.append_message(r["id"], i, "assistant", {"seq": i})
    msgs = await db_module.get_messages(r["id"])
    assert [m["sequence"] for m in msgs] == [0, 1, 2]


async def test_get_messages_empty():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    assert await db_module.get_messages(r["id"]) == []


async def test_get_messages_only_for_run():
    agent = await _make_agent()
    r1 = await db_module.create_run(agent["id"], "task1")
    r2 = await db_module.create_run(agent["id"], "task2")
    await db_module.append_message(r1["id"], 0, "assistant", {"run": 1})
    await db_module.append_message(r2["id"], 0, "assistant", {"run": 2})
    msgs = await db_module.get_messages(r1["id"])
    assert len(msgs) == 1
    assert msgs[0]["content"]["run"] == 1


async def test_message_content_roundtrip():
    agent = await _make_agent()
    r = await db_module.create_run(agent["id"], "task")
    content = {
        "type": "result",
        "result": "Success!",
        "stop_reason": "end_turn",
        "nested": {"list": [1, 2, 3]},
    }
    await db_module.append_message(r["id"], 0, "result", content)
    msgs = await db_module.get_messages(r["id"])
    assert msgs[0]["content"] == content


# ── settings ───────────────────────────────────────────────────────────────────

async def test_get_setting_default_when_missing():
    await db_module.init_db()
    assert await db_module.get_setting("theme") == ""
    assert await db_module.get_setting("theme", default="dracula") == "dracula"


async def test_set_and_get_setting():
    await db_module.init_db()
    await db_module.set_setting("theme", "dracula")
    assert await db_module.get_setting("theme") == "dracula"


async def test_set_setting_overwrites():
    await db_module.init_db()
    await db_module.set_setting("theme", "nord")
    await db_module.set_setting("theme", "dracula")
    assert await db_module.get_setting("theme") == "dracula"


async def test_set_setting_multiple_keys():
    await db_module.init_db()
    await db_module.set_setting("theme", "dracula")
    await db_module.set_setting("scan_dir", "/some/path")
    assert await db_module.get_setting("theme") == "dracula"
    assert await db_module.get_setting("scan_dir") == "/some/path"
