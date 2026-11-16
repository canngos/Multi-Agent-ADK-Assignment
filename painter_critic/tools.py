"""Drawing tools for the Painter agent.

Every tool draws many pixels at once on the shared 200x200 canvas.
Coordinates: (0, 0) is the top-left corner, x grows to the right, y grows
downwards, and both go from 0 to 199. Coordinates off the canvas are moved to
the nearest edge.

Tools never raise on bad input. They return {"status": "error", "message": ...}
so the model can read what went wrong and correct its next call.
"""

from __future__ import annotations

import json

from . import config
from .canvas import get_canvas, parse_color

_MAX = config.CANVAS_SIZE - 1


def _cmd(name: str, **kwargs) -> str:
    """A replayable command: tool name + JSON arguments, e.g.
    'draw_lines {"lines": [[0, 0, 9, 9]], "color": "red", "width": 2}'.

    JSON matches the format the model itself uses for tool-call arguments.
    (A Python-style 'draw_lines(lines=...)' got pasted into the JSON as a key.)
    """
    if "points" in kwargs:
        kwargs["points"] = [list(p) for p in kwargs["points"]]
    return f"{name} {json.dumps(kwargs)}"


def _ok(message: str, command: str) -> dict:
    get_canvas().record(message, command)
    return {"status": "success", "message": message}


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _int(value, name: str, low: int, high: int) -> int:
    """Validates a number argument and returns it as an int."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}.")
    number = int(round(value))
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {number}.")
    return number


def _coord(value, name: str) -> int:
    """Validates a coordinate. Values off the canvas are moved to the nearest
    edge (e.g. 200 -> 199): the visible result is the same, and an error here
    would only make the model waste calls on an off-by-one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}.")
    return min(max(int(round(value)), 0), _MAX)


def _points(points, minimum: int) -> list[tuple[int, int]]:
    """Validates a list of [x, y] pairs."""
    if not isinstance(points, (list, tuple)):
        raise ValueError("points must be a list of [x, y] pairs, e.g. [[10, 20], [30, 40]].")
    if len(points) < minimum:
        raise ValueError(f"points needs at least {minimum} [x, y] pairs, got {len(points)}.")
    if len(points) > config.MAX_POINTS:
        raise ValueError(f"points can have at most {config.MAX_POINTS} pairs, got {len(points)}.")
    result = []
    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"points[{i}] must be an [x, y] pair, got {point!r}.")
        result.append((_coord(point[0], f"points[{i}] x"), _coord(point[1], f"points[{i}] y")))
    return result


def fill_background(color: str) -> dict:
    """Fills the WHOLE canvas with one color, erasing everything drawn so far.

    Use it once at the start to set the background, or to start over.

    Args:
        color: A color name such as "skyblue" or a hex code such as "#87ceeb".
    """
    try:
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    canvas = get_canvas()
    canvas.draw.rectangle((0, 0, _MAX, _MAX), fill=rgb)
    canvas.history.clear()  # everything before is gone
    return _ok(f"Filled the whole canvas with {color}.", _cmd("fill_background", color=color))


def draw_rectangle(x1: int, y1: int, x2: int, y2: int, color: str) -> dict:
    """Draws a filled rectangle between two opposite corners.

    Good for large areas such as ground, sky bands, walls, doors and windows.

    Args:
        x1: x of the first corner (0-199).
        y1: y of the first corner (0-199).
        x2: x of the opposite corner (0-199).
        y2: y of the opposite corner (0-199).
        color: A color name such as "red" or a hex code such as "#ff0000".
    """
    try:
        x1, y1 = _coord(x1, "x1"), _coord(y1, "y1")
        x2, y2 = _coord(x2, "x2"), _coord(y2, "y2")
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    get_canvas().draw.rectangle((left, top, right, bottom), fill=rgb)
    return _ok(
        f"Drew a {color} rectangle from ({left}, {top}) to ({right}, {bottom}).",
        _cmd("draw_rectangle", x1=left, y1=top, x2=right, y2=bottom, color=color),
    )


