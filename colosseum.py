#!/usr/bin/env python3
"""
Autonomous Agent Colosseum
==========================
Usage:
    python colosseum.py "should I use SwiftData or CoreData?"
    python colosseum.py "monolith or microservices?" --rounds 5 --mode debate
    python colosseum.py "design a real-time collab editor" --mode plan
    python colosseum.py "is it safe to use eval() in Python?" --mode tech
    python colosseum.py "vim or emacs?" --unlimited --output transcript.md

Modes:
    debate  — 5 agents argue, attack, commit, Judge picks a winner (default)
    plan    — 5 agents brainstorm, build on ideas, converge on an actionable plan
    tech    — 5 specialist engineers analyze, cross-check, converge on the correct answer

Requirements: pip install rich
"""

import argparse
import asyncio
import json
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from modes import MODES, DEFAULT_MODE

console = Console()

TRANSCRIPT_DIR = Path(__file__).parent / "transcripts"

# ── Active mode state (set in main, used by helpers) ─────────────────────────
# These are module-level so the TUI can import and set them too.

_active_mode = MODES[DEFAULT_MODE]
_active_agents = _active_mode["agents"]
_active_judge_prompt = _active_mode["judge_system_prompt"]
_active_round_styles = _active_mode["round_styles"]


def set_mode(mode_name: str):
    """Switch the active mode. Call before running any rounds."""
    global _active_mode, _active_agents, _active_judge_prompt, _active_round_styles
    _active_mode = MODES[mode_name]
    _active_agents = _active_mode["agents"]
    _active_judge_prompt = _active_mode["judge_system_prompt"]
    _active_round_styles = _active_mode["round_styles"]


def get_mode():
    return _active_mode


def get_agents():
    return _active_agents


# ── Subprocess helper ────────────────────────────────────────────────────────

class ClaudeError(Exception):
    """Raised when a claude subprocess fails."""
    pass


@dataclass
class ClaudeResult:
    """Parsed output of a single `claude -p --output-format json` call."""
    text: str
    cost_usd: float = 0.0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    structured: dict | None = None
    model: str | None = None


# Per-subprocess timeout (seconds). A single claude -p call that exceeds this
# is killed so one hung agent can't stall an entire round. Repo-grounded calls
# can take longer (the agent reads files), so they get a larger budget.
CLAUDE_TIMEOUT = 180
CLAUDE_TIMEOUT_REPO = 300

# Read-only tools granted to agents when a debate is grounded in a repo.
REPO_TOOLS = ["Read", "Grep", "Glob"]


async def call_claude(
    prompt: str,
    system_prompt: str,
    model: str | None = None,
    json_schema: dict | None = None,
    repo: str | None = None,
) -> ClaudeResult:
    """Run a single claude -p subprocess and return its parsed result.

    Uses --output-format json so we get usage/cost metrics alongside the text.
    When `repo` is set, the subprocess runs in that directory with read-only
    tools (Read/Grep/Glob) so the agent can inspect the codebase.
    The subprocess is killed if it exceeds the timeout or if the caller is
    cancelled (e.g. the web client disconnects), so we never leak processes.
    """
    args = [
        "claude", "-p", prompt,
        "--system-prompt", system_prompt,
        "--output-format", "json",
    ]
    if model:
        args += ["--model", model]
    if json_schema:
        args += ["--json-schema", json.dumps(json_schema)]
    if repo:
        args += ["--allowedTools", *REPO_TOOLS]

    timeout = CLAUDE_TIMEOUT_REPO if repo else CLAUDE_TIMEOUT

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo or None,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ClaudeError(f"claude timed out after {timeout}s")
    except asyncio.CancelledError:
        # Client disconnected or round aborted — don't leave the child running.
        proc.kill()
        await proc.wait()
        raise

    out = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        raise ClaudeError(err or f"claude exited with code {proc.returncode}")
    if not out:
        raise ClaudeError(err or "claude returned no output")

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise ClaudeError("Could not parse claude JSON output")

    if data.get("is_error"):
        raise ClaudeError(data.get("result") or "claude reported an error")

    usage = data.get("usage") or {}
    return ClaudeResult(
        text=(data.get("result") or "").strip(),
        cost_usd=float(data.get("total_cost_usd") or 0.0),
        duration_ms=int(data.get("duration_ms") or 0),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        structured=data.get("structured_output"),
    )


