# Agent Colosseum

A multi-agent debate arena powered by Claude Code. Five AI agents with distinct personalities argue your question across multiple rounds, then a Judge delivers the final verdict.

No API keys, no SDK, no app — just `claude -p` subprocesses orchestrated with Python and `asyncio`.

## How it works

1. You pose a question
2. Five agents answer independently (Round 1)
3. Each agent attacks another's weakest argument (Round 2+)
4. Each agent commits to a final recommendation (last round)
5. A Judge reviews the full transcript and delivers a verdict
6. You ask follow-up questions — all agents respond with full debate context

All agents within a round run concurrently via `asyncio.gather`.

## The agents

| Agent | Role |
|---|---|
| **Pragmatist** | Ships and reduces risk. Dismissive of elegance and abstraction. |
| **Contrarian** | Finds the flaw in whatever's most popular. Never satisfied. |
| **Architect** | Thinks in systems and second-order consequences. Plays the long game. |
| **Executor** | Obsessed with momentum. Attacks overthinking and analysis paralysis. |
| **Devil's Advocate** | Takes the least popular position and argues it with full conviction. |

## Setup

```bash
pip install -r requirements.txt
```

For the web interface, also install the frontend dependencies:

```bash
cd web && npm install
```

Requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude` CLI) installed and authenticated.

## Usage

### Web interface

The recommended way to use Agent Colosseum. Run the backend and frontend in two terminals:

```bash
# Terminal 1 — API server
uvicorn server:app --reload --port 8000

# Terminal 2 — Svelte frontend
cd web && npm run dev
```

Open `http://localhost:5173`. The web UI features:

- Dark theme with color-coded agents
- Mode selector (debate / plan / tech)
- Round selector (3, 5, or unlimited)
- Real-time streaming — rounds appear as they complete via SSE
- Follow-up questions after the verdict
- Transcript browser sidebar
- Responsive mobile layout

### CLI mode

```bash
# Basic — 3 rounds + verdict
python colosseum.py "should I use SwiftData or CoreData?"

# More rounds for deeper debate
python colosseum.py "monolith or microservices?" --rounds 5

# Unlimited — keeps going until context limits hit
python colosseum.py "vim or emacs?" --unlimited

# Export to a specific file (in addition to auto-save)
python colosseum.py "tabs or spaces?" --output transcript.md

# Disable auto-save
python colosseum.py "React or Svelte?" --no-save
```

### Interactive TUI

```bash
python colosseum_tui.py
```

The TUI gives you a full terminal interface: type a question, pick your round count (3, 5, or unlimited), hit Launch, and watch the debate unfold live. A sidebar lists all saved transcripts — click any to view it. Keyboard shortcuts: `Ctrl+N` for new debate, `Ctrl+Q` to quit.

After the verdict, the CLI drops into an interactive follow-up prompt. Ask as many follow-up questions as you want — all five agents respond with the full debate as context. Type `quit` to exit. Use `--no-followup` to skip this.

In the TUI, a follow-up input appears at the bottom after every debate.

### CLI options

```
question              The question to debate
--rounds, -r N        Number of debate rounds (default: 3, min: 2)
--unlimited, -u       Keep debating until context/rate limits hit
--output, -o FILE     Export transcript to .md or .json
--no-save             Disable auto-saving to transcripts/
--no-followup         Skip interactive follow-up prompt
```

## Transcripts

Every debate auto-saves to a `transcripts/` folder as both `.md` and `.json` files, named with a timestamp and question slug (e.g. `20260326-143022_swiftdata-or-coredata.md`). Use `--no-save` to disable this, or `--output` to additionally write to a specific path.

## Architecture

```
colosseum.py       — Core debate engine (async, calls claude -p subprocesses)
modes.py           — Mode configs (agents, prompts, round styles)
server.py          — FastAPI backend with SSE streaming
web/               — SvelteKit frontend
colosseum_tui.py   — Terminal UI (Textual)
```

The web interface uses Server-Sent Events to stream debate progress in real time. The FastAPI server wraps the same `colosseum.py` engine used by the CLI and TUI, so all three interfaces produce identical results.

## Output

Terminal output uses Rich formatting — color-coded agents, round headers, spinners while waiting, and the Judge's verdict in a panel box. The TUI uses Textual for a full interactive experience with live-updating debate log and transcript browser. The web interface uses a dark-themed Svelte UI with live SSE streaming.
