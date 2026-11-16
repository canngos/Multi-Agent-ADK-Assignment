import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions
    from google.genai import types

from painter_critic.transcript import Transcript


def _call(author, name, args):
    return Event(
        author=author,
        content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]),
    )


def _result(author, name, response):
    return Event(
        author=author,
        content=types.Content(
            role="user", parts=[types.Part(function_response=types.FunctionResponse(name=name, response=response))]
        ),
    )


def _text(author, text):
    return Event(author=author, content=types.Content(role="model", parts=[types.Part(text=text)]))


def _run_two_rounds(transcript, critic_stops: bool):
    transcript.handle(_text("user", "Please draw this subject: a house"))
    for round_no in (1, 2):
        transcript.handle(_call("painter", "draw_rectangle", {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "color": "red"}))
        transcript.handle(_result("painter", "draw_rectangle", {"status": "success", "message": "Drew it."}))
        transcript.handle(_text("painter", f"Painter summary {round_no}"))
        transcript.handle(_text("critic", f"Score: {6 + round_no}/10\nDecision: CONTINUE"))
    if critic_stops:
        stop = _call("critic", "exit_loop", {})
        transcript.handle(stop)
        transcript.handle(
            Event(
                author="critic",
                content=types.Content(
                    role="user",
                    parts=[types.Part(function_response=types.FunctionResponse(name="exit_loop", response={}))],
                ),
                actions=EventActions(escalate=True, skip_summarization=True),
            )
        )


def test_log_has_rounds_tool_calls_images_and_reviews(tmp_path):
    log = tmp_path / "conversation_log.md"
    t = Transcript(log, subject="a house", max_rounds=30, model="openai/test")
    _run_two_rounds(t, critic_stops=True)
    t.finish(2, [tmp_path / "round_001.png", tmp_path / "round_002.png"])

    text = log.read_text(encoding="utf-8")
    assert "**Subject:** a house" in text
    assert text.count("## Round ") == 2
    assert text.count("### Painter") == 2 and text.count("### Critic") == 2
    assert '`draw_rectangle({"x1": 1, "y1": 2, "x2": 3, "y2": 4, "color": "red"})`' in text
    assert "Drew it." in text
    assert "![Round 1](round_001.png)" in text and "![Round 2](round_002.png)" in text
    assert "Painter summary 2" in text and "Score: 8/10" in text
    assert "called `exit_loop`" in text
    assert "the Critic called exit_loop in round 2" in text
    start = text.index("## Start message")
    assert start < text.index("Please draw this subject") < text.index("## Round 1")


def test_stop_reason_when_cap_is_reached(tmp_path):
    t = Transcript(tmp_path / "log.md", subject="a house", max_rounds=2, model="openai/test")
    _run_two_rounds(t, critic_stops=False)
    t.finish(2, [])
    assert "the maximum of 2 rounds was reached" in (tmp_path / "log.md").read_text(encoding="utf-8")


def test_error_is_written_to_log(tmp_path):
    t = Transcript(tmp_path / "log.md", subject="a house", max_rounds=30, model="openai/test")
    t.handle(_text("painter", "started"))
    t.finish(1, [], error=ConnectionError("VPN down"))
    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "ConnectionError: VPN down" in text
    assert "ended early" in text
