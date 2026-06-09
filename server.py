#!/usr/bin/env python3
"""
FastAPI backend for Agent Colosseum web UI.

Streams debate progress via Server-Sent Events so the Svelte frontend
can show rounds — and individual agent responses — appearing in real time.

Usage:
    uvicorn server:app --reload --port 8000
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from modes import MODES, DEFAULT_MODE
from colosseum import (
    TRANSCRIPT_DIR,
    auto_save_transcript,
    call_claude,
    get_round_style,
    run_round_stream,
    run_judge_full,
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

ALLOWED_MODELS = {"opus", "sonnet", "haiku", "fable"}

# "Diverse" spreads Claude tiers across the panel so disagreement is
# architectural, not just persona-deep. Assignment is by agent order, so
# follow-ups/extend reconstruct the same mapping from the stored selection.
DIVERSE_TIERS = ["opus", "sonnet", "haiku", "fable", "sonnet"]
DIVERSE_JUDGE = "sonnet"

# Sessions live in memory but are also persisted to disk so follow-ups and
# "extend" survive a backend restart.
_sessions: dict[str, dict] = {}
SESSION_DIR = TRANSCRIPT_DIR.parent / ".sessions"
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def _sse_event(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data)}


def _norm_model(model: str | None) -> str | None:
    return model if model in ALLOWED_MODELS else None


def _model_plan(requested: str | None, mode_dict: dict):
    """Resolve a model selection into (base_model, agent_models, judge_model).

    For "diverse", each agent gets a distinct tier and the judge runs on a
    fixed strong tier. Otherwise a single normalized model is used throughout.
    """
    if requested == "diverse":
        names = list(mode_dict["agents"].keys())
        agent_models = {n: DIVERSE_TIERS[i % len(DIVERSE_TIERS)] for i, n in enumerate(names)}
        return None, agent_models, DIVERSE_JUDGE
    m = _norm_model(requested)
    return m, None, m


def _resolve_repo(repo: str | None) -> str | None:
    """Return an absolute path if `repo` is an existing directory, else None."""
    if not repo or not repo.strip():
        return None
    p = Path(repo.strip()).expanduser()
    if p.is_dir():
        return str(p.resolve())
    return None


def _save_session(sid: str, data: dict) -> None:
    try:
        SESSION_DIR.mkdir(exist_ok=True)
        (SESSION_DIR / f"{sid}.json").write_text(json.dumps(data))
    except Exception:
        pass


def _load_session(sid: str) -> dict | None:
    if sid in _sessions:
        return _sessions[sid]
    if not _UUID_RE.match(sid):
        return None
    try:
        path = SESSION_DIR / f"{sid}.json"
        if path.is_file():
            data = json.loads(path.read_text())
            _sessions[sid] = data
            return data
    except Exception:
        pass
    return None


def _metrics_event(totals: dict, start: float) -> dict:
    return _sse_event("metrics", {
        "cost_usd": round(totals["cost"], 4),
        "input_tokens": totals["in"],
        "output_tokens": totals["out"],
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    })


_VERDICT_PRIORITY = [
    "tldr", "decision", "recommendation", "risk_posture", "correct_answer",
    "winning_idea", "verdict", "confidence",
]


def _verdict_label(key: str) -> str:
    key = key.replace("ninety_day", "90_day").replace("tldr", "TL;DR")
    if key == "TL;DR":
        return key
    return " ".join(w.capitalize() for w in key.split("_"))


def _verdict_to_text(s: dict) -> str:
    """Render any structured verdict (mode-specific schema) as markdown."""
    keys = [k for k in _VERDICT_PRIORITY if k in s]
    keys += [k for k in s if k not in keys]
    lines = []
    for k in keys:
        v = s.get(k)
        if v in (None, "", []):
            continue
        label = _verdict_label(k)
        if k == "tldr":
            lines.append(f"**TL;DR:** {v}")
        elif isinstance(v, str):
            lines.append(f"\n**{label}:** {v}")
        elif isinstance(v, list):
            lines.append(f"\n**{label}:**")
            for item in v:
                if isinstance(item, dict):
                    parts = [f"{_verdict_label(ik)}: {iv}" for ik, iv in item.items() if iv]
                    lines.append("- " + " — ".join(parts))
                else:
                    lines.append(f"- {item}")
    return "\n".join(lines)


async def _stream_round(
    kind: str,
    rnd: int | None,
    question: str,
    history: list,
    model: str | None,
    totals: dict,
    *,
    followup: str | None = None,
    verdict: str | None = None,
    event: str = "agent_response",
    repo: str | None = None,
    mode: dict | None = None,
    agent_models: dict | None = None,
):
    """Run one round, emitting an SSE event per agent as it completes.

    Accumulates cost/token totals and appends the completed round to history.
    """
    round_dict: dict[str, str] = {}
    async for name, res in run_round_stream(
        kind, question, history, model, followup, verdict, repo, mode, agent_models
    ):
        round_dict[name] = res.text
        totals["cost"] += res.cost_usd
        totals["in"] += res.input_tokens
        totals["out"] += res.output_tokens
        data = {"agent": name, "response": res.text, "model": res.model}
        if rnd is not None:
            data["round"] = rnd
        yield _sse_event(event, data)
    history.append(round_dict)


async def _judge_and_finish(
    session_id: str,
    question: str,
    history: list,
    mode_dict: dict,
    judge_model: str | None,
    session_model: str | None,
    agent_colors: dict,
    totals: dict,
    start: float,
    repo: str | None = None,
):
    """Shared tail: judge, emit verdict + metrics, persist, emit done."""
    yield _sse_event("judging", {"message": "Delivering verdict..."})
    structured = None
    try:
        jres = await run_judge_full(question, history, judge_model, repo=repo, mode=mode_dict)
        verdict = jres.text
        structured = jres.structured
        totals["cost"] += jres.cost_usd
        totals["in"] += jres.input_tokens
        totals["out"] += jres.output_tokens
    except ClaudeError as e:
        verdict = f"(Could not deliver verdict — {e})"

    verdict_text = _verdict_to_text(structured) if structured else verdict
    mode_key = mode_dict["name"]
    verdict_title = MODE_VERDICT_TITLES.get(mode_key, "VERDICT")
    yield _sse_event("verdict", {
        "verdict": verdict_text,
        "structured": structured,
        "title": verdict_title,
    })
    yield _metrics_event(totals, start)

    try:
        auto_save_transcript(question, history, verdict_text, mode=mode_dict)
    except Exception:
        pass

    session = {
        "question": question,
        "history": history,
        "verdict": verdict_text,
        "structured": structured,
        "mode": mode_key,
        "model": session_model,
        "repo": repo,
        "agents": agent_colors,
    }
    _sessions[session_id] = session
    _save_session(session_id, session)

    yield _sse_event("done", {"session_id": session_id})


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


IMPROVE_SYSTEM_PROMPT = (
    "You are an expert at crafting questions for multi-agent debates. "
    "Rewrite the user's topic into a single sharp, specific, and genuinely "
    "debatable prompt that will provoke substantive disagreement between agents. "
    "Keep it concise — one or two sentences. Preserve the user's intent and "
    "subject; do not answer it, add options, or include any commentary or quotes. "
    "Return ONLY the rewritten prompt text."
)


class ImproveRequest(BaseModel):
    question: str
    mode: str = DEFAULT_MODE
    model: str | None = None


@app.post("/api/improve-prompt")
async def improve_prompt(req: ImproveRequest):
    """Rewrite a raw question into a sharper, more debatable prompt."""
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Question is empty")
    if len(q) > 4000:
        raise HTTPException(status_code=422, detail="Question too long")

    mode_label = req.mode if req.mode in MODES else DEFAULT_MODE
    prompt = f"Debate mode: {mode_label}\n\nTopic to sharpen:\n{q}"
    try:
        result = await call_claude(prompt, IMPROVE_SYSTEM_PROMPT, _norm_model(req.model))
    except ClaudeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"improved": result.text}


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
    """Return the content of a saved transcript (+ re-run metadata if present)."""
    # Resolve and confirm the path stays inside TRANSCRIPT_DIR (no traversal).
    base = TRANSCRIPT_DIR.resolve()
    path = (base / filename).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Transcript not found")

    result = {"filename": path.name, "content": path.read_text()}
    # The sibling JSON carries the original question + mode for "Re-run".
    jpath = path.with_suffix(".json")
    if jpath.is_file():
        try:
            meta = json.loads(jpath.read_text())
            result["question"] = meta.get("question")
            mode = meta.get("mode")
            result["mode"] = mode if mode in MODES else None
        except Exception:
            pass
    return result


@app.get("/api/debate/stream")
async def stream_debate(
    question: str = Query(..., min_length=1, max_length=4000),
    mode: str = Query(default=DEFAULT_MODE),
    rounds: int = Query(default=3, ge=1, le=10),
    unlimited: bool = Query(default=False),
    model: str | None = Query(default=None),
    repo: str | None = Query(default=None),
):
    """Stream a debate via SSE, revealing each agent response as it completes."""
    if mode not in MODES:
        raise HTTPException(status_code=422, detail=f"Unknown mode: {mode}")
    requested_model = model
    repo_requested = bool(repo and repo.strip())
    repo = _resolve_repo(repo)

    async def event_generator():
        session_id = str(uuid.uuid4())

        # A repo path was given but doesn't exist / isn't a directory.
        if repo_requested and not repo:
            yield _sse_event("server_error", {
                "message": "Repo path not found or not a directory. Check the path and try again.",
            })
            return

        # Resolve mode locally — no module globals, so concurrent debates can't
        # corrupt each other.
        active_mode = MODES[mode]
        round_styles = active_mode["round_styles"]
        agent_colors = {name: cfg["color"] for name, cfg in active_mode["agents"].items()}
        base_model, agent_models, judge_model = _model_plan(requested_model, active_mode)

        yield _sse_event("session", {
            "session_id": session_id,
            "mode": mode,
            "model": requested_model,
            "repo": repo,
            "question": question,
            "agents": agent_colors,
        })

        history: list[dict[str, str]] = []
        totals = {"cost": 0.0, "in": 0, "out": 0}
        start = time.monotonic()

        def rnd_kwargs():
            return {"repo": repo, "mode": active_mode, "agent_models": agent_models}

        if unlimited:
            title, spinner = round_styles[0]
            yield _sse_event("round_start", {"round": 1, "title": title, "spinner": spinner})
            try:
                async for ev in _stream_round("independent", 1, question, history, base_model, totals, **rnd_kwargs()):
                    yield ev
            except ClaudeError as e:
                yield _sse_event("server_error", {"message": str(e)})
                return

            rnd = 2
            while True:
                title, spinner = get_round_style(rnd, round_styles)
                yield _sse_event("round_start", {"round": rnd, "title": title, "spinner": spinner})
                try:
                    async for ev in _stream_round("middle", rnd, question, history, base_model, totals, **rnd_kwargs()):
                        yield ev
                    rnd += 1
                except ClaudeError as e:
                    yield _sse_event("info", {"message": f"Stopped after {rnd - 1} rounds: {e}"})
                    break

            yield _sse_event("round_start", {
                "round": rnd, "title": "Final Commitment", "spinner": "Agents locking in...",
            })
            try:
                async for ev in _stream_round("commit", rnd, question, history, base_model, totals, **rnd_kwargs()):
                    yield ev
            except ClaudeError:
                yield _sse_event("info", {"message": "Could not run final round — going to verdict."})

        else:
            for rnd in range(1, rounds + 1):
                if rnd == 1:
                    title, spinner = round_styles[0]
                    kind = "independent"
                elif rnd == rounds:
                    title, spinner = "Final Commitment", "Agents locking in..."
                    kind = "commit"
                else:
                    title, spinner = get_round_style(rnd, round_styles)
                    kind = "middle"

                yield _sse_event("round_start", {"round": rnd, "title": title, "spinner": spinner})
                try:
                    async for ev in _stream_round(kind, rnd, question, history, base_model, totals, **rnd_kwargs()):
                        yield ev
                except ClaudeError as e:
                    yield _sse_event("server_error", {"message": str(e)})
                    return

        async for ev in _judge_and_finish(
            session_id, question, history, active_mode, judge_model,
            requested_model, agent_colors, totals, start, repo,
        ):
            yield ev

    return EventSourceResponse(event_generator())


@app.get("/api/followup/stream")
async def stream_followup(
    session_id: str = Query(...),
    followup: str = Query(..., min_length=1, max_length=4000),
):
    """Stream follow-up responses via SSE, one agent at a time."""
    session = _load_session(session_id)
    if not session:
        async def error_gen():
            yield _sse_event("server_error", {"message": "Session not found. Run a debate first."})
        return EventSourceResponse(error_gen())

    async def event_generator():
        active_mode = MODES.get(session.get("mode"))
        if active_mode is None:
            yield _sse_event("server_error", {"message": "Session mode is no longer available."})
            return
        base_model, agent_models, _ = _model_plan(session.get("model"), active_mode)
        repo = _resolve_repo(session.get("repo"))
        question = session["question"]
        history = session["history"]
        verdict = session["verdict"]
        totals = {"cost": 0.0, "in": 0, "out": 0}
        start = time.monotonic()

        yield _sse_event("followup_start", {"question": followup})

        try:
            async for ev in _stream_round(
                "followup", None, question, history, base_model, totals,
                followup=followup, verdict=verdict, event="followup_agent",
                repo=repo, mode=active_mode, agent_models=agent_models,
            ):
                yield ev
        except ClaudeError as e:
            yield _sse_event("server_error", {"message": str(e)})
            return

        yield _metrics_event(totals, start)

        try:
            auto_save_transcript(question, history, verdict, mode=active_mode)
        except Exception:
            pass

        session["history"] = history
        _sessions[session_id] = session
        _save_session(session_id, session)

        yield _sse_event("done", {"session_id": session_id})

    return EventSourceResponse(event_generator())


@app.get("/api/extend/stream")
async def stream_extend(
    session_id: str = Query(...),
    rounds: int = Query(default=2, ge=1, le=5),
):
    """Continue an existing debate for N more rounds, then re-judge."""
    session = _load_session(session_id)
    if not session:
        async def error_gen():
            yield _sse_event("server_error", {"message": "Session not found. Run a debate first."})
        return EventSourceResponse(error_gen())

    async def event_generator():
        active_mode = MODES.get(session.get("mode"))
        if active_mode is None:
            yield _sse_event("server_error", {"message": "Session mode is no longer available."})
            return
        requested_model = session.get("model")
        base_model, agent_models, judge_model = _model_plan(requested_model, active_mode)
        round_styles = active_mode["round_styles"]
        repo = _resolve_repo(session.get("repo"))
        question = session["question"]
        history = session["history"]
        agent_colors = session.get("agents", {})
        totals = {"cost": 0.0, "in": 0, "out": 0}
        start = time.monotonic()

        rnd_kwargs = {"repo": repo, "mode": active_mode, "agent_models": agent_models}

        base = len(history)
        # Additional debate rounds.
        for i in range(rounds):
            rnd = base + i + 1
            title, spinner = get_round_style(rnd, round_styles)
            yield _sse_event("round_start", {"round": rnd, "title": title, "spinner": spinner})
            try:
                async for ev in _stream_round("middle", rnd, question, history, base_model, totals, **rnd_kwargs):
                    yield ev
            except ClaudeError as e:
                yield _sse_event("info", {"message": f"Stopped after {i} more rounds: {e}"})
                break

        # Fresh commitment round.
        rnd = len(history) + 1
        yield _sse_event("round_start", {
            "round": rnd, "title": "Final Commitment", "spinner": "Agents locking in...",
        })
        try:
            async for ev in _stream_round("commit", rnd, question, history, base_model, totals, **rnd_kwargs):
                yield ev
        except ClaudeError:
            yield _sse_event("info", {"message": "Could not run final round — going to verdict."})

        async for ev in _judge_and_finish(
            session_id, question, history, active_mode, judge_model,
            requested_model, agent_colors, totals, start, repo,
        ):
            yield ev

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