# ── Round runners ────────────────────────────────────────────────────────────

def build_history_block(history: list[dict[str, str]]) -> str:
    parts = []
    for i, rnd in enumerate(history, 1):
        parts.append(f"== Round {i} ==")
        for name, resp in rnd.items():
            parts.append(f"[{name}]: {resp}")
        parts.append("")
    return "\n".join(parts)


def _get_middle_prompt(question: str, history: list[dict[str, str]]) -> str:
    """Build the middle-round prompt based on mode strategy."""
    block = build_history_block(history)
    mode = _active_mode
    strategy = mode.get("round_strategy", "debate")

    if strategy == "debate":
        # Classic: attack a specific agent
        agent_names = list(_active_agents.keys())
        # We return a template; caller fills in target
        return None  # handled specially in run_round_middle

    # For iterative/converge modes, use custom prompt from config
    custom = mode.get("round_prompts", {}).get("middle", "")
    return (
        f"Original question: {question}\n\n"
        f"{block}\n"
        f"{custom}"
    )


def _get_last_prompt(
    question: str, history: list[dict[str, str]], mode: dict | None = None
) -> str:
    """Build the final-round prompt based on mode strategy."""
    block = build_history_block(history)
    mode = mode if mode is not None else _active_mode
    strategy = mode.get("round_strategy", "debate")

    if strategy == "debate":
        return (
            f"Original question: {question}\n\n"
            f"{block}\n"
            f"Now commit to ONE concrete recommendation. Be specific and actionable. "
            f"3-5 sentences max."
        )

    custom = mode.get("round_prompts", {}).get("last", "")
    return (
        f"Original question: {question}\n\n"
        f"{block}\n"
        f"{custom}"
    )


# Prepended to agent/judge prompts when a debate is grounded in a repo.
REPO_PREAMBLE = (
    "You have READ-ONLY access to a code repository in your current working "
    "directory. Use your Read, Grep, and Glob tools to inspect the actual files "
    "before forming your argument, and ground your points in specific code you "
    "find (cite file paths). Do not speculate about the code without checking.\n\n"
)


def _build_agent_prompt(
    name: str,
    question: str,
    history: list[dict[str, str]],
    kind: str,
    followup: str | None = None,
    verdict: str | None = None,
    repo: str | None = None,
    mode: dict | None = None,
) -> str:
    """Build the prompt for one agent for a given round kind."""
    block = build_history_block(history)
    m = mode if mode is not None else _active_mode
    agents = m["agents"]
    strategy = m.get("round_strategy", "debate")

    if kind == "independent":
        base = question
    elif kind == "middle":
        if strategy == "debate":
            targets = [n for n in agents if n != name]
            target = random.choice(targets) if targets else name
            base = (
                f"Original question: {question}\n\n"
                f"{block}\n"
                f"Now attack the weakest argument. Specifically target {target}'s position. "
                f"Explain why their reasoning is flawed. 3-5 sentences max."
            )
        else:
            custom = m.get("round_prompts", {}).get("middle", "")
            base = f"Original question: {question}\n\n{block}\n{custom}"
    elif kind == "commit":
        base = _get_last_prompt(question, history, m)
    elif kind == "followup":
        base = (
            f"Original question: {question}\n\n"
            f"{block}\n"
            f"== Judge's Verdict ==\n{verdict}\n\n"
            f"The user has a follow-up question: {followup}\n\n"
            f"Respond to this follow-up, informed by the full discussion. "
            f"Stay in character. 3-5 sentences max."
        )
    else:
        base = question

    return (REPO_PREAMBLE + base) if repo else base


