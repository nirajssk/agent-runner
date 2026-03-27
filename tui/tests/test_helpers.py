"""
Unit tests for pure helper functions in app.py and discovery.py.
No I/O, no database, no SDK — fast and deterministic.

The SDK stub is installed by conftest.py before this module is imported.
"""
from pathlib import Path

# SDK classes come from the stub installed by conftest.py
from claude_agent_sdk import (
    SystemMessage, AssistantMessage, ResultMessage, RateLimitEvent,
    TextBlock, ToolUseBlock,
)

from app import (
    serialize_message,
    _status_markup,
    _format_duration,
    _format_tokens,
    _agent_status_dot,
    _sparkline,
)
from discovery import scan_agents


class UnknownBlock:
    pass


def test_serialize_system_message():
    msg = SystemMessage(subtype="init", data={"session_id": "abc123"})
    result = serialize_message(msg, 0)
    assert result["type"] == "system"
    assert result["subtype"] == "init"
    assert result["data"]["session_id"] == "abc123"
    assert result["sequence"] == 0
    assert "timestamp" in result


def test_serialize_assistant_message_text():
    tb = TextBlock("Hello world")
    msg = AssistantMessage(
        content=[tb],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    result = serialize_message(msg, 1)
    assert result["type"] == "assistant"
    assert result["content"][0] == {"type": "text", "text": "Hello world"}
    assert result["usage"]["input_tokens"] == 10
    assert result["sequence"] == 1


def test_serialize_assistant_message_tool_use():
    tb = ToolUseBlock(id="tu1", name="Read", input={"file": "foo.py"})
    msg = AssistantMessage(content=[tb])
    result = serialize_message(msg, 2)
    block = result["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "Read"
    assert block["input"] == {"file": "foo.py"}


def test_serialize_assistant_message_unknown_block():
    msg = AssistantMessage(content=[UnknownBlock()])
    result = serialize_message(msg, 3)
    assert result["content"][0]["type"] == "unknown"
    assert "repr" in result["content"][0]


def test_serialize_assistant_empty_content():
    msg = AssistantMessage(content=[], usage={})
    result = serialize_message(msg, 4)
    assert result["type"] == "assistant"
    assert result["content"] == []


def test_serialize_result_message():
    msg = ResultMessage(result="Done!", stop_reason="end_turn")
    result = serialize_message(msg, 5)
    assert result["type"] == "result"
    assert result["result"] == "Done!"
    assert result["stop_reason"] == "end_turn"


def test_serialize_rate_limit_event():
    msg = RateLimitEvent()
    result = serialize_message(msg, 6)
    assert result["type"] == "rate_limit"
    assert result["sequence"] == 6


def test_serialize_unknown_object():
    result = serialize_message(object(), 7)
    assert result["type"] == "unknown"
    assert "repr" in result


# ── _status_markup ─────────────────────────────────────────────────────────────

def test_status_markup_known():
    # Dracula palette: green running, cyan done, red failed, orange pending, comment cancelled
    assert "#50fa7b" in _status_markup("running")
    assert "#8be9fd" in _status_markup("done")
    assert "#ff5555" in _status_markup("failed")
    assert "#ffb86c" in _status_markup("pending")
    assert "#6272a4" in _status_markup("cancelled")


def test_status_markup_contains_symbol():
    assert "▶" in _status_markup("running")
    assert "✔" in _status_markup("done")
    assert "✘" in _status_markup("failed")
    assert "⊘" in _status_markup("cancelled")


def test_status_markup_unknown_passthrough():
    assert _status_markup("weird_status") == "weird_status"


# ── _format_duration ───────────────────────────────────────────────────────────

def test_format_duration_seconds():
    result = _format_duration("2024-01-01T00:00:00+00:00", "2024-01-01T00:00:45+00:00")
    assert result == "45s"


def test_format_duration_minutes():
    result = _format_duration("2024-01-01T00:00:00+00:00", "2024-01-01T00:02:05+00:00")
    assert result == "2m05s"


def test_format_duration_no_end():
    # Should not raise; returns a reasonable string
    result = _format_duration("2024-01-01T00:00:00+00:00", None)
    assert result.endswith("s") or "m" in result


def test_format_duration_bad_input():
    assert _format_duration("not-a-date", None) == "—"


# ── _format_tokens ─────────────────────────────────────────────────────────────

def test_format_tokens_below_1k():
    assert _format_tokens(0)   == "0"
    assert _format_tokens(999) == "999"


def test_format_tokens_above_1k():
    assert _format_tokens(1000) == "1.0k"
    assert _format_tokens(1500) == "1.5k"
    assert _format_tokens(12345) == "12.3k"


# ── _agent_status_dot ──────────────────────────────────────────────────────────

def test_agent_status_dot_no_runs():
    result = _agent_status_dot([])
    assert "○" in result
    assert "#6272a4" in result  # Dracula comment color for empty


def test_agent_status_dot_running():
    runs = [{"status": "running"}]
    result = _agent_status_dot(runs)
    assert "#50fa7b" in result  # Dracula green


def test_agent_status_dot_pending():
    runs = [{"status": "pending"}]
    result = _agent_status_dot(runs)
    assert "#50fa7b" in result  # pending treated same as running


def test_agent_status_dot_failed():
    runs = [{"status": "failed"}]
    result = _agent_status_dot(runs)
    assert "#ff5555" in result  # Dracula red


def test_agent_status_dot_done():
    runs = [{"status": "done"}]
    result = _agent_status_dot(runs)
    assert "●" in result
    assert "#8be9fd" in result  # Dracula cyan for done


def test_agent_status_dot_running_takes_precedence():
    runs = [{"status": "failed"}, {"status": "running"}]
    assert "#50fa7b" in _agent_status_dot(runs)


# ── _sparkline ─────────────────────────────────────────────────────────────────

def test_sparkline_empty():
    result = _sparkline([])
    assert "░" in result
    assert "#44475a" in result  # Dracula subtle for empty slots


def test_sparkline_all_done():
    runs = [{"status": "done"}] * 5
    result = _sparkline(runs)
    assert "#8be9fd" in result  # Dracula cyan for done
    assert "█" in result


def test_sparkline_mixed():
    runs = [
        {"status": "done"},
        {"status": "failed"},
        {"status": "cancelled"},
    ]
    result = _sparkline(runs)
    assert "#8be9fd" in result   # done → cyan
    assert "#ff5555" in result   # failed → red
    assert "#6272a4" in result   # cancelled → comment


def test_sparkline_running():
    runs = [{"status": "running"}]
    result = _sparkline(runs)
    assert "#50fa7b" in result  # Dracula green for running


def test_sparkline_capped_at_7():
    runs = [{"status": "done"}] * 20
    result = _sparkline(runs)
    assert result.count("█") <= 7


# ── discovery.scan_agents ──────────────────────────────────────────────────────

def test_scan_agents_empty_dir(tmp_path):
    assert scan_agents(tmp_path) == []


def test_scan_agents_nonexistent_dir():
    assert scan_agents("/does/not/exist/xyz") == []


def test_scan_agents_finds_valid_file(tmp_path):
    (tmp_path / "my_task.agent.py").write_text(
        'NAME = "My Task"\nDESCRIPTION = "Does stuff"\nPROMPT = "Do the thing"\n'
        'TOOLS = ["Read", "Glob"]\nMAX_TURNS = 10\n'
    )
    agents = scan_agents(tmp_path)
    assert len(agents) == 1
    assert agents[0]["name"] == "My Task"
    assert agents[0]["description"] == "Does stuff"
    assert agents[0]["prompt"] == "Do the thing"
    assert agents[0]["tools"] == ["Read", "Glob"]
    assert agents[0]["max_turns"] == 10
    assert agents[0]["permission_mode"] == "acceptEdits"


def test_scan_agents_default_name_from_filename(tmp_path):
    (tmp_path / "code_review.agent.py").write_text('PROMPT = "Review code"\n')
    agents = scan_agents(tmp_path)
    assert agents[0]["name"] == "Code Review"


def test_scan_agents_skips_file_without_prompt(tmp_path):
    (tmp_path / "no_prompt.agent.py").write_text('NAME = "Ghost"\n')
    assert scan_agents(tmp_path) == []


def test_scan_agents_skips_syntax_error(tmp_path):
    (tmp_path / "broken.agent.py").write_text('PROMPT = "ok"\ndef bad(:\n')
    assert scan_agents(tmp_path) == []


def test_scan_agents_uses_agent_prompt_alias(tmp_path):
    (tmp_path / "alias.agent.py").write_text('AGENT_PROMPT = "Use me"\n')
    agents = scan_agents(tmp_path)
    assert agents[0]["prompt"] == "Use me"


def test_scan_agents_defaults(tmp_path):
    (tmp_path / "minimal.agent.py").write_text('PROMPT = "Do stuff"\n')
    agent = scan_agents(tmp_path)[0]
    assert agent["tools"] == ["Read", "Glob", "Grep"]
    assert agent["max_turns"] == 20
    assert agent["permission_mode"] == "acceptEdits"


def test_scan_agents_recursive(tmp_path):
    subdir = tmp_path / "subdir" / "deep"
    subdir.mkdir(parents=True)
    (subdir / "nested.agent.py").write_text('PROMPT = "Deep"\n')
    agents = scan_agents(tmp_path)
    assert len(agents) == 1
    assert agents[0]["prompt"] == "Deep"


def test_scan_agents_ignores_non_agent_py(tmp_path):
    (tmp_path / "helper.py").write_text('PROMPT = "Not an agent"\n')
    (tmp_path / "agent.txt").write_text('PROMPT = "Also not"\n')
    assert scan_agents(tmp_path) == []


def test_scan_agents_source_file_path(tmp_path):
    f = tmp_path / "my.agent.py"
    f.write_text('PROMPT = "Check"\n')
    agents = scan_agents(tmp_path)
    assert agents[0]["source_file"] == str(f)


def test_scan_agents_permission_mode(tmp_path):
    (tmp_path / "bypass.agent.py").write_text(
        'PROMPT = "Go"\nPERMISSION_MODE = "bypassPermissions"\n'
    )
    agents = scan_agents(tmp_path)
    assert agents[0]["permission_mode"] == "bypassPermissions"


def test_scan_agents_multiline_prompt(tmp_path):
    (tmp_path / "multi.agent.py").write_text(
        'PROMPT = """Line one\nLine two\nLine three"""\n'
    )
    agents = scan_agents(tmp_path)
    assert "Line one" in agents[0]["prompt"]
    assert "Line three" in agents[0]["prompt"]