def draw_ellipse(x: int, y: int, radius_x: int, radius_y: int, color: str) -> dict:
    """Draws a filled ellipse centered at (x, y). Use equal radii for a circle.

    Good for round things: sun, tree crowns, clouds, bushes, wheels. The shape
    may extend past the canvas edge; the outside part is simply cut off.

    Args:
        x: x of the center (0-199).
        y: y of the center (0-199).
        radius_x: Horizontal radius in pixels (1-200).
        radius_y: Vertical radius in pixels (1-200).
        color: A color name such as "yellow" or a hex code such as "#ffd700".
    """
    # (Parameters were center_x/center_y; the model kept dropping center_y.)
    try:
        cx, cy = _coord(x, "x"), _coord(y, "y")
        rx = _int(radius_x, "radius_x", 1, config.CANVAS_SIZE)
        ry = _int(radius_y, "radius_y", 1, config.CANVAS_SIZE)
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    get_canvas().draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=rgb)
    return _ok(
        f"Drew a {color} ellipse centered at ({cx}, {cy}) with radii {rx}x{ry}.",
        _cmd("draw_ellipse", x=cx, y=cy, radius_x=rx, radius_y=ry, color=color),
    )


def _segments(lines) -> list[tuple[int, int, int, int]]:
    """Validates a list of [x1, y1, x2, y2] line segments."""
    if not isinstance(lines, (list, tuple)):
        raise ValueError("lines must be a list of [x1, y1, x2, y2] segments, e.g. [[10, 20, 10, 40]].")
    if not 1 <= len(lines) <= config.MAX_POINTS:
        raise ValueError(f"lines needs 1 to {config.MAX_POINTS} segments, got {len(lines)}.")
    result = []
    for i, seg in enumerate(lines):
        if not isinstance(seg, (list, tuple)) or len(seg) != 4:
            raise ValueError(f"lines[{i}] must be [x1, y1, x2, y2], got {seg!r}.")
        result.append(tuple(_coord(v, f"lines[{i}][{j}]") for j, v in enumerate(seg)))
    return result


def draw_lines(lines: list[list[int]], color: str, width: int) -> dict:
    """Draws one or more straight lines, all with the same color and thickness.

    Good for thin or long details, and for many similar strokes at once: all
    fence posts in one call, all sun rays in one call, trunks, branches,
    window frames, outlines.

    Args:
        lines: Line segments as [x1, y1, x2, y2] lists (each value 0-199), at
            least 1, e.g. [[20, 170, 20, 190], [30, 170, 30, 190]] for two posts.
        color: A color name such as "brown" or a hex code such as "#8b4513".
        width: Line thickness in pixels (1-20).
    """
    try:
        segs = _segments(lines)
        w = _int(width, "width", 1, config.MAX_LINE_WIDTH)
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    draw = get_canvas().draw
    for seg in segs:
        draw.line(seg, fill=rgb, width=w)
    return _ok(
        f"Drew {len(segs)} {color} line{'s' if len(segs) != 1 else ''}, {w}px wide.",
        _cmd("draw_lines", lines=[list(seg) for seg in segs], color=color, width=w),
    )


def draw_polygon(points: list[list[int]], color: str) -> dict:
    """Draws a filled polygon through the given corner points, in order.

    Good for shapes with straight edges and angles: roofs (triangles), hills,
    mountains, irregular shapes.

    Args:
        points: Corner points as [x, y] pairs (each 0-199), at least 3,
            e.g. [[50, 100], [100, 50], [150, 100]] for a triangle.
        color: A color name such as "brown" or a hex code such as "#8b4513".
    """
    try:
        pts = _points(points, minimum=3)
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    get_canvas().draw.polygon(pts, fill=rgb)
    return _ok(
        f"Drew a {color} polygon with {len(pts)} corners: {pts}.",
        _cmd("draw_polygon", points=pts, color=color),
    )


def draw_dots(points: list[list[int]], color: str, dot_size: int) -> dict:
    """Draws a square dot of dot_size x dot_size pixels at each point.

    Good for small details and texture: flowers, stars, leaves, grass,
    windows panes, highlights.

    Args:
        points: Dot positions as [x, y] pairs (each 0-199), at least 1,
            e.g. [[20, 150], [35, 160], [50, 148]].
        color: A color name such as "white" or a hex code such as "#ffffff".
        dot_size: Width and height of each dot in pixels (1-10).
    """
    try:
        pts = _points(points, minimum=1)
        size = _int(dot_size, "dot_size", 1, config.MAX_DOT_SIZE)
        rgb = parse_color(color)
    except ValueError as e:
        return _error(str(e))
    draw = get_canvas().draw
    half = (size - 1) // 2
    for x, y in pts:
        draw.rectangle((x - half, y - half, x - half + size - 1, y - half + size - 1), fill=rgb)
    return _ok(
        f"Drew {len(pts)} {color} dots of size {size}px.",
        _cmd("draw_dots", points=pts, color=color, dot_size=size),
    )


PAINTER_TOOLS = [
    fill_background,
    draw_rectangle,
    draw_ellipse,
    draw_lines,
    draw_polygon,
    draw_dots,
]
