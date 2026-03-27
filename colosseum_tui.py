#!/usr/bin/env python3
"""
Agent Colosseum TUI
===================
Usage:
    python colosseum_tui.py

Interactive terminal UI for launching debates, watching them live,
and browsing saved transcripts. Supports all modes: debate, plan, tech.

Requirements: pip install rich textual
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    RadioButton,
    RadioSet,
    Static,
)

from modes import MODES
from colosseum import (
    TRANSCRIPT_DIR,
    MODE_VERDICT_TITLES,
    auto_save_transcript,
    get_agents,
    get_round_style,
    run_followup,
    run_judge,
    run_round_attack,
    run_round_commit,
    run_round_independent,
    set_mode,
    ClaudeError,
)


# ── Transcript viewer screen ────────────────────────────────────────────────

class TranscriptScreen(ModalScreen):
    """Full-screen viewer for a saved transcript."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    TranscriptScreen {
        align: center middle;
    }
    TranscriptScreen > Vertical {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    TranscriptScreen Markdown {
        height: 1fr;
    }
    TranscriptScreen #close-btn {
        dock: bottom;
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, content: str, title: str = "Transcript"):
        super().__init__()
        self._content = content
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Markdown(self._content)
            yield Button("Close  [Esc]", id="close-btn", variant="default")

    @on(Button.Pressed, "#close-btn")
    def close_screen(self):
        self.dismiss()


# ── Main app ─────────────────────────────────────────────────────────────────

