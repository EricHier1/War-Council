# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Agent Colosseum — a multi-agent debate arena. Poses a question to 5 AI agents with distinct personalities, runs multiple rounds of debate/analysis, then a judge delivers a verdict. Uses `claude -p` subprocesses (not the Anthropic SDK) orchestrated with asyncio. Three interfaces: CLI, TUI, and web.

## Commands

```bash
# Backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# Frontend
cd web && npm install
cd web && npm run dev          # Dev server at localhost:5173
cd web && npm run build        # Production build
cd web && npm run check        # Svelte type checking

# CLI
python colosseum.py "question" --mode debate --rounds 3
python colosseum_tui.py        # TUI
```

The Vite dev server proxies `/api/*` to the FastAPI backend on port 8000.

## Architecture

**Engine layer** (`colosseum.py`): Spawns `claude -p` subprocesses via `asyncio.create_subprocess_exec`. All agents in a round run concurrently via `asyncio.gather`. Module-level globals hold the active mode state (`_active_mode`, `_active_agents`, etc.) set by `set_mode()`.

**Mode definitions** (`modes.py`): Each mode is a dict with `round_strategy` ("debate"=attack, "iterative"=build-on, "converge"=cross-check), 5 agents (name, Rich color, system_prompt), a judge_system_prompt, round_styles, and optional round_prompts for non-debate strategies. 6 modes: debate, plan, tech, startup, ethics, red-team.

**Web backend** (`server.py`): FastAPI wrapping the same engine. Streams debate progress via SSE (`sse_starlette`). Events: `session` > `round_start` > `round_responses` > `judging` > `verdict` > `done`. Sessions stored in-memory (`_sessions` dict) for follow-ups — lost on restart.

**Web frontend** (`web/`): SvelteKit 5 with runes (`$state`, `$derived`, `$bindable`). State lives in `+page.svelte`, 8 presentational components in `lib/components/`. EventSource connects to SSE endpoints. Theme system uses `data-theme` attribute on `<html>` with CSS custom properties in `app.css`.

## Key Patterns

**Adding a new mode**: Add a `*_MODE` dict to `modes.py` following the existing pattern (5 agents, judge prompt, round_styles with 7 entries, round_strategy, optional round_prompts). Register it in `MODES` dict. Add icon/verdict title to `MODE_ICONS` and `MODE_VERDICT_TITLES` in `colosseum.py`. The web UI, CLI, and TUI pick it up automatically.

**Agent colors**: Defined as Rich terminal color names in `modes.py` (`red`, `yellow`, `green`, `blue`, `magenta`, `bright_cyan`, `orange`). Mapped to CSS variables in `web/src/lib/colors.ts`. Both dark and light theme values defined in `app.css`.

**Markdown rendering**: `web/src/lib/markdown.ts` uses `marked` + `highlight.js` with manually registered languages. Shared prose styles live in `web/src/lib/styles/prose.css` and are imported by `RoundBlock` and `VerdictBlock`.

**Svelte components use `$bindable()` rune** for two-way props (question, selectedMode, etc. in DebateControls).

## Caveats

- No test suite exists yet.
- No linter/formatter configured.
- `colosseum.py` uses module-level mutable globals for mode state — not thread-safe, but fine since the server runs one debate at a time per SSE connection.
- The TUI (`colosseum_tui.py`) imports from `colosseum.py` and uses the same engine but may lag behind web features.
