"""Agent definitions: Painter + Critic inside an ADK LoopAgent.

Design pattern: generator-critic loop. One LoopAgent iteration is one round:
the Painter draws, then the Critic reviews. The loop ends when the Critic calls
ADK's built-in `exit_loop` tool, or after `max_iterations` rounds.
"""

from __future__ import annotations

import os
import warnings

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import exit_loop

from . import callbacks, config
from .prompts import critic_instruction, painter_instruction
from .tools import PAINTER_TOOLS


def build_model() -> LiteLlm:
    """Gemma4 26B on Lehmus AI, via LiteLLM's OpenAI-compatible route."""
    return LiteLlm(
        model=f"openai/{config.MODEL_ID}",
        api_base=config.API_BASE,
        api_key=os.environ["LEHMUS_API_KEY"],
    )


def build_painter(model: LiteLlm) -> LlmAgent:
    return LlmAgent(
        name="painter",
        description="Draws and refines the picture on the canvas with drawing tools.",
        model=model,
        instruction=painter_instruction,
        tools=PAINTER_TOOLS,
        # Earlier rounds are left out: the instruction carries the latest
        # feedback and the callback shows the current canvas.
        include_contents="none",
        output_key="painter_summary",
        before_agent_callback=callbacks.painter_before_agent,
        before_model_callback=callbacks.painter_before_model,
        before_tool_callback=callbacks.painter_before_tool,
        after_model_callback=callbacks.painter_after_model,
        after_agent_callback=callbacks.painter_after_agent,
    )


def build_critic(model: LiteLlm) -> LlmAgent:
    return LlmAgent(
        name="critic",
        description="Reviews the rendered image and decides whether to continue.",
        model=model,
        instruction=critic_instruction,
        tools=[exit_loop],
        include_contents="none",
        output_key="critic_feedback",
        before_model_callback=callbacks.critic_before_model,
        after_model_callback=callbacks.critic_after_model,
    )


def build_root_agent(max_rounds: int = config.MAX_ROUNDS) -> LoopAgent:
    model = build_model()
    with warnings.catch_warnings():
        # ADK 2.14.1 marks LoopAgent as deprecated in favour of Workflow; the
        # assignment allows LoopAgent because the version is pinned.
        warnings.simplefilter("ignore", DeprecationWarning)
        return LoopAgent(
            name="painter_critic_loop",
            description="Painter and Critic take turns until the Critic stops.",
            sub_agents=[build_painter(model), build_critic(model)],
            max_iterations=max_rounds,
        )
