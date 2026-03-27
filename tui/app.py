from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── File logging ───────────────────────────────────────────────────────────────
# Writes to agent_runner.log next to this file.  The TUI owns stdout/stderr so
# all diagnostics go here instead.

_LOG_PATH = Path(__file__).parent / "agent_runner.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(_LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger("agent_runner")

from textual import on, work
from textual.app import App, ComposeResult
from textual.theme import Theme
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.coordinate import Coordinate
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    TextArea,
)

from database import (
    init_db,
    create_agent,
    get_agents,
    get_agent,
    delete_agent,
    create_run,
    get_runs,
    get_run,
    get_messages,
    update_run,
    append_message,
    get_setting,
    set_setting,
)
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    SystemMessage,
    AssistantMessage,
    ResultMessage,
    RateLimitEvent,
)
from discovery import scan_agents

DEFAULT_SCAN_DIR = r"C:\src\Teams-Graph"

# ── Dracula theme ──────────────────────────────────────────────────────────────

DRACULA_THEME = Theme(
    name="dracula",
    dark=True,
    primary="#bd93f9",    # purple  — buttons, focus rings, highlights
    secondary="#8be9fd",  # cyan    — secondary accents
    accent="#50fa7b",     # green   — success / active
    warning="#ffb86c",    # orange
    error="#ff5555",      # red
    success="#50fa7b",    # green
    background="#282a36", # main bg
    surface="#21222c",    # panel bg
    panel="#191a21",      # dark bars (header, footer, toolbar)
    foreground="#f8f8f2", # default text
    boost="#44475a",      # subtle borders / zebra rows
)


# ── Custom Messages ────────────────────────────────────────────────────────────

class AgentMessage(Message):
    """Posted when the agent emits a message during a run."""

    def __init__(self, run_id: str, content: dict) -> None:
        super().__init__()
        self.run_id = run_id
        self.content = content


class RunFinished(Message):
    """Posted when an agent run reaches a terminal state."""

    def __init__(self, run_id: str, status: str, error: str = "") -> None:
        super().__init__()
        self.run_id = run_id
        self.status = status
        self.error = error


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_message(msg: Any, sequence: int) -> dict:
    """Convert an SDK message object into a serializable dict."""
    ts = _now_iso()
    if isinstance(msg, SystemMessage):
        return {
            "type": "system",
            "subtype": msg.subtype,
            "data": msg.data or {},
            "sequence": sequence,
            "timestamp": ts,
        }
    if isinstance(msg, AssistantMessage):
        blocks = []
        for b in (msg.content or []):
            n = type(b).__name__
            if n == "TextBlock":
                blocks.append({"type": "text", "text": b.text})
            elif n == "ToolUseBlock":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
            else:
                blocks.append({"type": "unknown", "repr": str(b)})
        return {
            "type": "assistant",
            "content": blocks,
            "usage": msg.usage or {},
            "sequence": sequence,
            "timestamp": ts,
        }
    if isinstance(msg, ResultMessage):
        return {
            "type": "result",
            "result": msg.result,
            "stop_reason": msg.stop_reason,
            "sequence": sequence,
            "timestamp": ts,
        }
    if isinstance(msg, RateLimitEvent):
        return {"type": "rate_limit", "sequence": sequence, "timestamp": ts}
    return {"type": "unknown", "repr": str(msg), "sequence": sequence, "timestamp": ts}


def _status_markup(status: str) -> str:
    m = {
        "running":   "[bold #50fa7b]▶ running[/]",
        "pending":   "[#ffb86c]… pending[/]",
        "done":      "[#8be9fd]✔ done[/]",
        "failed":    "[bold #ff5555]✘ failed[/]",
        "cancelled": "[#6272a4]⊘ cancelled[/]",
    }
    return m.get(status, status)


def _format_duration(started_at: str, finished_at: str | None) -> str:
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at) if finished_at else datetime.now(timezone.utc)
        s = int((end - start).total_seconds())
        return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"
    except Exception:
        return "—"