class ColosseumApp(App):
    """Interactive Agent Colosseum."""

    TITLE = "Agent Colosseum"
    CSS = """
    #app-grid {
        height: 1fr;
    }

    #sidebar {
        width: 32;
        border-right: thick $accent;
        padding: 1;
    }
    #sidebar Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #transcript-list {
        height: 1fr;
    }
    #transcript-list ListItem {
        padding: 0 1;
    }

    #main-area {
        width: 1fr;
        padding: 1 2;
    }

    #question-row {
        height: auto;
        margin-bottom: 1;
    }
    #question-input {
        width: 1fr;
    }
    #launch-btn {
        width: auto;
        min-width: 16;
        margin-left: 1;
    }

    #config-row {
        height: auto;
        margin-bottom: 1;
    }
    #config-row RadioButton {
        width: auto;
        margin-right: 2;
    }

    #mode-row {
        height: auto;
        margin-bottom: 1;
    }
    #mode-row RadioButton {
        width: auto;
        margin-right: 2;
    }
    #mode-row Label {
        width: auto;
        margin-right: 1;
        text-style: bold;
    }

    #debate-log {
        height: 1fr;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }

    .round-header {
        text-style: bold;
        color: $text;
        margin-top: 1;
        margin-bottom: 1;
    }
    .agent-name {
        text-style: bold;
    }
    .agent-response {
        margin-bottom: 1;
        margin-left: 2;
    }
    .verdict-box {
        margin-top: 1;
        padding: 1 2;
        border: tall $accent;
        text-style: bold;
        background: $boost;
    }
    .status-msg {
        text-style: italic;
        color: $text-muted;
    }

    #followup-row {
        height: auto;
        margin-top: 1;
    }
    #followup-input {
        width: 1fr;
    }
    #followup-btn {
        width: auto;
        min-width: 12;
        margin-left: 1;
    }
    .followup-header {
        text-style: bold italic;
        color: $warning;
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_debate", "New Debate"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._running = False
        self._debate_question: str = ""
        self._debate_history: list[dict[str, str]] = []
        self._debate_verdict: str = ""
        self._followup_num: int = 0
        self._current_mode: str = "debate"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="app-grid"):
            with Vertical(id="sidebar"):
                yield Label("Saved Transcripts")
                yield ListView(id="transcript-list")
                yield Button("Refresh", id="refresh-btn", variant="default")
            with Vertical(id="main-area"):
                with Horizontal(id="question-row"):
                    yield Input(
                        placeholder="Ask a question...",
                        id="question-input",
                    )
                    yield Button("Launch", id="launch-btn", variant="primary")
                with Horizontal(id="mode-row"):
                    yield Label("Mode:")
                    with RadioSet(id="mode-config"):
                        yield RadioButton("Debate", value=True)
                        yield RadioButton("Plan")
                        yield RadioButton("Tech")
                with Horizontal(id="config-row"):
                    yield Label("Rounds:")
                    with RadioSet(id="rounds-config"):
                        yield RadioButton("3", value=True)
                        yield RadioButton("5")
                        yield RadioButton("Unlimited")
                yield VerticalScroll(id="debate-log")
                with Horizontal(id="followup-row"):
                    yield Input(
                        placeholder="Ask a follow-up question...",
                        id="followup-input",
                        disabled=True,
                    )
                    yield Button("Ask", id="followup-btn", variant="warning", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_transcript_list()

    # ── Sidebar: transcript list ─────────────────────────────────────────

    def _refresh_transcript_list(self) -> None:
        lv = self.query_one("#transcript-list", ListView)
        lv.clear()
        if not TRANSCRIPT_DIR.exists():
            return
        md_files = sorted(TRANSCRIPT_DIR.glob("*.md"), reverse=True)
        for f in md_files:
            name = f.stem
            parts = name.split("_", 1)
            if len(parts) == 2:
                date_str, slug = parts
                label = f"{slug.replace('-', ' ')[:24]}  {date_str[:8]}"
            else:
                label = name[:32]
            item = ListItem(Label(label))
            item._transcript_path = f
            lv.append(item)

    @on(Button.Pressed, "#refresh-btn")
    def refresh_transcripts(self):
        self._refresh_transcript_list()

    @on(ListView.Selected, "#transcript-list")
    def open_transcript(self, event: ListView.Selected):
        path = getattr(event.item, "_transcript_path", None)
        if path and path.exists():
            content = path.read_text()
            self.push_screen(TranscriptScreen(content, title=path.stem))

    # ── Launch debate ────────────────────────────────────────────────────

    @on(Button.Pressed, "#launch-btn")
    def on_launch(self):
        self._start_debate()

    @on(Input.Submitted, "#question-input")
    def on_submit(self):
        self._start_debate()

    def action_new_debate(self):
        inp = self.query_one("#question-input", Input)
        inp.value = ""
        inp.focus()

    def _get_selected_mode(self) -> str:
        mode_set = self.query_one("#mode-config", RadioSet)
        idx = mode_set.pressed_index
        return ["debate", "plan", "tech"][idx]

    def _start_debate(self):
        if self._running:
            return
        inp = self.query_one("#question-input", Input)
        question = inp.value.strip()
        if not question:
            return

        # Determine mode
        mode_name = self._get_selected_mode()
        self._current_mode = mode_name
        set_mode(mode_name)

        # Determine rounds config
        radio_set = self.query_one("#rounds-config", RadioSet)
        idx = radio_set.pressed_index
        if idx == 0:
            rounds = 3
            unlimited = False
        elif idx == 1:
            rounds = 5
            unlimited = False
        else:
            rounds = 0
            unlimited = True

        # Reset state
        self._debate_question = question
        self._debate_history = []
        self._debate_verdict = ""
        self._followup_num = 0
        self._disable_followup()

        self._running = True
        self.query_one("#launch-btn", Button).disabled = True
        self._clear_log()
        self._run_debate(question, rounds, unlimited)

    def _clear_log(self):
        log = self.query_one("#debate-log", VerticalScroll)
        log.remove_children()

    def _log(self, widget):
        log = self.query_one("#debate-log", VerticalScroll)
        log.mount(widget)
        widget.scroll_visible()

    def _log_round_header(self, round_num: int, title: str):
        self._log(Static(
            f"━━━ ROUND {round_num} — {title} ━━━",
            classes="round-header",
        ))

    def _log_status(self, msg: str):
        self._log(Static(msg, classes="status-msg"))

    def _log_responses(self, responses: dict[str, str]):
        agents = get_agents()
        for name, resp in responses.items():
            color = agents.get(name, {}).get("color", "white")
            self._log(Static(f"[{color} bold]{name}[/]", classes="agent-name"))
            self._log(Static(resp, classes="agent-response"))

    def _log_verdict(self, verdict: str):
        title = MODE_VERDICT_TITLES.get(self._current_mode, "VERDICT")
        self._log(Static(
            f"{title}\n\n{verdict}",
            classes="verdict-box",
        ))

    def _enable_followup(self):
        self.query_one("#followup-input", Input).disabled = False
        self.query_one("#followup-btn", Button).disabled = False
        self.query_one("#followup-input", Input).focus()

    def _disable_followup(self):
        self.query_one("#followup-input", Input).disabled = True
        self.query_one("#followup-btn", Button).disabled = True

    def _finish_debate(self):
        self._running = False
        self.query_one("#launch-btn", Button).disabled = False
        self._refresh_transcript_list()
        self._enable_followup()

    # ── Follow-up questions ─────────────────────────────────────────────

    @on(Button.Pressed, "#followup-btn")
    def on_followup_btn(self):
        self._send_followup()

    @on(Input.Submitted, "#followup-input")
    def on_followup_submit(self):
        self._send_followup()

    def _send_followup(self):
        if self._running or not self._debate_verdict:
            return
        inp = self.query_one("#followup-input", Input)
        followup = inp.value.strip()
        if not followup:
            return
        inp.value = ""
        self._running = True
        self._disable_followup()
        self.query_one("#launch-btn", Button).disabled = True
        self._run_followup(followup)

    @work(thread=False)
    async def _run_followup(self, followup: str):
        self._followup_num += 1
        self._log(Static(
            f"━━━ Follow-up {self._followup_num}: {followup} ━━━",
            classes="followup-header",
        ))
        self._log_status("Agents responding...")
        try:
            responses = await run_followup(
                self._debate_question, followup,
                self._debate_history, self._debate_verdict,
            )
            self._log_responses(responses)
            self._debate_history.append(responses)
            auto_save_transcript(
                self._debate_question, self._debate_history, self._debate_verdict,
            )
            self._log_status("Updated transcript saved.")
        except ClaudeError as e:
            self._log_status(f"Error: {e}")

        self._running = False
        self.query_one("#launch-btn", Button).disabled = False
        self._enable_followup()
        self._refresh_transcript_list()

    # ── Run debate ───────────────────────────────────────────────────────

    @work(thread=False)
    async def _run_debate(self, question: str, rounds: int, unlimited: bool):
        try:
            if unlimited:
                await self._run_unlimited(question)
            else:
                await self._run_fixed(question, rounds)
        except Exception as e:
            self._log_status(f"Error: {e}")

        self._finish_debate()

    async def _run_fixed(self, question: str, num_rounds: int):
        history = self._debate_history

        # Round 1
        title, spinner = get_round_style(1)
        self._log_round_header(1, title)
        self._log_status(spinner)
        responses = await run_round_independent(question)
        self._log_responses(responses)
        history.append(responses)

        # Middle rounds
        for rnd in range(2, num_rounds):
            title, spinner = get_round_style(rnd)
            self._log_round_header(rnd, title)
            self._log_status(spinner)
            responses = await run_round_attack(question, history)
            self._log_responses(responses)
            history.append(responses)

        # Final commitment
        self._log_round_header(num_rounds, "Final Commitment")
        self._log_status("Agents locking in...")
        responses = await run_round_commit(question, history)
        self._log_responses(responses)
        history.append(responses)

        # Judge
        self._log_status("Delivering verdict...")
        verdict = await run_judge(question, history)
        self._debate_verdict = verdict
        self._log_verdict(verdict)

        auto_save_transcript(question, history, verdict)
        self._log_status("Transcript auto-saved. Ask a follow-up below!")

    async def _run_unlimited(self, question: str):
        history = self._debate_history

        # Round 1
        title, spinner = get_round_style(1)
        self._log_round_header(1, title)
        self._log_status(spinner)
        responses = await run_round_independent(question)
        self._log_responses(responses)
        history.append(responses)

        # Middle rounds until failure
        rnd = 2
        while True:
            title, spinner = get_round_style(rnd)
            self._log_round_header(rnd, title)
            self._log_status(spinner)
            try:
                responses = await run_round_attack(question, history)
                self._log_responses(responses)
                history.append(responses)
                rnd += 1
            except ClaudeError as e:
                self._log_status(f"Hit limit after {rnd - 1} rounds: {e}")
                self._log_status("Closing the session...")
                break

        # Commitment
        self._log_round_header(rnd, "Final Commitment")
        self._log_status("Agents locking in...")
        try:
            responses = await run_round_commit(question, history)
            self._log_responses(responses)
            history.append(responses)
        except ClaudeError:
            self._log_status("Could not run final round — going to verdict.")

        # Judge
        self._log_status("Delivering verdict...")
        try:
            verdict = await run_judge(question, history)
            self._debate_verdict = verdict
            self._log_verdict(verdict)
        except ClaudeError:
            verdict = "(Could not deliver verdict — context limit reached)"
            self._debate_verdict = verdict
            self._log_verdict(verdict)

        auto_save_transcript(question, history, verdict)
        self._log_status("Transcript auto-saved. Ask a follow-up below!")


if __name__ == "__main__":
    app = ColosseumApp()
    app.run()
