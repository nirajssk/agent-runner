"""
Core agent execution engine.

Each run is executed as an asyncio.Task so the FastAPI event loop remains
unblocked.  The task streams SDK messages through the WebSocketManager and
persists every message to SQLite via the database module.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    SystemMessage,
    query,
)

from database import append_message, update_run

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

# run_id -> asyncio.Task
active_tasks: Dict[str, asyncio.Task] = {}

# run_id -> (asyncio.Event, {"value": str | None})
# Reserved for future pause/reply support.
input_gates: Dict[str, tuple] = {}


# ---------------------------------------------------------------------------
# Message serialisation
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_message(msg: Any, sequence: int) -> dict:
    """Convert an SDK message object to a JSON-serialisable dict."""
    timestamp = _now_iso()

    if isinstance(msg, SystemMessage):
        return {
            "type": "system",
            "subtype": msg.subtype,
            "data": msg.data or {},
            "sequence": sequence,
            "timestamp": timestamp,
        }

    if isinstance(msg, AssistantMessage):
        serialized_blocks = []
        for block in msg.content or []:
            block_name = type(block).__name__
            if block_name == "TextBlock":
                serialized_blocks.append({"type": "text", "text": block.text})
            elif block_name == "ToolUseBlock":
                serialized_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
            else:
                serialized_blocks.append({"type": "unknown", "repr": str(block)})

        return {
            "type": "assistant",
            "content": serialized_blocks,
            "usage": msg.usage or {},
            "sequence": sequence,
            "timestamp": timestamp,
        }

    if isinstance(msg, ResultMessage):
        return {
            "type": "result",
            "result": msg.result,
            "stop_reason": msg.stop_reason,
            "sequence": sequence,
            "timestamp": timestamp,
        }

    if isinstance(msg, RateLimitEvent):
        rate_status = None
        if hasattr(msg, "rate_limit_info") and msg.rate_limit_info is not None:
            rate_status = str(msg.rate_limit_info.status)
        return {
            "type": "rate_limit",
            "status": rate_status,
            "sequence": sequence,
            "timestamp": timestamp,
        }

    # Fallback for any unrecognised message type
    return {
        "type": "unknown",
        "repr": str(msg),
        "sequence": sequence,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------

async def run_agent(run_id: str, agent: dict, ws_manager: Any) -> None:
    """
    Execute a single agent run end-to-end.

    Updates run status in SQLite and broadcasts every message to WebSocket
    subscribers as it arrives.  Handles cancellation and errors gracefully.
    """
    await update_run(run_id, status="running")

    sequence: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    try:
        tools: list = json.loads(agent["tools"])

        options = ClaudeAgentOptions(
            allowed_tools=tools,
            max_turns=agent["max_turns"],
            permission_mode=agent["permission_mode"],
            disallowed_tools=["AskUserQuestion"],  # no interactive prompts
        )

        async for msg in query(prompt=agent["prompt"], options=options):
            serialized = serialize_message(msg, sequence)
            sequence += 1

            # Capture session_id from the init system message
            if (
                serialized["type"] == "system"
                and serialized.get("subtype") == "init"
            ):
                session_id: Optional[str] = (
                    serialized.get("data", {}).get("session_id")
                )
                if session_id:
                    await update_run(run_id, session_id=session_id)

            # Accumulate token usage from assistant messages
            if serialized["type"] == "assistant":
                usage: dict = serialized.get("usage") or {}
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)
                await update_run(
                    run_id,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            # Persist message to SQLite
            await append_message(run_id, sequence, serialized["type"], serialized)

            # Broadcast to all WebSocket subscribers
            await ws_manager.broadcast(run_id, serialized)

            # Finalise the run when the SDK signals completion
            if serialized["type"] == "result":
                await update_run(
                    run_id,
                    status="done",
                    result=serialized.get("result"),
                    stop_reason=serialized.get("stop_reason"),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                await ws_manager.broadcast(
                    run_id, {"type": "run_status", "status": "done"}
                )

    except asyncio.CancelledError:
        await update_run(
            run_id,
            status="cancelled",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        await ws_manager.broadcast(
            run_id, {"type": "run_status", "status": "cancelled"}
        )

    except Exception as exc:
        error_msg = str(exc)
        await update_run(
            run_id,
            status="failed",
            error=error_msg,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        await ws_manager.broadcast(
            run_id,
            {"type": "run_status", "status": "failed", "error": error_msg},
        )

    finally:
        active_tasks.pop(run_id, None)


async def start_run(run_id: str, agent: dict, ws_manager: Any) -> None:
    """
    Spawn *run_agent* as a background asyncio.Task and register it.

    The task is stored in *active_tasks* so it can be cancelled later.
    """
    task = asyncio.create_task(run_agent(run_id, agent, ws_manager))
    active_tasks[run_id] = task


async def stop_run(run_id: str) -> None:
    """Cancel the running task for *run_id* if one exists."""
    task = active_tasks.get(run_id)
    if task is not None and not task.done():
        task.cancel()