def _format_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _agent_status_dot(runs: list[dict]) -> str:
    if any(r["status"] in ("running", "pending") for r in runs):
        return "[bold #50fa7b]●[/]"
    if runs and runs[0]["status"] == "failed":
        return "[bold #ff5555]●[/]"
    if runs:
        return "[#8be9fd]●[/]"
    return "[#6272a4]○[/]"


def _sparkline(runs: list[dict]) -> str:
    recent = list(reversed(runs[:7]))
    dots = {
        "done":      "[#8be9fd]█[/]",
        "failed":    "[#ff5555]█[/]",
        "running":   "[#50fa7b]█[/]",
        "pending":   "[#ffb86c]░[/]",
        "cancelled": "[#6272a4]░[/]",
    }
    spark = "".join(dots.get(r["status"], "[#6272a4]░[/]") for r in recent)
    spark = "[#44475a]░[/]" * (7 - len(recent)) + spark
    return spark


# ── NewAgentScreen ─────────────────────────────────────────────────────────────

AVAILABLE_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]
DEFAULT_TOOLS = {"Read", "Glob", "Grep"}


class NewAgentScreen(ModalScreen):
    """Modal dialog for creating a new agent definition."""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New Agent", id="dialog-title")
            yield Input(placeholder="Name *", id="name-input")
            yield Input(placeholder="Description (optional)", id="desc-input")
            yield Label("Prompt *", classes="field-label")
            yield TextArea(id="prompt-input")
            yield Label("Tools", classes="field-label")
            with Horizontal(id="tools-row"):
                for tool in AVAILABLE_TOOLS:
                    yield Checkbox(tool, value=(tool in DEFAULT_TOOLS), id=f"cb-{tool}")
            with Horizontal(id="bottom-row"):
                yield Label("Max turns: ", classes="field-label")
                yield Input("20", id="turns-input")
                yield Label("  Permission: ", classes="field-label")
                yield Select(
                    [("Accept Edits", "acceptEdits"), ("Bypass All \u26a0", "bypassPermissions")],
                    value="acceptEdits",
                    id="perm-select",
                    allow_blank=False,
                )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    @on(Button.Pressed, "#btn-save")
    async def save(self) -> None:
        name = self.query_one("#name-input", Input).value.strip()
        prompt = self.query_one("#prompt-input", TextArea).text.strip()
        if not name or not prompt:
            return
        tools = [t for t in AVAILABLE_TOOLS if self.query_one(f"#cb-{t}", Checkbox).value]
        try:
            max_turns = int(self.query_one("#turns-input", Input).value)
        except ValueError:
            max_turns = 20
        perm = self.query_one("#perm-select", Select).value
        self.dismiss({
            "name": name,
            "description": self.query_one("#desc-input", Input).value.strip() or None,
            "prompt": prompt,
            "tools": tools,
            "max_turns": max_turns,
            "permission_mode": str(perm),
        })

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


# ── ScanAgentsScreen ───────────────────────────────────────────────────────────

