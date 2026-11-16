"""Phase 2 smoke test: checks that the Lehmus model works through ADK + LiteLLM.

Runs three checks against the real model (needs University network / VPN):
  1. text   - a plain question
  2. vision - an image sent as a google.genai Part with inline_data
  3. tools  - the model calls a Python function tool

Usage:  python scripts/smoke_test.py
"""

import asyncio
import io
import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw

warnings.filterwarnings("ignore", category=DeprecationWarning)

from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from painter_critic import config  # noqa: E402

MODEL = LiteLlm(
    model=f"openai/{config.MODEL_ID}",
    api_base=config.API_BASE,
    api_key=os.environ["LEHMUS_API_KEY"],
)

tool_calls: list[tuple[int, int]] = []


def add_numbers(a: int, b: int) -> dict:
    """Adds two integers and returns the sum.

    Args:
        a: The first integer.
        b: The second integer.
    """
    tool_calls.append((a, b))
    return {"sum": a + b}


def make_test_image() -> bytes:
    """A 200x200 PNG: blue background, red circle on the left, yellow square on the right."""
    img = Image.new("RGB", (200, 200), (30, 60, 200))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 60, 100, 140), fill=(220, 20, 20))
    draw.rectangle((120, 70, 180, 130), fill=(250, 220, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def ask(runner: InMemoryRunner, parts: list[types.Part]) -> str:
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="smoke"
    )
    text = []
    async for event in runner.run_async(
        user_id="smoke",
        session_id=session.id,
        new_message=types.Content(role="user", parts=parts),
    ):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    text.append(p.text)
                if p.function_call:
                    print(f"    [tool call] {p.function_call.name}({p.function_call.args})")
    return "".join(text).strip()


async def main() -> int:
    agent = LlmAgent(
        name="smoke_agent",
        model=MODEL,
        instruction="You are a concise assistant. When asked to add numbers, use the add_numbers tool.",
        tools=[add_numbers],
    )
    runner = InMemoryRunner(agent=agent, app_name="smoke")
    results = {}

    print("1) text")
    answer = await ask(runner, [types.Part(text="What is the capital of France? One word.")])
    print("   ->", answer)
    results["text"] = "paris" in answer.lower()

    print("2) vision")
    image_part = types.Part(inline_data=types.Blob(mime_type="image/png", data=make_test_image()))
    answer = await ask(
        runner,
        [
            types.Part(
                text="Describe this image: background color, and each shape with its color and "
                "position (left/right). Be brief."
            ),
            image_part,
        ],
    )
    print("   ->", answer)
    low = answer.lower()
    results["vision"] = all(w in low for w in ("blue", "red", "yellow"))

    print("3) tools")
    answer = await ask(runner, [types.Part(text="Use the tool to add 17 and 25. Tell me the result.")])
    print("   ->", answer)
    results["tools"] = bool(tool_calls) and "42" in answer

    print("4) vision via before_model_callback (include_contents='none')")

    def inject_image(callback_context, llm_request):
        llm_request.contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(text="This is the current image:"),
                    types.Part(inline_data=types.Blob(mime_type="image/png", data=make_test_image())),
                ],
            )
        )
        return None

    cb_agent = LlmAgent(
        name="callback_agent",
        model=MODEL,
        instruction="Answer briefly about the image you are shown.",
        include_contents="none",
        before_model_callback=inject_image,
    )
    cb_runner = InMemoryRunner(agent=cb_agent, app_name="smoke_cb")
    answer = await ask(cb_runner, [types.Part(text="What color is the circle, and what color is the square?")])
    print("   ->", answer)
    low = answer.lower()
    results["callback"] = "red" in low and "yellow" in low

    print()
    for name, ok in results.items():
        print(f"{name:7s} {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
