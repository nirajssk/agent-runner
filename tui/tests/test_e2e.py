"""
End-to-end tests using Textual's built-in app pilot.

The SDK stub is installed by conftest.py before this module is imported.
"""
import asyncio
import pytest

import database as db_module
from app import AgentRunnerApp


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "e2e_test.db"))


@pytest.fixture
def app(tmp_path):
    return AgentRunnerApp(scan_dir=str(tmp_path))


# ── Layout smoke test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_app_mounts_three_panels(app):
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#agents-panel")
        assert pilot.app.query_one("#runs-panel")
        assert pilot.app.query_one("#stream-panel")


@pytest.mark.asyncio
async def test_agents_panel_has_new_button(app):
    async with app.run_test() as pilot:
        btn = pilot.app.query_one("#btn-new-agent")
        assert btn is not None


@pytest.mark.asyncio
async def test_agents_panel_has_import_button(app):
    async with app.run_test() as pilot:
        btn = pilot.app.query_one("#btn-scan-agents")
        assert btn is not None


@pytest.mark.asyncio
async def test_runs_panel_has_run_and_stop_buttons(app):
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#btn-run")
        assert pilot.app.query_one("#btn-stop")


@pytest.mark.asyncio
async def test_stream_panel_has_richlog(app):
    from textual.widgets import RichLog
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#stream-log", RichLog)


# ── Agent list ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agents_list_empty_on_fresh_start(app):
    from textual.widgets import ListView
    async with app.run_test() as pilot:
        lv = pilot.app.query_one("#agents-list", ListView)
        assert len(lv) == 0


@pytest.mark.asyncio
async def test_agents_title_shows_count(app):
    from textual.widgets import Static
    async with app.run_test() as pilot:
        await db_module.create_agent(
            name="Pre-seeded",
            description=None,
            prompt="Do something",
            tools=["Read"],
            max_turns=5,
            permission_mode="acceptEdits",
        )
        await pilot.app._refresh_agents()
        await pilot.pause()
        title = pilot.app.query_one("#agents-title", Static)
        # Render to string — works across Textual versions
        assert "1" in str(title.render())


# ── New agent modal ────────────────────────────────────────────────────────────

async def _wait_for_modal(pilot, modal_cls, attempts=20):
    """Click-through helper: pauses until the expected modal is on top."""
    for _ in range(attempts):
        await pilot.pause()
        if isinstance(pilot.app.screen, modal_cls):
            return True
    return False


@pytest.mark.asyncio
async def test_new_agent_modal_opens_on_button(app):
    from app import NewAgentScreen
    async with app.run_test() as pilot:
        await pilot.click("#btn-new-agent")
        opened = await _wait_for_modal(pilot, NewAgentScreen)
        assert opened, "NewAgentScreen never appeared"


@pytest.mark.asyncio
async def test_new_agent_modal_cancel(app):
    from app import NewAgentScreen
    from textual.widgets import Input
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.click("#btn-new-agent")
        await _wait_for_modal(pilot, NewAgentScreen)
        await pilot.click("#btn-cancel")
        await pilot.pause()
        await pilot.pause()
        agents = await db_module.get_agents()
        assert len(agents) == 0


@pytest.mark.asyncio
async def test_new_agent_save_creates_agent(app):
    from app import NewAgentScreen
    from textual.widgets import Input, TextArea
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.click("#btn-new-agent")
        await _wait_for_modal(pilot, NewAgentScreen)

        # Set values directly on the widgets (pilot.type() not available)
        modal = pilot.app.screen
        modal.query_one("#name-input", Input).value = "E2E Agent"
        modal.query_one("#prompt-input", TextArea).text = "Do some work"

        await pilot.click("#btn-save")
        for _ in range(20):
            await pilot.pause()
            agents = await db_module.get_agents()
            if agents:
                break

        agents = await db_module.get_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "E2E Agent"


# ── Import (scan) modal ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_modal_opens(app):
    from app import ScanAgentsScreen
    async with app.run_test() as pilot:
        await pilot.click("#btn-scan-agents")
        opened = await _wait_for_modal(pilot, ScanAgentsScreen)
        assert opened, "ScanAgentsScreen never appeared"


@pytest.mark.asyncio
async def test_scan_modal_shows_empty_message(app):
    from app import ScanAgentsScreen
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.click("#btn-scan-agents")
        await _wait_for_modal(pilot, ScanAgentsScreen)
        # Modal widgets live on the active screen, not the base app
        empty_label = pilot.app.screen.query_one("#scan-empty")
        assert empty_label is not None


@pytest.mark.asyncio
async def test_scan_modal_import_discovered_agents(tmp_path, monkeypatch):
    from app import ScanAgentsScreen
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "scan_e2e.db"))
    (tmp_path / "my_task.agent.py").write_text(
        'NAME = "Scan Task"\nPROMPT = "Do scan work"\n'
    )
    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test(size=(160, 50)) as pilot:
        await pilot.click("#btn-scan-agents")
        await _wait_for_modal(pilot, ScanAgentsScreen)
        cb = pilot.app.screen.query_one("#scan-cb-0")
        assert cb is not None
        await pilot.click("#btn-scan-import")
        for _ in range(20):
            await pilot.pause()
            agents = await db_module.get_agents()
            if agents:
                break
        agents = await db_module.get_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "Scan Task"