class ScanAgentsScreen(ModalScreen):
    """Modal that shows agents discovered from the filesystem."""

    def __init__(self, scan_dir: str, discovered: list[dict]) -> None:
        super().__init__()
        self._scan_dir = scan_dir
        self._discovered = discovered
        # track which items are checked; default all on
        self._checked: dict[int, bool] = {i: True for i in range(len(discovered))}

    def compose(self) -> ComposeResult:
        with Vertical(id="scan-dialog"):
            yield Label("Import Agents from Filesystem", id="scan-title")
            yield Label(f"📂 {self._scan_dir}", id="scan-dir-label")

            if not self._discovered:
                yield Label(
                    "No *.agent.py files found.\n\n"
                    "Create a file like my_task.agent.py with:\n"
                    "  NAME = \"My Agent\"\n"
                    "  PROMPT = \"\"\"...\"\"\"\n"
                    "  TOOLS = [\"Read\", \"Glob\", \"Grep\"]",
                    id="scan-empty",
                )
            else:
                yield Label(f"{len(self._discovered)} agent(s) found — select to import:")
                with ScrollableContainer(id="scan-list"):
                    for i, agent in enumerate(self._discovered):
                        with Vertical(classes="scan-item"):
                            yield Checkbox(
                                f"[bold]{agent['name']}[/bold]",
                                value=True,
                                id=f"scan-cb-{i}",
                            )
                            prompt_preview = agent["prompt"][:120].replace("\n", " ")
                            if len(agent["prompt"]) > 120:
                                prompt_preview += "…"
                            yield Label(f"  {prompt_preview}", classes="scan-item-prompt")
                            rel = Path(agent["source_file"]).name
                            yield Label(f"  📄 {rel}", classes="scan-item-file")

            with Horizontal(id="scan-buttons"):
                if self._discovered:
                    yield Button("Import Selected", variant="primary", id="btn-scan-import")
                yield Button("Cancel", id="btn-scan-cancel")

    @on(Button.Pressed, "#btn-scan-import")
    def do_import(self) -> None:
        selected = [
            self._discovered[i]
            for i in range(len(self._discovered))
            if self.query_one(f"#scan-cb-{i}", Checkbox).value
        ]
        self.dismiss(selected)

    @on(Button.Pressed, "#btn-scan-cancel")
    def do_cancel(self) -> None:
        self.dismiss([])


# ── Main App ───────────────────────────────────────────────────────────────────