async def run_round_stream(
    kind: str,
    question: str,
    history: list[dict[str, str]],
    model: str | None = None,
    followup: str | None = None,
    verdict: str | None = None,
    repo: str | None = None,
    mode: dict | None = None,
    agent_models: dict[str, str] | None = None,
):
    """Async-generator yielding (name, ClaudeResult) as each agent completes.

    Used by the web server to reveal responses one-by-one instead of waiting
    for the whole round. Raises ClaudeError if any agent's call fails.

    `mode` (the resolved mode dict) makes the call independent of the module
    globals; `agent_models` optionally assigns a distinct model per agent.
    """
    m = mode if mode is not None else _active_mode
    agents = m["agents"]

    async def one(name, cfg):
        prompt = _build_agent_prompt(name, question, history, kind, followup, verdict, repo, m)
        agent_model = (agent_models or {}).get(name) or model
        res = await call_claude(prompt, cfg["system_prompt"], agent_model, repo=repo)
        return name, res, agent_model

    coros = [one(n, c) for n, c in agents.items()]
    for fut in asyncio.as_completed(coros):
        name, res, agent_model = await fut
        res.model = agent_model
        yield name, res


async def _collect(
    kind: str,
    question: str,
    history: list[dict[str, str]],
    model: str | None = None,
    followup: str | None = None,
    verdict: str | None = None,
    repo: str | None = None,
) -> dict[str, str]:
    """Run a full round and return {agent: text} (for the CLI/TUI)."""
    out: dict[str, str] = {}
    async for name, res in run_round_stream(
        kind, question, history, model, followup, verdict, repo
    ):
        out[name] = res.text
    return out


async def run_round_independent(question: str, model: str | None = None) -> dict[str, str]:
    """Round 1: each agent answers independently."""
    return await _collect("independent", question, [], model)


async def run_round_middle(
    question: str, history: list[dict[str, str]], model: str | None = None
) -> dict[str, str]:
    """Middle rounds: behavior depends on mode strategy."""
    return await _collect("middle", question, history, model)


async def run_round_commit(
    question: str, history: list[dict[str, str]], model: str | None = None
) -> dict[str, str]:
    """Final round: behavior depends on mode strategy."""
    return await _collect("commit", question, history, model)


# Keep old name as alias for backward compat with TUI
run_round_attack = run_round_middle


async def run_followup(
    question: str, followup: str, history: list[dict[str, str]], verdict: str,
    model: str | None = None,
) -> dict[str, str]:
    """All agents respond to a follow-up question with full context."""
    return await _collect("followup", question, history, model, followup, verdict)


# Structured-verdict schemas used with `claude --json-schema`. Each mode gets a
# schema matching what its judge_system_prompt already asks for, so the verdict
# becomes a mode-specific decision artifact instead of a flat summary.
_CONFIDENCE = {"type": "string", "enum": ["low", "medium", "high"]}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

DEFAULT_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "string", "description": "One-sentence bottom line."},
        "decision": {"type": "string", "description": "The concrete answer or recommendation."},
        "confidence": _CONFIDENCE,
        "key_reasons": {**_STR_LIST, "description": "The 3-5 strongest reasons."},
        "strongest_dissent": {"type": "string", "description": "The best counterargument."},
        "winning_agent": {"type": "string", "description": "Who made the strongest case (or empty)."},
    },
    "required": ["tldr", "decision", "confidence", "key_reasons"],
}

