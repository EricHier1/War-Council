#!/usr/bin/env python3
"""
FastAPI backend for Agent Colosseum web UI.

Streams debate progress via Server-Sent Events so the Svelte frontend
can show rounds appearing in real time.

Usage:
    uvicorn server:app --reload --port 8000
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from modes import MODES, DEFAULT_MODE
from colosseum import (
    TRANSCRIPT_DIR,
    auto_save_transcript,
    call_claude,
    set_mode,
    get_agents,
    get_mode,
    get_round_style,
    run_followup,
    run_judge,
    run_round_commit,
    run_round_independent,
    run_round_middle,
    ClaudeError,
    MODE_VERDICT_TITLES,
)

app = FastAPI(title="Agent Colosseum API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for active sessions (for follow-ups)
_sessions: dict[str, dict] = {}


def _sse_event(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data)}


@app.get("/api/modes")
def list_modes():
    """Return available modes and their agent configurations."""
    result = {}
    for key, mode in MODES.items():
        result[key] = {
            "name": mode["name"],
            "description": mode["description"],
            "agents": {
                name: {"color": cfg["color"]}
                for name, cfg in mode["agents"].items()
            },
        }
    return result


@app.get("/api/transcripts")
def list_transcripts():
    """Return list of saved transcripts."""
    if not TRANSCRIPT_DIR.exists():
        return []
    files = sorted(TRANSCRIPT_DIR.glob("*.md"), reverse=True)
    result = []
    for f in files:
        result.append({
            "filename": f.name,
            "stem": f.stem,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return result


@app.get("/api/transcripts/{filename}")
def get_transcript(filename: str):
    """Return the content of a saved transcript."""
    path = TRANSCRIPT_DIR / filename
    if not path.exists() or not path.is_file():
        return {"error": "Not found"}
    return {"filename": filename, "content": path.read_text()}


@app.get("/api/debate/stream")
async def stream_debate(
    question: str = Query(...),
    mode: str = Query(default=DEFAULT_MODE),
    rounds: int = Query(default=3),
    unlimited: bool = Query(default=False),
):
    """Stream a debate via SSE. Each event is a step in the debate."""

    async def event_generator():
        session_id = str(uuid.uuid4())
        set_mode(mode)
        agents = get_agents()
        active_mode = get_mode()
        round_styles = active_mode["round_styles"]

        agent_colors = {
            name: cfg["color"] for name, cfg in agents.items()
        }

        yield _sse_event("session", {
            "session_id": session_id,
            "mode": mode,
            "question": question,
            "agents": agent_colors,
        })

        history: list[dict[str, str]] = []

        if unlimited:
            # Round 1
            title, spinner = round_styles[0]
            yield _sse_event("round_start", {
                "round": 1, "title": title, "spinner": spinner,
            })
            try:
                responses = await run_round_independent(question)
            except ClaudeError as e:
                yield _sse_event("error", {"message": str(e)})
                return
            history.append(responses)
            yield _sse_event("round_responses", {
                "round": 1, "responses": responses,
            })

            # Middle rounds until failure
            rnd = 2
            while True:
                title, spinner = get_round_style(rnd)
                yield _sse_event("round_start", {
                    "round": rnd, "title": title, "spinner": spinner,
                })
                try:
                    responses = await run_round_middle(question, history)
                    history.append(responses)
                    yield _sse_event("round_responses", {
                        "round": rnd, "responses": responses,
                    })
                    rnd += 1
                except ClaudeError as e:
                    yield _sse_event("info", {
                        "message": f"Hit limit after {rnd - 1} rounds: {e}",
                    })
                    break

            # Commitment
            yield _sse_event("round_start", {
                "round": rnd, "title": "Final Commitment",
                "spinner": "Agents locking in...",
            })
            try:
                responses = await run_round_commit(question, history)
                history.append(responses)
                yield _sse_event("round_responses", {
                    "round": rnd, "responses": responses,
                })
            except ClaudeError:
                yield _sse_event("info", {
                    "message": "Could not run final round — going to verdict.",
                })

        else:
            # Fixed rounds
            for rnd in range(1, rounds + 1):
                if rnd == 1:
                    title, spinner = round_styles[0]
                elif rnd == rounds:
                    title = "Final Commitment"
                    spinner = "Agents locking in..."
                else:
                    title, spinner = get_round_style(rnd)

                yield _sse_event("round_start", {
                    "round": rnd, "title": title, "spinner": spinner,
                })

                try:
                    if rnd == 1:
                        responses = await run_round_independent(question)
                    elif rnd == rounds:
                        responses = await run_round_commit(question, history)
                    else:
                        responses = await run_round_middle(question, history)
                except ClaudeError as e:
                    yield _sse_event("error", {"message": str(e)})
                    return

                history.append(responses)
                yield _sse_event("round_responses", {
                    "round": rnd, "responses": responses,
                })

        # Judge
        yield _sse_event("judging", {"message": "Delivering verdict..."})
        try:
            verdict = await run_judge(question, history)
        except ClaudeError:
            verdict = "(Could not deliver verdict — context limit reached)"

        verdict_title = MODE_VERDICT_TITLES.get(mode, "VERDICT")
        yield _sse_event("verdict", {
            "verdict": verdict,
            "title": verdict_title,
        })

        # Auto-save
        try:
            auto_save_transcript(question, history, verdict)
        except Exception:
            pass

        # Store session for follow-ups
        _sessions[session_id] = {
            "question": question,
            "history": history,
            "verdict": verdict,
            "mode": mode,
        }

        yield _sse_event("done", {"session_id": session_id})

    return EventSourceResponse(event_generator())


@app.get("/api/followup/stream")
async def stream_followup(
    session_id: str = Query(...),
    followup: str = Query(...),
):
    """Stream follow-up responses via SSE."""
    session = _sessions.get(session_id)
    if not session:
        async def error_gen():
            yield _sse_event("error", {"message": "Session not found. Run a debate first."})
        return EventSourceResponse(error_gen())

    async def event_generator():
        set_mode(session["mode"])
        question = session["question"]
        history = session["history"]
        verdict = session["verdict"]

        yield _sse_event("followup_start", {"question": followup})

        try:
            responses = await run_followup(question, followup, history, verdict)
        except ClaudeError as e:
            yield _sse_event("error", {"message": str(e)})
            return

        history.append(responses)
        yield _sse_event("followup_responses", {"responses": responses})

        # Re-save transcript
        try:
            auto_save_transcript(question, history, verdict)
        except Exception:
            pass

        yield _sse_event("done", {"session_id": session_id})

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
