import json
import warnings

import pytest

from painter_critic import tools
from painter_critic.canvas import get_canvas, reset_canvas

RED = (255, 0, 0)
WHITE = (255, 255, 255)


@pytest.fixture(autouse=True)
def fresh_canvas():
    reset_canvas()
    yield


def px(x, y):
    return get_canvas().pixel(x, y)


def test_there_are_at_least_three_tools():
    assert len(tools.PAINTER_TOOLS) >= 3
    assert len({t.__name__ for t in tools.PAINTER_TOOLS}) == len(tools.PAINTER_TOOLS)


# --- successful drawing --------------------------------------------------------


def test_fill_background():
    result = tools.fill_background("skyblue")
    assert result["status"] == "success"
    assert px(0, 0) == px(199, 199) == (135, 206, 235)


def test_draw_rectangle_fills_area_and_accepts_any_corner_order():
    result = tools.draw_rectangle(60, 60, 20, 20, "red")
    assert result["status"] == "success"
    assert px(20, 20) == px(40, 40) == px(60, 60) == RED
    assert px(61, 61) == WHITE


def test_draw_ellipse_circle():
    result = tools.draw_ellipse(100, 100, 20, 20, "#00ff00")
    assert result["status"] == "success"
    assert px(100, 100) == (0, 255, 0)
    assert px(100, 85) == (0, 255, 0)
    assert px(82, 82) == WHITE  # corner of the bounding box is outside the circle


def test_draw_ellipse_may_extend_past_edge():
    result = tools.draw_ellipse(195, 5, 30, 30, "yellow")
    assert result["status"] == "success"
    assert px(199, 0) == (255, 255, 0)


def test_draw_line_with_width():
    result = tools.draw_lines([[10, 100, 190, 100]], "blue", 5)
    assert result["status"] == "success"
    assert px(100, 100) == (0, 0, 255)
    assert px(100, 102) == (0, 0, 255)
    assert px(100, 110) == WHITE


def test_draw_lines_draws_many_segments_in_one_call():
    posts = [[x, 170, x, 190] for x in range(10, 200, 20)]  # a whole fence
    result = tools.draw_lines(posts, "white", 3)
    assert result["status"] == "success"
    assert "10 white lines" in result["message"]
    assert all(px(x, 180) == WHITE for x in range(10, 200, 20))
    tools.fill_background("black")
    tools.draw_lines(posts, "white", 3)
    assert px(20, 180) == (0, 0, 0)  # gaps between posts stay empty
    assert len(get_canvas().history) == 2  # fill + ONE command for the fence


def test_draw_polygon_triangle():
    result = tools.draw_polygon([[50, 150], [100, 50], [150, 150]], "brown")
    assert result["status"] == "success"
    assert px(100, 120) == (165, 42, 42)
    assert px(55, 60) == WHITE


def test_draw_dots():
    result = tools.draw_dots([[20, 20], [180, 180]], "red", 3)
    assert result["status"] == "success"
    assert px(20, 20) == px(21, 21) == px(19, 19) == RED
    assert px(180, 180) == RED
    assert px(23, 23) == WHITE


def test_float_coordinates_are_rounded():
    result = tools.draw_rectangle(10.4, 10.6, 20.0, 20.0, "red")
    assert result["status"] == "success"
    assert "(10, 11)" in result["message"]


def test_off_canvas_coordinates_are_moved_to_the_edge():
    result = tools.draw_polygon([[0, 150], [100, 120], [200, 150], [200, 200], [-5, 200]], "green")
    assert result["status"] == "success"
    assert "(199, 199)" in result["message"] and "(0, 199)" in result["message"]
    assert px(199, 199) == (0, 128, 0)
    result = tools.draw_rectangle(-10, -10, 300, 20, "red")
    assert result["status"] == "success"
    assert px(0, 0) == px(199, 20) == RED


def test_successful_actions_are_recorded():
    tools.fill_background("white")
    tools.draw_rectangle(0, 0, 10, 10, "red")
    tools.draw_rectangle(0, 0, 30, 10, "no-such-color")  # error: not recorded
    assert len(get_canvas().actions) == 2