VERDICT_SCHEMAS: dict[str, dict] = {
    "debate": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "One-sentence final verdict."},
            "winning_agent": {"type": "string", "description": "Who made the single strongest argument."},
            "strongest_argument": {"type": "string", "description": "The strongest argument made."},
            "unresolved_tension": {"type": "string", "description": "The key tension left unresolved."},
            "confidence": _CONFIDENCE,
        },
        "required": ["tldr", "winning_agent", "strongest_argument"],
    },
    "ethics": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "Nuanced one-sentence verdict."},
            "strongest_argument": {"type": "string"},
            "winning_agent": {"type": "string"},
            "core_tension": {"type": "string", "description": "The moral tension no framework resolves."},
            "additional_context": {"type": "string", "description": "What context would change the answer."},
            "confidence": _CONFIDENCE,
        },
        "required": ["tldr", "core_tension"],
    },
    "plan": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "One-sentence plan summary."},
            "winning_idea": {"type": "string"},
            "next_steps": {**_STR_LIST, "description": "3-5 concrete, actionable next steps."},
            "biggest_open_risk": {"type": "string"},
            "confidence": _CONFIDENCE,
        },
        "required": ["tldr", "winning_idea", "next_steps"],
    },
    "tech": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "The technically correct answer in one sentence."},
            "correct_answer": {"type": "string", "description": "The synthesized correct answer."},
            "confidence": _CONFIDENCE,
            "incorrect_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "correction": {"type": "string"},
                    },
                    "required": ["claim", "correction"],
                },
                "description": "Claims made during the debate that were wrong, with corrections.",
            },
            "caveats": {**_STR_LIST, "description": "Edge cases and caveats."},
        },
        "required": ["tldr", "correct_answer", "confidence"],
    },
    "startup": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "One-sentence investment take."},
            "recommendation": {"type": "string", "enum": ["GO", "CONDITIONAL_GO", "NO_GO"]},
            "strongest_reason": {"type": "string"},
            "biggest_risk": {"type": "string"},
            "must_be_true": {**_STR_LIST, "description": "Things that must be true for this to work."},
            "ninety_day_milestones": {**_STR_LIST, "description": "What you'd want to see in 90 days."},
            "confidence": _CONFIDENCE,
        },
        "required": ["tldr", "recommendation", "strongest_reason"],
    },
    "red-team": {
        "type": "object",
        "properties": {
            "tldr": {"type": "string", "description": "One-sentence risk summary."},
            "risk_posture": {"type": "string", "enum": ["RED", "YELLOW", "GREEN"]},
            "most_dangerous_flaw": {"type": "string", "description": "The single most dangerous flaw + worst case."},
            "vulnerabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                        "remediation": {"type": "string"},
                    },
                    "required": ["title", "severity"],
                },
                "description": "Vulnerabilities ranked by severity.",
            },
            "prioritized_fixes": {**_STR_LIST, "description": "Top 3-5 fixes in priority order."},
        },
        "required": ["tldr", "risk_posture", "most_dangerous_flaw"],
    },
}


def _build_judge_prompt(
    question: str, history: list[dict[str, str]], repo: str | None = None
) -> str:
    parts = []
    for i, rnd in enumerate(history, 1):
        parts.append(f"== ROUND {i} ==")
        for name, resp in rnd.items():
            parts.append(f"[{name}]: {resp}")
        parts.append("")
    base = (
        f"Original question: {question}\n\n"
        f"{''.join(chr(10) + p for p in parts)}\n\n"
        f"Now deliver your judgment."
    )
    return (REPO_PREAMBLE + base) if repo else base


async def run_judge_full(
    question: str,
    history: list[dict[str, str]],
    model: str | None = None,
    structured: bool = True,
    repo: str | None = None,
    mode: dict | None = None,
) -> ClaudeResult:
    """Judge the transcript, returning a (mode-specific) structured verdict."""
    m = mode if mode is not None else _active_mode
    prompt = _build_judge_prompt(question, history, repo)
    schema = VERDICT_SCHEMAS.get(m["name"], DEFAULT_VERDICT_SCHEMA) if structured else None
    return await call_claude(
        prompt, m["judge_system_prompt"], model, json_schema=schema, repo=repo
    )


