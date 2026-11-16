"""ADK callbacks that connect the agents to the canvas.

- painter_before_agent:  starts a new round (round counter, per-round limits)
- painter_before_model:  shows the Painter the current canvas (grid view)
- painter_before_tool:   caps the number of tool calls per round
- painter_after_model:   recovers tool calls that the model sent as plain text
- painter_after_agent:   saves the round's image as round_NNN.png
- critic_before_model:   shows the Critic the saved image (+ grid view)
- critic_after_model:    turns a written "Decision: STOP" into the exit_loop call
                         when the model forgot to make it

Images are added to the model request as google.genai `types.Part` objects with
`inline_data`; LiteLLM turns them into OpenAI-style image messages.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from PIL import Image

from . import config
from .canvas import get_canvas
from .tools import PAINTER_TOOLS


def _png_part(data: bytes) -> types.Part:
    return types.Part(inline_data=types.Blob(mime_type="image/png", data=data))


def _ensure_defaults(state) -> None:
    """Fills in state that main.py normally provides, so the agents never miss it."""
    if not state.get("subject"):
        state["subject"] = config.SUBJECT
    if not state.get("max_rounds"):
        state["max_rounds"] = config.MAX_ROUNDS
    if not state.get("output_dir"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        state["output_dir"] = str(Path(config.OUTPUT_ROOT) / f"run_{stamp}")


# --- Painter -------------------------------------------------------------------


def painter_before_agent(callback_context: CallbackContext) -> None:
    state = callback_context.state
    _ensure_defaults(state)
    state["round"] = int(state.get("round") or 0) + 1
    state["tool_calls_this_round"] = 0
    state["fills_this_round"] = 0
    canvas = get_canvas()
    canvas.actions.clear()
    # Frozen copy for the Painter's instruction: a redraw clears the live
    # history, but the Painter still needs the full list it is replaying.
    state["start_history"] = list(canvas.history)
    return None


def painter_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
    canvas = get_canvas()
    n = len(canvas.actions)
    note = (
        f"Current canvas (round {callback_context.state.get('round')}, "
        f"{n} drawing action{'s' if n != 1 else ''} so far this round). "
        "Grid labels are canvas coordinates; the grid is not part of the drawing."
    )
    if int(callback_context.state.get("fills_this_round") or 0) >= 1:
        note += (
            " You already used fill_background this round: do not call it again, "
            "continue with the next shapes from your plan."
        )
    llm_request.contents.append(
        types.Content(role="user", parts=[types.Part(text=note), _png_part(canvas.to_grid_png_bytes())])
    )
    return None


def painter_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict | None:
    state = tool_context.state
    used = int(state.get("tool_calls_this_round") or 0) + 1
    state["tool_calls_this_round"] = used
    if used > config.MAX_TOOL_CALLS_PER_ROUND:
        # Returning a dict skips the real tool and sends this result to the model.
        return {
            "status": "error",
            "message": (
                f"Tool limit of {config.MAX_TOOL_CALLS_PER_ROUND} calls for this round reached. "
                "Stop drawing now and reply with your summary."
            ),
        }
    if tool.name == "fill_background":
        fills = int(state.get("fills_this_round") or 0) + 1
        state["fills_this_round"] = fills
        if fills > 1:
            # Guards against a loop of repeated restarts within one round.
            return {
                "status": "error",
                "message": (
                    "fill_background was already used this round, so the canvas is already "
                    "reset. Do not call it again. Continue by drawing the remaining shapes "
                    "with the other tools."
                ),
            }
    return None


def painter_after_agent(callback_context: CallbackContext) -> None:
    state = callback_context.state
    round_no = int(state.get("round") or 1)
    path = Path(state["output_dir"]) / f"round_{round_no:03d}.png"
    get_canvas().save(path)
    state["previous_image"] = state.get("last_image") or ""
    state["last_image"] = str(path)
    return None


# --- Critic --------------------------------------------------------------------


def _saved_image_upscaled(path: str) -> bytes:
    """Reads the saved round PNG and upscales it (pixel-exact) for the model."""
    with Image.open(path) as img:
        big = img.convert("RGB").resize(
            (img.width * config.MODEL_VIEW_SCALE, img.height * config.MODEL_VIEW_SCALE),
            Image.Resampling.NEAREST,
        )
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    return buf.getvalue()


# --- Recovering tool calls that arrive as text -----------------------------------

_LEAKED_CALL = re.compile(r"<\|tool_call\>\s*call:\s*(\w+)\s*(\{.*?\})\s*<tool_call\|>", re.DOTALL)
RECOVERED_KEY = "tool_calls_recovered_from_text"


def recover_text_tool_calls(llm_response: LlmResponse, allowed: set[str]) -> int:
    """Turns tool calls that leaked into the reply text into real function calls.

    Gemma sometimes emits its native tool-call markup as plain text, e.g.
    '<|tool_call>call:draw_polygon {"points": ...}<tool_call|>', instead of a
    structured tool call. ADK would then treat the reply as the agent's final
    answer and end its turn half-way (seen as a nearly blank canvas). This puts
    the call back into a proper function_call part so ADK executes it.
    Returns the number of recovered calls.
    """
    content = llm_response.content
    if not content or not content.parts or llm_response.partial:
        return 0
    new_parts: list[types.Part] = []
    calls: list[types.Part] = []
    for part in content.parts:
        if not part.text or part.thought or "<|tool_call>" not in part.text:
            new_parts.append(part)
            continue

        def _take(match: re.Match) -> str:
            name, raw_args = match.group(1), match.group(2)
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                return match.group(0)  # leave unparseable text as it is
            if name not in allowed or not isinstance(args, dict):
                return match.group(0)
            calls.append(types.Part(function_call=types.FunctionCall(name=name, args=args)))
            return ""

        leftover = _LEAKED_CALL.sub(_take, part.text).strip()
        if leftover:
            new_parts.append(types.Part(text=leftover))
    if not calls:
        return 0
    content.parts = new_parts + calls
    meta = dict(llm_response.custom_metadata or {})
    meta[RECOVERED_KEY] = meta.get(RECOVERED_KEY, 0) + len(calls)
    llm_response.custom_metadata = meta
    return len(calls)


_PAINTER_TOOL_NAMES = {f.__name__ for f in PAINTER_TOOLS}


def painter_after_model(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    return llm_response if recover_text_tool_calls(llm_response, _PAINTER_TOOL_NAMES) else None


# --- Critic stop ------------------------------------------------------------------

_STOP_DECISION = re.compile(r"^\W*decision\W*\s*stop\b", re.IGNORECASE | re.MULTILINE)
AUTO_EXIT_KEY = "exit_loop_added_from_written_decision"


def critic_after_model(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """Carries out a written 'Decision: STOP' that came without the exit_loop call.

    Gemma sometimes writes "Decision: STOP" but forgets to call exit_loop, so the
    loop would continue against the Critic's own decision. In that case this
    adds the exit_loop function call to the Critic's response; ADK then runs
    the built-in exit_loop tool as usual. The decision is still the Critic's.
    """
    recovered = recover_text_tool_calls(llm_response, {"exit_loop"})
    content = llm_response.content
    if not content or not content.parts or llm_response.partial:
        return None
    if any(p.function_call for p in content.parts):
        return llm_response if recovered else None
    text = "\n".join(p.text for p in content.parts if p.text and not p.thought)
    if not _STOP_DECISION.search(text):
        return None
    content.parts.append(types.Part(function_call=types.FunctionCall(name="exit_loop", args={})))
    llm_response.custom_metadata = {**(llm_response.custom_metadata or {}), AUTO_EXIT_KEY: True}
    return llm_response


def critic_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
    state = callback_context.state
    last_image = state.get("last_image")
    canvas = get_canvas()
    clean = _saved_image_upscaled(last_image) if last_image else canvas.to_png_bytes(config.MODEL_VIEW_SCALE)
    label = Path(last_image).name if last_image else "current canvas"
    parts = [
        types.Part(text=f"Image 1 - the clean drawing ({label}):"),
        _png_part(clean),
        types.Part(text="Image 2 - the same drawing with a coordinate grid:"),
        _png_part(canvas.to_grid_png_bytes()),
    ]
    previous = state.get("previous_image")
    if previous and Path(previous).exists():
        parts += [
            types.Part(
                text=f"Image 3 - the PREVIOUS round's drawing ({Path(previous).name}), "
                "only for comparison:"
            ),
            _png_part(_saved_image_upscaled(previous)),
        ]
    llm_request.contents.append(types.Content(role="user", parts=parts))
    return None
