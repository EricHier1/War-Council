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


async def call_claude(prompt: str, system_prompt: str) -> str:
    """Run a single claude -p subprocess and return its stdout."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--system-prompt", system_prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        raise ClaudeError(err or f"claude exited with code {proc.returncode}")
    if not output and err:
        raise ClaudeError(err)
    return output


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


def _get_last_prompt(question: str, history: list[dict[str, str]]) -> str:
    """Build the final-round prompt based on mode strategy."""
    block = build_history_block(history)
    mode = _active_mode
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


async def run_round_independent(question: str) -> dict[str, str]:
    """Round 1: each agent answers independently."""
    async def ask(name, cfg):
        return (name, await call_claude(question, cfg["system_prompt"]))

    results = await asyncio.gather(*[ask(n, c) for n, c in _active_agents.items()])
    return dict(results)


async def run_round_middle(
    question: str, history: list[dict[str, str]]
) -> dict[str, str]:
    """Middle rounds: behavior depends on mode strategy."""
    block = build_history_block(history)
    strategy = _active_mode.get("round_strategy", "debate")

    if strategy == "debate":
        # Attack mode: each agent targets another
        agent_names = list(_active_agents.keys())

        async def attack(name, cfg):
            targets = [n for n in agent_names if n != name]
            target = random.choice(targets)
            prompt = (
                f"Original question: {question}\n\n"
                f"{block}\n"
                f"Now attack the weakest argument. Specifically target {target}'s position. "
                f"Explain why their reasoning is flawed. 3-5 sentences max."
            )
            return (name, await call_claude(prompt, cfg["system_prompt"]))

        results = await asyncio.gather(*[attack(n, c) for n, c in _active_agents.items()])
    else:
        # Iterative/converge: use mode's custom middle prompt
        custom = _active_mode.get("round_prompts", {}).get("middle", "")
        prompt = (
            f"Original question: {question}\n\n"
            f"{block}\n"
            f"{custom}"
        )

        async def respond(name, cfg):
            return (name, await call_claude(prompt, cfg["system_prompt"]))

        results = await asyncio.gather(*[respond(n, c) for n, c in _active_agents.items()])

    return dict(results)


async def run_round_commit(
    question: str, history: list[dict[str, str]]
) -> dict[str, str]:
    """Final round: behavior depends on mode strategy."""
    prompt = _get_last_prompt(question, history)

    async def commit(name, cfg):
        return (name, await call_claude(prompt, cfg["system_prompt"]))

    results = await asyncio.gather(*[commit(n, c) for n, c in _active_agents.items()])
    return dict(results)


# Keep old name as alias for backward compat with TUI
run_round_attack = run_round_middle


async def run_followup(
    question: str, followup: str, history: list[dict[str, str]], verdict: str,
) -> dict[str, str]:
    """All agents respond to a follow-up question with full context."""
    block = build_history_block(history)

    async def respond(name, cfg):
        prompt = (
            f"Original question: {question}\n\n"
            f"{block}\n"
            f"== Judge's Verdict ==\n{verdict}\n\n"
            f"The user has a follow-up question: {followup}\n\n"
            f"Respond to this follow-up, informed by the full discussion. "
            f"Stay in character. 3-5 sentences max."
        )
        return (name, await call_claude(prompt, cfg["system_prompt"]))

    results = await asyncio.gather(*[respond(n, c) for n, c in _active_agents.items()])
    return dict(results)


async def run_judge(question: str, history: list[dict[str, str]]) -> str:
    """Final Judge/Reviewer call that reads the full transcript."""
    parts = []
    for i, rnd in enumerate(history, 1):
        parts.append(f"== ROUND {i} ==")
        for name, resp in rnd.items():
            parts.append(f"[{name}]: {resp}")
        parts.append("")

    prompt = (
        f"Original question: {question}\n\n"
        f"{''.join(chr(10) + p for p in parts)}\n\n"
        f"Now deliver your judgment."
    )
    return await call_claude(prompt, _active_judge_prompt)


# ── Display helpers ──────────────────────────────────────────────────────────

MODE_ICONS = {
    "debate": "🏛️",
    "plan": "🧠",
    "tech": "🔬",
}

MODE_VERDICT_TITLES = {
    "debate": "⚖️  JUDGE'S VERDICT",
    "plan": "📋  THE PLAN",
    "tech": "✅  TECHNICAL REVIEW",
}


def get_round_style(round_num: int) -> tuple[str, str]:
    """Get title and spinner message for a given round number."""
    styles = _active_round_styles
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
):
    """Export the full debate transcript to markdown or JSON."""
    path = Path(output_path)
    ext = path.suffix.lower()
    mode_name = mode_name or _active_mode["name"]
    agents = _active_agents

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
            title, _ = get_round_style(i)
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
) -> Path:
    """Auto-save transcript to transcripts/ with a timestamped filename."""
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode_name = _active_mode["name"]
    slug = slugify(question)
    md_path = TRANSCRIPT_DIR / f"{stamp}_{mode_name}_{slug}.md"
    json_path = TRANSCRIPT_DIR / f"{stamp}_{mode_name}_{slug}.json"
    export_transcript(question, history, verdict, str(md_path))
    export_transcript(question, history, verdict, str(json_path))
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