class AgentRunnerApp(App):
    """Three-panel TUI for managing and running Claude agents."""

    TITLE = "Claude Agent Runner"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("n", "new_agent",    "New Agent"),
        Binding("i", "scan_agents",  "Import"),
        Binding("r", "run_agent",    "Run"),
        Binding("s", "stop_run",     "Stop"),
        Binding("D", "delete_agent", "Delete"),
        Binding("q", "quit",         "Quit"),
    ]

    selected_agent_id: reactive[str | None] = reactive(None, recompose=False)
    selected_run_id:   reactive[str | None] = reactive(None, recompose=False)

    def __init__(self, scan_dir: str = DEFAULT_SCAN_DIR) -> None:
        super().__init__()
        self._scan_dir = scan_dir
        self._agents: list[dict] = []
        self._runs:   list[dict] = []
        self._active_workers: dict[str, Any] = {}
        self._stream_run_id: str | None = None

    # ── Layout ─────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="agents-panel"):
                yield Static("AGENTS", classes="panel-title", id="agents-title")
                yield ListView(id="agents-list")
                with Horizontal(classes="toolbar"):
                    yield Button("+ New", id="btn-new-agent", variant="primary")
                    yield Button("↓ Import", id="btn-scan-agents", variant="success")
                    yield Button("Delete", id="btn-delete-agent", classes="warning")
            with Vertical(id="runs-panel"):
                yield Static("RUNS", classes="panel-title", id="runs-title")
                yield DataTable(id="runs-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="toolbar"):
                    yield Button("\u25b6 Run", id="btn-run", variant="primary")
                    yield Button("\u23f9 Stop", id="btn-stop")
            with Vertical(id="stream-panel"):
                yield Static("STREAM", classes="panel-title", id="stream-title")
                yield RichLog(id="stream-log", highlight=True, markup=True, wrap=True, auto_scroll=True)
        yield Footer()

    # ── Init ───────────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        log.info("app started  scan_dir=%s  log=%s", self._scan_dir, _LOG_PATH)
        self.register_theme(DRACULA_THEME)
        await init_db()
        await self._setup_table()
        await self._refresh_agents()
        saved_theme = await get_setting("theme", default="dracula")
        self.theme = saved_theme
        log.info("theme loaded: %s", saved_theme)

    async def watch_theme(self, theme: str) -> None:
        """Persist theme changes so they survive restarts."""
        try:
            await set_setting("theme", theme)
            log.info("theme saved: %s", theme)
        except Exception:
            pass  # DB may not be ready on the very first call

    # ── Init (continued) ───────────────────────────────────────────────────────

    async def _setup_table(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.add_column("#",        key="num",      width=4)
        table.add_column("Status",   key="status",   width=14)
        table.add_column("Time",     key="time",     width=8)
        table.add_column("Duration", key="duration", width=9)
        table.add_column("Tokens",   key="tokens",   width=8)

    # ── Data helpers ───────────────────────────────────────────────────────────

    async def _refresh_agents(self) -> None:
        self._agents = await get_agents()
        agent_list = self.query_one("#agents-list", ListView)
        await agent_list.clear()
        for agent in self._agents:
            runs = await get_runs(agent["id"])
            dot   = _agent_status_dot(runs)
            spark = _sparkline(runs)
            label = f"{dot} {agent['name']}\n   {spark}"
            await agent_list.append(ListItem(Label(label), id=f"agent-{agent['id']}"))
        title = self.query_one("#agents-title", Static)
        title.update(f"AGENTS ({len(self._agents)})")

    async def _refresh_runs(self) -> None:
        if not self.selected_agent_id:
            return
        self._runs = await get_runs(self.selected_agent_id)
        table = self.query_one("#runs-table", DataTable)
        table.clear()
        total = len(self._runs)
        for i, run in enumerate(self._runs):
            table.add_row(
                str(total - i),
                _status_markup(run["status"]),
                datetime.fromisoformat(run["started_at"]).strftime("%H:%M"),
                _format_duration(run["started_at"], run.get("finished_at")),
                _format_tokens(run["total_input_tokens"] + run["total_output_tokens"]),
                key=run["id"],
            )

    async def _load_stream(self, run_id: str) -> None:
        log = self.query_one("#stream-log", RichLog)
        log.clear()
        run = await get_run(run_id)
        if run:
            log.write(f"[#6272a4]run {run_id[:8]}\u2026  [{run['status']}][/]")
            prompt_preview = run["prompt"][:120]
            ellipsis = "\u2026" if len(run["prompt"]) > 120 else ""
            log.write(f"[#6272a4]{prompt_preview}{ellipsis}[/]")
            log.write("")
        msgs = await get_messages(run_id)
        for row in msgs:
            self._render_to_log(row["content"], log)
        self._stream_run_id = run_id

    def _render_to_log(self, content: dict, log: RichLog) -> None:
        t = content.get("type")
        if t == "assistant":
            for b in content.get("content", []):
                if b["type"] == "text":
                    log.write(f"[#f8f8f2]{b['text']}[/]")
                elif b["type"] == "tool_use":
                    inp = json.dumps(b["input"])
                    if len(inp) > 80:
                        inp = inp[:80] + "\u2026"
                    log.write(f"[bold #bd93f9]\U0001f527 {b['name']}[/] [#6272a4]{inp}[/]")
        elif t == "result":
            log.write("")
            log.write(f"[bold #50fa7b]\u2501\u2501 Result ({content.get('stop_reason', '')}) \u2501\u2501[/]")
            log.write(f"[#8be9fd]{content.get('result', '')}[/]")
        elif t == "run_status":
            st = content.get("status")
            if st == "failed":
                log.write(f"\n[bold #ff5555]\u2717 Failed: {content.get('error', '')}[/]")
            elif st == "cancelled":
                log.write("\n[#ffb86c]\u2298 Cancelled[/]")
        elif t == "rate_limit":
            log.write("[#ffb86c]\u23f3 Rate limited \u2014 waiting\u2026[/]")

    # ── Reactive watchers ──────────────────────────────────────────────────────

    async def watch_selected_agent_id(self, agent_id: str | None) -> None:
        self.selected_run_id = None
        self._stream_run_id = None
        self.query_one("#stream-log", RichLog).clear()
        if not agent_id:
            return
        agent = await get_agent(agent_id)
        if agent:
            self.query_one("#runs-title", Static).update(f"RUNS \u2014 {agent['name']}")
        await self._refresh_runs()

    async def watch_selected_run_id(self, run_id: str | None) -> None:
        if not run_id:
            return
        run = await get_run(run_id)
        if run:
            self.query_one("#stream-title", Static).update(
                f"STREAM \u2014 run {run_id[:8]}\u2026 [{run['status']}]"
            )
        await self._load_stream(run_id)

    # ── Event handlers ─────────────────────────────────────────────────────────

    @on(ListView.Selected, "#agents-list")
    def on_agent_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("agent-"):
            self.selected_agent_id = item_id[len("agent-"):]

    @on(DataTable.RowSelected, "#runs-table")
    async def on_run_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            self.selected_run_id = str(event.row_key.value)

    @on(Button.Pressed, "#btn-new-agent")
    @work
    async def on_new_agent(self) -> None:
        result = await self.push_screen_wait(NewAgentScreen())
        if result:
            await create_agent(**result)
            await self._refresh_agents()

    @on(Button.Pressed, "#btn-scan-agents")
    @work
    async def on_scan_agents(self) -> None:
        discovered = scan_agents(self._scan_dir)
        imported: list[dict] = await self.push_screen_wait(
            ScanAgentsScreen(self._scan_dir, discovered)
        )
        if imported:
            existing = {a["name"] for a in self._agents}
            added = 0
            for agent in imported:
                if agent["name"] not in existing:
                    await create_agent(
                        name=agent["name"],
                        description=agent.get("description"),
                        prompt=agent["prompt"],
                        tools=agent["tools"],
                        max_turns=agent["max_turns"],
                        permission_mode=agent["permission_mode"],
                    )
                    added += 1
            await self._refresh_agents()
            if added:
                self.notify(f"Imported {added} agent(s) from {self._scan_dir}")
            else:
                self.notify("All selected agents already exist.", severity="warning")

    @on(Button.Pressed, "#btn-delete-agent")
    async def on_delete_agent(self) -> None:
        if self.selected_agent_id:
            await delete_agent(self.selected_agent_id)
            self.selected_agent_id = None
            await self._refresh_agents()

    @on(Button.Pressed, "#btn-run")
    async def on_run(self) -> None:
        if not self.selected_agent_id:
            return
        agent = await get_agent(self.selected_agent_id)
        if not agent:
            return
        run = await create_run(agent["id"], agent["prompt"])
        agent_for_run = dict(agent)
        worker = self._execute_agent(run["id"], agent_for_run)
        self._active_workers[run["id"]] = worker
        await self._refresh_runs()
        self.selected_run_id = run["id"]

    @on(Button.Pressed, "#btn-stop")
    async def on_stop(self) -> None:
        if self.selected_run_id:
            worker = self._active_workers.get(self.selected_run_id)
            if worker:
                worker.cancel()

    def on_agent_message(self, event: AgentMessage) -> None:
        """Live-update the stream panel and token count for the active run."""
        if event.run_id == self._stream_run_id:
            log = self.query_one("#stream-log", RichLog)
            self._render_to_log(event.content, log)
        if event.content.get("type") == "assistant":
            try:
                table = self.query_one("#runs-table", DataTable)
                run_id = event.run_id
                for row_key in table.rows:
                    if str(row_key.value) == run_id:
                        run = next((r for r in self._runs if r["id"] == run_id), None)
                        if run:
                            table.update_cell(
                                row_key,
                                "tokens",
                                _format_tokens(
                                    run["total_input_tokens"] + run["total_output_tokens"]
                                ),
                            )
                        break
            except Exception:
                pass

    async def on_run_finished(self, event: RunFinished) -> None:
        await self._refresh_runs()
        await self._refresh_agents()
        if event.run_id == self._stream_run_id:
            log = self.query_one("#stream-log", RichLog)
            if event.status == "done":
                log.write("\n[#44475a]\u2500\u2500\u2500 completed \u2500\u2500\u2500[/]")
            elif event.status == "failed":
                log.write(f"\n[bold #ff5555]\u2500\u2500\u2500 failed: {event.error} \u2500\u2500\u2500[/]")
            self.query_one("#stream-title", Static).update(
                f"STREAM \u2014 run {event.run_id[:8]}\u2026 [{event.status}]"
            )

    # ── Key bindings ───────────────────────────────────────────────────────────

    def action_new_agent(self)    -> None: self.query_one("#btn-new-agent").press()
    def action_scan_agents(self)  -> None: self.query_one("#btn-scan-agents").press()
    def action_run_agent(self)    -> None: self.query_one("#btn-run").press()
    def action_stop_run(self)     -> None: self.query_one("#btn-stop").press()
    def action_delete_agent(self) -> None: self.query_one("#btn-delete-agent").press()

    # ── Worker (agent execution) ───────────────────────────────────────────────

    @work(exclusive=False, exit_on_error=False)
    async def _execute_agent(self, run_id: str, agent: dict) -> None:
        """Background worker that streams an agent run and persists all messages."""
        log.info("run start  run_id=%s  agent=%s", run_id, agent.get("name"))
        await update_run(run_id, status="running")
        sequence = total_in = total_out = 0
        try:
            tools = agent["tools"] if isinstance(agent["tools"], list) else json.loads(agent["tools"])
            options = ClaudeAgentOptions(
                allowed_tools=tools,
                max_turns=agent["max_turns"],
                permission_mode=agent["permission_mode"],
                disallowed_tools=["AskUserQuestion"],
            )
            async for msg in query(prompt=agent["prompt"], options=options):
                serialized = serialize_message(msg, sequence)
                sequence += 1
                log.debug("msg  run_id=%s  seq=%d  type=%s", run_id, sequence, serialized["type"])

                if serialized["type"] == "system" and serialized.get("subtype") == "init":
                    sid = serialized.get("data", {}).get("session_id")
                    if sid:
                        await update_run(run_id, session_id=sid)

                if serialized["type"] == "assistant":
                    usage = serialized.get("usage") or {}
                    total_in  += usage.get("input_tokens", 0)
                    total_out += usage.get("output_tokens", 0)
                    await update_run(
                        run_id,
                        total_input_tokens=total_in,
                        total_output_tokens=total_out,
                    )

                await append_message(run_id, sequence, serialized["type"], serialized)
                self.post_message(AgentMessage(run_id, serialized))

                if serialized["type"] == "result":
                    log.info("run done  run_id=%s  stop_reason=%s  in=%d  out=%d",
                             run_id, serialized.get("stop_reason"), total_in, total_out)
                    await update_run(
                        run_id,
                        status="done",
                        result=serialized.get("result"),
                        stop_reason=serialized.get("stop_reason"),
                        finished_at=_now_iso(),
                        total_input_tokens=total_in,
                        total_output_tokens=total_out,
                    )
                    self.post_message(RunFinished(run_id, "done"))

        except asyncio.CancelledError:
            log.info("run cancelled  run_id=%s", run_id)
            await update_run(run_id, status="cancelled", finished_at=_now_iso())
            self.post_message(RunFinished(run_id, "cancelled"))
        except Exception as exc:
            log.error("run failed  run_id=%s\n%s", run_id, traceback.format_exc())
            err = str(exc)
            await update_run(run_id, status="failed", error=err, finished_at=_now_iso())
            self.post_message(RunFinished(run_id, "failed", err))
        finally:
            self._active_workers.pop(run_id, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Agent Runner TUI")
    parser.add_argument(
        "--scan-dir",
        default=DEFAULT_SCAN_DIR,
        metavar="DIR",
        help=f"Directory to scan for *.agent.py files (default: {DEFAULT_SCAN_DIR})",
    )
    args = parser.parse_args()
    try:
        AgentRunnerApp(scan_dir=args.scan_dir).run()
        log.info("app exited cleanly")
    except Exception:
        log.critical("app crashed\n%s", traceback.format_exc())
        raise
