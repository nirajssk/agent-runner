"""
FastAPI application for the Claude Agent Runner dashboard backend.

Start with:
    uvicorn main:app --reload --port 8000
"""

import json
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import (
    create_agent,
    create_run,
    delete_agent,
    get_agent,
    get_agents,
    get_messages,
    get_run,
    get_runs,
    init_db,
    update_agent,
)
from runner import start_run, stop_run
from websocket_manager import WebSocketManager

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Claude Agent Runner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: str
    tools: List[str] = ["Read", "Glob", "Grep"]
    max_turns: int = 20
    permission_mode: str = "acceptEdits"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: Optional[List[str]] = None
    max_turns: Optional[int] = None
    permission_mode: Optional[str] = None


class RunCreate(BaseModel):
    agent_id: str
    prompt_override: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent routes
# ---------------------------------------------------------------------------

@app.get("/agents")
async def list_agents():
    """Return all stored agent definitions."""
    return await get_agents()


@app.post("/agents", status_code=201)
async def create_agent_route(body: AgentCreate):
    """Create a new agent definition."""
    return await create_agent(
        name=body.name,
        description=body.description,
        prompt=body.prompt,
        tools=body.tools,
        max_turns=body.max_turns,
        permission_mode=body.permission_mode,
    )


@app.get("/agents/{agent_id}")
async def get_agent_route(agent_id: str):
    """Retrieve a single agent definition by id."""
    agent = await get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.put("/agents/{agent_id}")
async def update_agent_route(agent_id: str, body: AgentUpdate):
    """Update one or more fields on an agent definition."""
    agent = await get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Only pass fields that were explicitly provided
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return agent

    return await update_agent(agent_id, **updates)


@app.delete("/agents/{agent_id}")
async def delete_agent_route(agent_id: str):
    """Delete an agent definition."""
    agent = await get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    await delete_agent(agent_id)
    return {"ok": True}


@app.get("/agents/{agent_id}/runs")
async def list_agent_runs(agent_id: str):
    """Return all runs for a given agent, newest first."""
    agent = await get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await get_runs(agent_id)


# ---------------------------------------------------------------------------
# Run routes
# ---------------------------------------------------------------------------

@app.post("/runs", status_code=201)
async def create_run_route(body: RunCreate):
    """
    Start a new agent run.

    The run is created in SQLite with status='pending', then immediately
    promoted to 'running' as the background task begins.  The caller
    receives the initial run record and can subscribe to /ws/runs/{id}
    for live updates.
    """
    agent = await get_agent(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Resolve the prompt: explicit override takes precedence over agent default
    resolved_prompt: str = body.prompt_override or agent["prompt"]

    run = await create_run(body.agent_id, resolved_prompt)

    # Build a full agent dict with the resolved prompt for the runner
    agent_for_run = dict(agent)
    agent_for_run["prompt"] = resolved_prompt

    await start_run(run["id"], agent_for_run, ws_manager)

    return run


@app.get("/runs/{run_id}")
async def get_run_route(run_id: str):
    """Retrieve a single run record by id."""
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/runs/{run_id}/messages")
async def get_run_messages(run_id: str):
    """Return all persisted messages for a run, in sequence order."""
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return await get_messages(run_id)


@app.post("/runs/{run_id}/stop")
async def stop_run_route(run_id: str):
    """Cancel an in-progress run."""
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await stop_run(run_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/runs/{run_id}")
async def ws_endpoint(websocket: WebSocket, run_id: str):
    """
    Live message stream for a run.

    On connect:
      1. Replays all messages already persisted for this run (catch-up for
         late-joining or reconnecting clients).
      2. Sends the current run status so the UI can render the correct state.
      3. Stays open, forwarding any new broadcasts until the client disconnects.
    """
    await ws_manager.connect(run_id, websocket)
    try:
        # Replay historical messages
        messages = await get_messages(run_id)
        for msg in messages:
            await websocket.send_json(json.loads(msg["content"]))

        # Send current run status so the client starts in the right state
        run = await get_run(run_id)
        if run is not None:
            await websocket.send_json(
                {"type": "run_status", "status": run["status"]}
            )

        # Keep the connection alive; the server pushes via broadcast()
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)
