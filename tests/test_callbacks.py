import warnings

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

from painter_critic.callbacks import (
    AUTO_EXIT_KEY,
    RECOVERED_KEY,
    critic_after_model,
    painter_after_model,
)


def _response(*parts: types.Part) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=list(parts)))


def _calls(response: LlmResponse) -> list[str]:
    return [p.function_call.name for p in response.content.parts if p.function_call]


@pytest.mark.parametrize(
    "text",
    [
        "Score: 9/10\nDecision: STOP",
        "Score: 9/10\n**Decision:** STOP",
        "Score: 9/10\nDecision: **STOP**",
        "Score: 9/10\ndecision - stop",
    ],
)
def test_written_stop_without_call_gets_exit_loop(text):
    response = _response(types.Part(text=text))
    result = critic_after_model(None, response)
    assert result is response
    assert _calls(result) == ["exit_loop"]
    assert result.custom_metadata[AUTO_EXIT_KEY] is True


def test_stop_with_call_is_left_alone():
    response = _response(
        types.Part(text="Decision: STOP"),
        types.Part(function_call=types.FunctionCall(name="exit_loop", args={})),
    )
    assert critic_after_model(None, response) is None
    assert _calls(response) == ["exit_loop"]


@pytest.mark.parametrize(
    "text",
    [
        "Score: 6/10\nDecision: CONTINUE",
        "Score: 6/10\nThe Painter should not stop now.\nDecision: CONTINUE",
        "Next steps: 1. Stop drawing extra clouds.\nDecision: CONTINUE",
    ],
)
def test_continue_is_left_alone(text):
    response = _response(types.Part(text=text))
    assert critic_after_model(None, response) is None
    assert _calls(response) == []


# --- tool calls that leaked into the text -----------------------------------------

LEAKED = (
    '<|tool_call>call:draw_polygon {"points": [[0, 150], [70, 110], [199, 199]], '
    '"color": "limegreen"}<tool_call|>'
)


def _args(response, i=0):
    calls = [p.function_call for p in response.content.parts if p.function_call]
    return calls[i].name, dict(calls[i].args)


def test_leaked_painter_call_becomes_a_real_function_call():
    response = _response(types.Part(text=LEAKED))
    result = painter_after_model(None, response)
    assert result is response
    assert _args(result) == ("draw_polygon", {"points": [[0, 150], [70, 110], [199, 199]], "color": "limegreen"})
    assert not any(p.text for p in result.content.parts)
    assert result.custom_metadata[RECOVERED_KEY] == 1


def test_several_leaked_calls_and_surrounding_text():
    text = (
        "Next I draw the hill and the sun.\n"
        + LEAKED
        + '\n<|tool_call>call:draw_ellipse {"x": 30, "y": 30, "radius_x": 20, '
        '"radius_y": 20, "color": "yellow"}<tool_call|>'
    )
    result = painter_after_model(None, _response(types.Part(text=text)))
    assert _calls(result) == ["draw_polygon", "draw_ellipse"]
    assert [p.text for p in result.content.parts if p.text] == ["Next I draw the hill and the sun."]
    assert result.custom_metadata[RECOVERED_KEY] == 2


@pytest.mark.parametrize(
    "text",
    [
        "I finished the round: drew the house and the tree.",
        '<|tool_call>call:delete_everything {"x": 1}<tool_call|>',  # unknown tool
        "<|tool_call>call:draw_lines {not json}<tool_call|>",  # unparseable
    ],
)
def test_normal_or_unusable_text_is_left_alone(text):
    response = _response(types.Part(text=text))
    assert painter_after_model(None, response) is None
    assert _calls(response) == []


def test_leaked_exit_loop_in_critic_reply_is_recovered_once():
    response = _response(types.Part(text="Score: 9/10\nDecision: STOP\n<|tool_call>call:exit_loop {}<tool_call|>"))
    result = critic_after_model(None, response)
    assert _calls(result) == ["exit_loop"]  # recovered, not added a second time
    assert result.custom_metadata[RECOVERED_KEY] == 1
    assert AUTO_EXIT_KEY not in result.custom_metadata