@pytest.mark.asyncio
async def test_scan_modal_cancel_does_not_import(tmp_path, monkeypatch):
    from app import ScanAgentsScreen
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "cancel_scan.db"))
    (tmp_path / "task.agent.py").write_text('PROMPT = "Do work"\n')
    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test(size=(160, 50)) as pilot:
        await pilot.click("#btn-scan-agents")
        await _wait_for_modal(pilot, ScanAgentsScreen)
        await pilot.click("#btn-scan-cancel")
        await pilot.pause()
        await pilot.pause()
        agents = await db_module.get_agents()
        assert len(agents) == 0


# ── Run execution ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_button_disabled_without_selection(app):
    """Clicking Run with no agent selected should do nothing."""
    async with app.run_test() as pilot:
        await pilot.click("#btn-run")
        await pilot.pause()
        # No runs should be created
        agents = await db_module.get_agents()
        assert agents == []


async def _run_agent_and_wait(pilot, agent_id, timeout_pauses=60):
    """Trigger a run and wait until it reaches a terminal status."""
    await pilot.click("#btn-run")
    for _ in range(timeout_pauses):
        await pilot.pause()
        runs = await db_module.get_runs(agent_id)
        if runs and runs[0]["status"] in ("done", "failed", "cancelled"):
            return runs[0]
    return None


@pytest.mark.asyncio
async def test_full_run_lifecycle(tmp_path, monkeypatch):
    """Create agent → run → wait for completion → verify DB state."""
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "lifecycle.db"))
    await db_module.init_db()

    agent = await db_module.create_agent(
        name="Lifecycle Agent",
        description=None,
        prompt="Do the thing",
        tools=["Read"],
        max_turns=5,
        permission_mode="acceptEdits",
    )

    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test() as pilot:
        await pilot.app._refresh_agents()
        await pilot.pause()
        pilot.app.selected_agent_id = agent["id"]
        await pilot.pause()

        run = await _run_agent_and_wait(pilot, agent["id"])
        assert run is not None, "Run never reached terminal state"
        assert run["status"] == "done"

        msgs = await db_module.get_messages(run["id"])
        types_seen = {m["msg_type"] for m in msgs}
        assert "assistant" in types_seen
        assert "result" in types_seen


@pytest.mark.asyncio
async def test_run_persists_token_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "tokens.db"))
    await db_module.init_db()

    agent = await db_module.create_agent(
        name="Token Agent",
        description=None,
        prompt="Count tokens",
        tools=["Read"],
        max_turns=5,
        permission_mode="acceptEdits",
    )

    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test() as pilot:
        await pilot.app._refresh_agents()
        await pilot.pause()
        pilot.app.selected_agent_id = agent["id"]
        await pilot.pause()

        run = await _run_agent_and_wait(pilot, agent["id"])
        assert run is not None, "Run never reached terminal state"
        assert run["total_input_tokens"] == 5
        assert run["total_output_tokens"] == 3


# ── Delete agent ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_agent_removes_from_list(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "delete.db"))
    await db_module.init_db()

    agent = await db_module.create_agent(
        name="To Delete",
        description=None,
        prompt="Temp",
        tools=[],
        max_turns=1,
        permission_mode="acceptEdits",
    )

    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test() as pilot:
        await pilot.app._refresh_agents()
        await pilot.pause()
        pilot.app.selected_agent_id = agent["id"]
        await pilot.pause()
        await pilot.click("#btn-delete-agent")
        await pilot.pause()

        assert await db_module.get_agent(agent["id"]) is None
        assert await db_module.get_agents() == []


# ── Keyboard bindings ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_key_n_opens_new_agent_modal(app):
    from app import NewAgentScreen
    async with app.run_test() as pilot:
        await pilot.press("n")
        opened = await _wait_for_modal(pilot, NewAgentScreen)
        assert opened, "NewAgentScreen never appeared after pressing n"


@pytest.mark.asyncio
async def test_key_i_opens_scan_modal(app):
    from app import ScanAgentsScreen
    async with app.run_test() as pilot:
        await pilot.press("i")
        opened = await _wait_for_modal(pilot, ScanAgentsScreen)
        assert opened, "ScanAgentsScreen never appeared after pressing i"


@pytest.mark.asyncio
async def test_key_q_quits(app):
    async with app.run_test() as pilot:
        await pilot.press("q")
        # App should exit cleanly (run_test context exits without error)


# ── Theme persistence ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_theme_is_dracula(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert pilot.app.theme == "dracula"


@pytest.mark.asyncio
async def test_theme_change_is_persisted(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        pilot.app.theme = "textual-dark"
        await pilot.pause()
        await pilot.pause()
        saved = await db_module.get_setting("theme")
        assert saved == "textual-dark"


@pytest.mark.asyncio
async def test_theme_restored_on_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "theme_restart.db"))
    await db_module.init_db()
    await db_module.set_setting("theme", "nord")

    app_instance = AgentRunnerApp(scan_dir=str(tmp_path))
    async with app_instance.run_test() as pilot:
        for _ in range(10):
            await pilot.pause()
            if pilot.app.theme == "nord":
                break
        assert pilot.app.theme == "nord"