def test_history_holds_replayable_commands_since_last_fill():
    tools.draw_rectangle(0, 0, 10, 10, "red")
    tools.fill_background("skyblue")  # clears earlier history
    tools.draw_polygon([[0, 150], [100, 120], [199, 150]], "green")
    tools.draw_dots([[5, 5]], "white", 2)
    tools.draw_lines([[0, 0, 9, 9]], "red", 99)  # error: not recorded
    history = get_canvas().history
    assert history == [
        'fill_background {"color": "skyblue"}',
        'draw_polygon {"points": [[0, 150], [100, 120], [199, 150]], "color": "green"}',
        'draw_dots {"points": [[5, 5]], "color": "white", "dot_size": 2}',
    ]


def test_replaying_history_reproduces_the_image():
    tools.fill_background("skyblue")
    tools.draw_rectangle(40, 100, 100, 150, "firebrick")
    tools.draw_ellipse(150, 50, 20, 20, "gold")
    tools.draw_lines([[10, 10, 60, 30], [100, 10, 100, 60]], "black", 3)
    tools.draw_polygon([[30, 100], [70, 60], [110, 100]], "saddlebrown")
    tools.draw_dots([[20, 180], [30, 185]], "pink", 4)
    original = get_canvas().to_png_bytes()
    commands = list(get_canvas().history)

    reset_canvas()
    for command in commands:
        name, args = command.split(" ", 1)
        assert getattr(tools, name)(**json.loads(args))["status"] == "success"
    assert get_canvas().to_png_bytes() == original


# --- bad input returns an error instead of crashing ----------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: tools.fill_background("not-a-color"),
        lambda: tools.draw_rectangle("a", 0, 10, 10, "red"),
        lambda: tools.draw_rectangle(0, None, 10, 10, "red"),
        lambda: tools.draw_polygon([[0, 0], [10, "x"], [20, 20]], "red"),
        lambda: tools.draw_ellipse(100, 100, 0, 10, "red"),
        lambda: tools.draw_ellipse(100, 100, 10, 10, ""),
        lambda: tools.draw_lines([[0, 0, 10, 10]], "red", 0),
        lambda: tools.draw_lines([[0, 0, 10, 10]], "red", 50),
        lambda: tools.draw_lines([], "red", 2),
        lambda: tools.draw_lines([[0, 0, 10]], "red", 2),
        lambda: tools.draw_lines("0 0 10 10", "red", 2),
        lambda: tools.draw_polygon([[0, 0], [10, 10]], "red"),
        lambda: tools.draw_polygon([[0, 0], [10], [20, 20]], "red"),
        lambda: tools.draw_polygon("0,0 10,10 20,0", "red"),
        lambda: tools.draw_dots([], "red", 2),
        lambda: tools.draw_dots([[10, 10]], "red", 11),
        lambda: tools.draw_dots([[10, 10]] * 501, "red", 1),
    ],
)
def test_bad_input_returns_error_and_leaves_canvas_untouched(call):
    before = get_canvas().to_png_bytes()
    result = call()
    assert result["status"] == "error"
    assert result["message"]
    assert get_canvas().to_png_bytes() == before


# --- ADK can turn every tool into a function declaration for the model ---------


def test_adk_builds_function_declarations():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from google.adk.tools import FunctionTool

    # ADK 2.x puts the schema in `parameters_json_schema` (plain JSON Schema).
    for func in tools.PAINTER_TOOLS:
        decl = FunctionTool(func)._get_declaration()
        assert decl.name == func.__name__
        assert decl.description
        schema = decl.parameters_json_schema
        assert schema and schema["properties"]
        assert set(schema["required"]) == set(schema["properties"])

    schema = FunctionTool(tools.draw_polygon)._get_declaration().parameters_json_schema
    points = schema["properties"]["points"]
    assert points["type"] == "array"
    assert points["items"]["type"] == "array"
    assert points["items"]["items"]["type"] == "integer"
