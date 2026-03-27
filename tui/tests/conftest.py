"""
Shared pytest configuration.

Installs a single claude_agent_sdk stub into sys.modules BEFORE any test file
is imported, so that app.py's `from claude_agent_sdk import ...` binds to these
exact class objects.  All test files must import the SDK names from here rather
than defining their own stubs.
"""
import sys
import types
from pathlib import Path

# Ensure the tui directory is on the path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Single canonical SDK stub ─────────────────────────────────────────────────

class SystemMessage:
    def __init__(self, subtype="init", data=None):
        self.subtype = subtype
        self.data = data or {}

class AssistantMessage:
    def __init__(self, content=None, usage=None):
        self.content = content or []
        self.usage = usage or {}

class ResultMessage:
    def __init__(self, result="done", stop_reason="end_turn"):
        self.result = result
        self.stop_reason = stop_reason

class RateLimitEvent:
    pass

class ClaudeAgentOptions:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

class TextBlock:
    def __init__(self, text):
        self.text = text

class ToolUseBlock:
    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


async def instant_query(prompt, options=None):
    """Stub query that emits one assistant turn then a result, instantly."""
    yield SystemMessage(subtype="init", data={"session_id": "stub-session"})
    yield AssistantMessage(
        content=[TextBlock("stub reply")],
        usage={"input_tokens": 5, "output_tokens": 3},
    )
    yield ResultMessage(result="stub result", stop_reason="end_turn")


_sdk = types.ModuleType("claude_agent_sdk")
_sdk.SystemMessage = SystemMessage
_sdk.AssistantMessage = AssistantMessage
_sdk.ResultMessage = ResultMessage
_sdk.RateLimitEvent = RateLimitEvent
_sdk.ClaudeAgentOptions = ClaudeAgentOptions
_sdk.TextBlock = TextBlock
_sdk.ToolUseBlock = ToolUseBlock
_sdk.query = instant_query
sys.modules["claude_agent_sdk"] = _sdk
