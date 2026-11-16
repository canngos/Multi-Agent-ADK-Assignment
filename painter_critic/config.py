"""Central settings for the Painter–Critic system."""

import os

from dotenv import load_dotenv

load_dotenv()  # read LEHMUS_* from .env before anything uses them

# What the Painter draws (the "subject prompt")
SUBJECT = (
    "A cozy countryside scene. A small red house with a brown triangular roof "
    "stands on a rolling green hill. The house has a wooden door, two windows "
    "with white frames, and a grey chimney with a puff of smoke. A light brown "
    "dirt path leads from the door down to the bottom of the picture. To the "
    "right of the house stands a tree with a brown trunk and a round green crown "
    "with a few red apples. A white picket fence runs along the bottom, small "
    "colorful flowers dot the grass, and in the blue sky there is a yellow sun "
    "with short rays and two white clouds."
)

# Rounds (one round = Painter turn + Critic turn)
MAX_ROUNDS = 30  # hard cap from the assignment; the Critic may stop earlier
MAX_TOOL_CALLS_PER_ROUND = 40  # safety cap on Painter tool calls (a full redraw needs ~25-35)
# ADK's default run limit is 500 model calls; 30 rounds can need more.
MAX_LLM_CALLS = MAX_ROUNDS * (MAX_TOOL_CALLS_PER_ROUND + 5)

# Model (Lehmus AI, OpenAI-compatible; values come from .env)
# `or` (not a getenv default) so that empty lines like "LEHMUS_MODEL_ID=" in .env
# still fall back to the defaults.
MODEL_ID = os.getenv("LEHMUS_MODEL_ID") or "wnofibsjlomanbprgbdp"
API_BASE = os.getenv("LEHMUS_API_BASE") or "https://api.lehmus-ai.oulu.fi/v1"

# Output
OUTPUT_ROOT = "output"  # each run writes to output/run_YYYYMMDD_HHMMSS/

# Canvas
CANVAS_SIZE = 200  # width and height in pixels (required by the assignment)
CANVAS_BACKGROUND = "white"  # starting color of the empty canvas

# The image shown to the model: upscaled with a labelled coordinate grid so the
# agents can read positions. Saved round images stay plain 200x200.
MODEL_VIEW_SCALE = 3  # 200 px -> 600 px
GRID_STEP = 20  # grid line every 20 canvas pixels, labelled every 40

# Tool limits (keep model mistakes from producing huge or invalid calls)
MAX_LINE_WIDTH = 20
MAX_DOT_SIZE = 10
MAX_POINTS = 500
