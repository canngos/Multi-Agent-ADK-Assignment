"""Turns the ADK event stream into a transcript, on the console and in a file.

The file (conversation_log.md) is Markdown: one section per round with every
Painter tool call and result, the Painter's summary, the round image, and the
Critic's full review. It is written line by line, so a partial log survives
even if the run is interrupted.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from google.adk.events.event import Event

from .callbacks import AUTO_EXIT_KEY, RECOVERED_KEY

AGENTS = ("painter", "critic")


def _json(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _short(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit] + " …"


class Transcript:
    def __init__(self, log_path: Path, subject: str, max_rounds: int, model: str) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.log_path.open("w", encoding="utf-8")
        self.max_rounds = max_rounds
        self.round = 0
        self.last_author: str | None = None
        self.stopped_by_critic = False
        self.started = time.monotonic()
        self.round_started = self.started

        self._console(f"Subject: {subject}")
        self._console(f"Max rounds: {max_rounds}   Log: {self.log_path}")
        self._md("# Painter–Critic conversation log")
        self._md()
        self._md(f"- **Subject:** {subject}")
        self._md(f"- **Started:** {datetime.now():%Y-%m-%d %H:%M:%S}")
        self._md(f"- **Max rounds:** {max_rounds}")
        self._md(f"- **Model:** {model} (both agents)")

    # --- output helpers --------------------------------------------------------

    def _console(self, line: str = "") -> None:
        print(line, flush=True)

    def _md(self, line: str = "") -> None:
        self._file.write(line + "\n")
        self._file.flush()

    def _both(self, console: str, md: str | None = None) -> None:
        self._console(console)
        self._md(console if md is None else md)

    # --- events ----------------------------------------------------------------

    def _start_section(self, author: str) -> None:
        if author == "painter":
            self.round += 1
            self.round_started = time.monotonic()
            self._console()
            self._console("=" * 70)
            self._console(f"ROUND {self.round}")
            self._console("=" * 70)
            self._md()
            self._md(f"## Round {self.round}")
        if author == "critic" and self.last_author == "painter":
            # The Painter's after_agent callback has saved the image by now.
            image = f"round_{self.round:03d}.png"
            self._console(f"[image saved] {image}")
            self._md()
            self._md(f"**Canvas after the Painter's turn** (`{image}`):")
            self._md()
            self._md(f"![Round {self.round}]({image})")
        self._console(f"\n--- {author.upper()} ---")
        self._md()
        self._md(f"### {author.capitalize()}")
        self._md()

    def handle(self, event: Event) -> None:
        author = event.author
        if author in AGENTS and author != self.last_author:
            self._start_section(author)
        elif author == "user" and self.last_author is None:
            self._md()
            self._md("## Start message (user → loop)")
        if author in AGENTS:
            self.last_author = author

        if recovered := (event.custom_metadata or {}).get(RECOVERED_KEY):
            self._both(
                f"[note] {recovered} tool call(s) arrived as plain text; "
                "the after_model_callback turned them into real tool calls.",
                f"> _Note: {recovered} tool call(s) arrived as plain text "
                "(`<|tool_call>…`); the `after_model_callback` turned them into real tool calls._",
            )
        if (event.custom_metadata or {}).get(AUTO_EXIT_KEY):
            self._both(
                "[note] The Critic wrote 'Decision: STOP' without calling exit_loop; "
                "the after_model_callback added the exit_loop call.",
                "> _Note: the Critic wrote \"Decision: STOP\" without calling `exit_loop`; "
                "the Critic's `after_model_callback` added the `exit_loop` call._",
            )
        if not event.partial and event.content and event.content.parts:
            for part in event.content.parts:
                if part.thought:
                    continue
                if part.function_call:
                    fc = part.function_call
                    args = _json(fc.args or {})
                    self._both(f"[tool call] {fc.name}({_short(args)})", f"- 🛠️ `{fc.name}({args})`")
                elif part.function_response:
                    fr = part.function_response
                    resp = _json(fr.response or {})
                    self._both(f"[tool result] {fr.name}: {_short(resp)}", f"  - ↳ `{resp}`")
                elif part.text and part.text.strip():
                    text = part.text.strip()
                    self._console(text)
                    self._md()
                    self._md(text)

        if event.actions and event.actions.escalate:
            self.stopped_by_critic = True
            self._both(
                f"\n>>> {author} called exit_loop: the Critic stopped the drawing session.",
                f"\n> **{author.capitalize()} called `exit_loop`: the drawing session is stopped.**",
            )
        if author == "critic" and event.is_final_response():
            took = time.monotonic() - self.round_started
            self._both(f"(round {self.round} took {took:.0f}s)", f"\n_Round {self.round} took {took:.0f}s._")

    # --- end of run ------------------------------------------------------------

    def stop_reason(self, rounds: int) -> str:
        if self.stopped_by_critic:
            return f"the Critic called exit_loop in round {rounds}"
        if rounds >= self.max_rounds:
            return f"the maximum of {self.max_rounds} rounds was reached"
        return "the run ended early (see error above)"

    def finish(self, rounds: int, images: list[Path], error: BaseException | None = None) -> None:
        elapsed = time.monotonic() - self.started
        reason = self.stop_reason(rounds)
        self._console()
        self._console("=" * 70)
        if error is not None:
            self._console(f"ERROR: {type(error).__name__}: {error}")
        self._console(f"Finished after {rounds} round(s) in {elapsed:.0f}s: {reason}.")
        self._console(f"{len(images)} image(s) and the log are in {self.log_path.parent}")

        self._md()
        self._md("## Result")
        self._md()
        if error is not None:
            self._md(f"- **Error:** `{type(error).__name__}: {error}`")
        self._md(f"- **Rounds:** {rounds}")
        self._md(f"- **Stopped because:** {reason}")
        self._md(f"- **Duration:** {elapsed:.0f}s")
        self._md(f"- **Images:** {', '.join(p.name for p in images) or 'none'}")
        self._file.close()