async def run_judge(question: str, history: list[dict[str, str]]) -> str:
    """Final Judge/Reviewer call that reads the full transcript (CLI/TUI)."""
    res = await run_judge_full(question, history, structured=False)
    return res.text


# ── Display helpers ──────────────────────────────────────────────────────────

MODE_ICONS = {
    "debate": "🏛️",
    "plan": "🧠",
    "tech": "🔬",
    "startup": "🚀",
    "ethics": "⚖️",
    "red-team": "🔴",
}

MODE_VERDICT_TITLES = {
    "debate": "⚖️  JUDGE'S VERDICT",
    "plan": "📋  THE PLAN",
    "tech": "✅  TECHNICAL REVIEW",
    "startup": "🚀  INVESTMENT VERDICT",
    "ethics": "🏛️  ETHICAL VERDICT",
    "red-team": "🔴  RED TEAM REPORT",
}


def get_round_style(round_num: int, round_styles: list | None = None) -> tuple[str, str]:
    """Get title and spinner message for a given round number."""
    styles = round_styles if round_styles is not None else _active_round_styles
    idx = min(round_num - 1, len(styles) - 1)
    if round_num > len(styles):
        cycle = styles[1:-1] if len(styles) > 2 else styles
        idx = (round_num - 2) % len(cycle)
        return cycle[idx]
    return styles[idx]


def print_round_header(round_num: int, title: str):
    console.print()
    console.print(Rule(
        f"[bold white] ROUND {round_num} — {title} [/bold white]",
        style="bright_white",
    ))
    console.print()


def print_responses(responses: dict[str, str]):
    agents = _active_agents
    for name, response in responses.items():
        color = agents.get(name, {}).get("color", "white")
        console.print(f"  [{color} bold]{name}[/{color} bold]")
        console.print(f"  [{color}]{response}[/{color}]")
        console.print()


def print_judge_verdict(verdict: str):
    mode_name = _active_mode["name"]
    title = MODE_VERDICT_TITLES.get(mode_name, "⚖️  VERDICT")
    console.print()
    console.print(Panel(
        verdict,
        title=f"[bold bright_white]{title}[/bold bright_white]",
        border_style="bright_white",
        padding=(1, 2),
    ))


# ── Transcript export ────────────────────────────────────────────────────────

def export_transcript(
    question: str,
    history: list[dict[str, str]],
    verdict: str,
    output_path: str,
    mode_name: str = None,
    mode: dict | None = None,
):
    """Export the full debate transcript to markdown or JSON."""
    path = Path(output_path)
    ext = path.suffix.lower()
    m = mode if mode is not None else _active_mode
    mode_name = mode_name or m["name"]
    agents = m["agents"]
    round_styles = m["round_styles"]

    if ext == ".json":
        data = {
            "question": question,
            "mode": mode_name,
            "timestamp": datetime.now().isoformat(),
            "agents": list(agents.keys()),
            "rounds": [
                {
                    "round": i + 1,
                    "responses": dict(rnd.items()),
                }
                for i, rnd in enumerate(history)
            ],
            "verdict": verdict,
        }
        path.write_text(json.dumps(data, indent=2))
    else:
        verdict_header = MODE_VERDICT_TITLES.get(mode_name, "Verdict")
        lines = [
            f"# Agent Colosseum Transcript",
            f"",
            f"**Question:** {question}  ",
            f"**Mode:** {mode_name}  ",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"**Rounds:** {len(history)}  ",
            f"**Agents:** {', '.join(agents.keys())}",
            f"",
        ]
        for i, rnd in enumerate(history, 1):
            title, _ = get_round_style(i, round_styles)
            lines.append(f"---")
            lines.append(f"")
            lines.append(f"## Round {i} — {title}")
            lines.append(f"")
            for name, resp in rnd.items():
                lines.append(f"**{name}:** {resp}")
                lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {verdict_header}")
        lines.append(f"")
        lines.append(verdict)
        lines.append(f"")
        path.write_text("\n".join(lines))

    console.print(f"\n  [dim]Transcript saved to[/dim] [bold]{path}[/bold]")
    return path


