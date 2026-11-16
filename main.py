"""Runs the Painter–Critic drawing session.

The whole session is ONE call to `runner.run_async(...)`. The rounds are
orchestrated inside ADK by the LoopAgent; this script only prepares the session
and records the events the agents produce (console + conversation_log.md).

Usage:
    python main.py                      # full run, up to 30 rounds
    python main.py --max-rounds 3       # short test run
    python main.py --subject "A red sailboat on a calm blue sea at sunset"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

from google.adk.agents.run_config import RunConfig  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from painter_critic import config  # noqa: E402  (loads .env)
from painter_critic.agent import build_root_agent  # noqa: E402
from painter_critic.canvas import reset_canvas  # noqa: E402
from painter_critic.transcript import Transcript  # noqa: E402

APP_NAME = "painter_critic"
USER_ID = "student"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Painter–Critic drawing session (Google ADK).")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=config.MAX_ROUNDS,
        help=f"maximum number of rounds (default {config.MAX_ROUNDS})",
    )
    parser.add_argument("--subject", default=config.SUBJECT, help="what the Painter should draw")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="where images and the log go (default output/run_YYYYMMDD_HHMMSS)",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or Path(config.OUTPUT_ROOT) / f"run_{stamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    reset_canvas()
    root_agent = build_root_agent(max_rounds=args.max_rounds)
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={
            "subject": args.subject,
            "max_rounds": args.max_rounds,
            "output_dir": str(output_dir),
            "round": 0,
        },
    )

    transcript = Transcript(
        output_dir / "conversation_log.md",
        subject=args.subject,
        max_rounds=args.max_rounds,
        model=f"openai/{config.MODEL_ID}",
    )
    message = types.Content(
        role="user", parts=[types.Part(text=f"Please draw this subject: {args.subject}")]
    )
    error: BaseException | None = None
    try:
        # One single run: the LoopAgent drives all rounds internally.
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=config.MAX_LLM_CALLS),
        ):
            transcript.handle(event)
    except (Exception, KeyboardInterrupt, asyncio.CancelledError) as e:  # keep the partial log
        error = e
    finally:
        final = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )
        rounds = int(final.state.get("round", 0)) if final else 0
        transcript.finish(rounds, sorted(output_dir.glob("round_*.png")), error)
    if error is not None:
        traceback.print_exception(error)
        return 1
    return 0


def main() -> int:
    args = parse_args()
    if not os.getenv("LEHMUS_API_KEY"):
        print(
            "LEHMUS_API_KEY is not set.\n"
            "Copy .env.example to .env and put the Lehmus API key after LEHMUS_API_KEY=\n"
            "(the API only works from the University of Oulu network or VPN)."
        )
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