def slugify(text: str, max_len: int = 40) -> str:
    """Turn a question into a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:max_len].rstrip("-")


def auto_save_transcript(
    question: str,
    history: list[dict[str, str]],
    verdict: str,
    mode: dict | None = None,
) -> Path:
    """Auto-save transcript to transcripts/ with a timestamped filename."""
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    m = mode if mode is not None else _active_mode
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode_name = m["name"]
    slug = slugify(question)
    md_path = TRANSCRIPT_DIR / f"{stamp}_{mode_name}_{slug}.md"
    json_path = TRANSCRIPT_DIR / f"{stamp}_{mode_name}_{slug}.json"
    export_transcript(question, history, verdict, str(md_path), mode=m)
    export_transcript(question, history, verdict, str(json_path), mode=m)
    return md_path


# ── Main ─────────────────────────────────────────────────────────────────────

def parse_args():
    mode_list = ", ".join(f"{k} — {v['description'][:50]}" for k, v in MODES.items())
    parser = argparse.ArgumentParser(
        description="Autonomous Agent Colosseum — multi-agent debate via claude CLI",
    )
    parser.add_argument("question", help="The question to debate")
    parser.add_argument(
        "--mode", "-m",
        type=str,
        default=DEFAULT_MODE,
        choices=MODES.keys(),
        help=f"Agent mode (default: {DEFAULT_MODE})",
    )
    parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=3,
        help="Number of debate rounds (default: 3, minimum: 2)",
    )
    parser.add_argument(
        "--unlimited", "-u",
        action="store_true",
        help="Keep debating until context/rate limits hit, then auto-close",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Export transcript to file (.md or .json)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Disable auto-saving transcripts to transcripts/ folder",
    )
    parser.add_argument(
        "--no-followup",
        action="store_true",
        help="Skip the interactive follow-up question prompt after the verdict",
    )
    args = parser.parse_args()
    if not args.unlimited and args.rounds < 2:
        parser.error("Need at least 2 rounds (opening + commitment)")
    return args


async def run_fixed(question: str, num_rounds: int) -> tuple[list[dict[str, str]], str]:
    """Run a fixed number of rounds + judge."""
    history: list[dict[str, str]] = []

    for rnd in range(1, num_rounds + 1):
        title, spinner_msg = get_round_style(rnd)

        if rnd == 1:
            title, spinner_msg = _active_round_styles[0]
        elif rnd == num_rounds:
            title = "Final Commitment"
            spinner_msg = "Agents locking in..."

        print_round_header(rnd, title)
        with console.status(f"[bold white]{spinner_msg}[/bold white]", spinner="dots"):
            if rnd == 1:
                responses = await run_round_independent(question)
            elif rnd == num_rounds:
                responses = await run_round_commit(question, history)
            else:
                responses = await run_round_middle(question, history)
        print_responses(responses)
        history.append(responses)

    with console.status("[bold white]Delivering verdict...[/bold white]", spinner="dots"):
        verdict = await run_judge(question, history)
    print_judge_verdict(verdict)

    return history, verdict


async def run_unlimited(question: str) -> tuple[list[dict[str, str]], str]:
    """Run rounds until claude fails, then close with commitment + judge."""
    history: list[dict[str, str]] = []

    # Round 1: independent
    title, spinner_msg = _active_round_styles[0]
    print_round_header(1, title)
    with console.status(f"[bold white]{spinner_msg}[/bold white]", spinner="dots"):
        responses = await run_round_independent(question)
    print_responses(responses)
    history.append(responses)

    # Middle rounds until failure
    rnd = 2
    while True:
        title, spinner_msg = get_round_style(rnd)
        print_round_header(rnd, title)
        try:
            with console.status(f"[bold white]{spinner_msg}[/bold white]", spinner="dots"):
                responses = await run_round_middle(question, history)
            print_responses(responses)
            history.append(responses)
            rnd += 1
        except ClaudeError as e:
            console.print(f"  [dim italic]Hit limit after {rnd - 1} rounds: {e}[/dim italic]")
            console.print(f"  [dim italic]Closing the session...[/dim italic]")
            break

    # Final commitment round
    print_round_header(rnd, "Final Commitment")
    try:
        with console.status("[bold white]Agents locking in...[/bold white]", spinner="dots"):
            responses = await run_round_commit(question, history)
        print_responses(responses)
        history.append(responses)
    except ClaudeError:
        console.print("  [dim italic]Could not run final round — going straight to verdict.[/dim italic]")

    # Judge
    try:
        with console.status("[bold white]Delivering verdict...[/bold white]", spinner="dots"):
            verdict = await run_judge(question, history)
        print_judge_verdict(verdict)
    except ClaudeError:
        verdict = "(Could not deliver verdict — context limit reached)"
        console.print()
        console.print(Panel(
            verdict,
            title="[bold bright_white]VERDICT[/bold bright_white]",
            border_style="dim",
            padding=(1, 2),
        ))

    return history, verdict


async def main():
    args = parse_args()
    question = args.question
    unlimited = args.unlimited

    # Activate the selected mode
    set_mode(args.mode)
    mode = get_mode()
    icon = MODE_ICONS.get(args.mode, "🏛️")
    agent_count = len(get_agents())

    rounds_label = "unlimited rounds" if unlimited else f"{args.rounds} rounds"
    subtitle = f"{agent_count} agents • {rounds_label} • 1 verdict"

    console.print()
    console.print(Panel(
        f"[bold]{question}[/bold]",
        title=f"[bold bright_white]{icon}  AGENT COLOSSEUM — {args.mode.upper()}[/bold bright_white]",
        subtitle=subtitle,
        border_style="bright_white",
        padding=(1, 2),
    ))

    if unlimited:
        history, verdict = await run_unlimited(question)
    else:
        history, verdict = await run_fixed(question, args.rounds)

    # Auto-save unless disabled
    if not args.no_save:
        auto_save_transcript(question, history, verdict)

    # Additional explicit export if requested
    if args.output:
        export_transcript(question, history, verdict, args.output)

    # Interactive follow-up loop
    if not args.no_followup:
        await followup_loop(question, history, verdict, save=not args.no_save)

    console.print()


async def followup_loop(
    question: str,
    history: list[dict[str, str]],
    verdict: str,
    save: bool = True,
):
    """Interactive loop for follow-up questions after the verdict."""
    followup_num = 0
    console.print()
    console.print(Rule("[bold white] FOLLOW-UP [/bold white]", style="dim"))
    console.print("  [dim]Ask a follow-up question (or type 'quit' to exit)[/dim]")

    while True:
        console.print()
        try:
            followup = console.input("[bold white]  > [/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not followup or followup.lower() in ("quit", "exit", "q"):
            break

        followup_num += 1
        rnd_label = f"Follow-up {followup_num}"

        console.print()
        console.print(Rule(
            f"[bold white] {rnd_label}: {followup} [/bold white]",
            style="dim",
        ))
        console.print()

        with console.status("[bold white]Agents responding...[/bold white]", spinner="dots"):
            try:
                responses = await run_followup(question, followup, history, verdict)
            except ClaudeError as e:
                console.print(f"  [dim italic]Error: {e}[/dim italic]")
                console.print("  [dim italic]Context may be too long for follow-ups.[/dim italic]")
                break

        print_responses(responses)
        history.append(responses)

        if save:
            auto_save_transcript(question, history, verdict)

    console.print()
    console.print("  [dim]Session ended.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
