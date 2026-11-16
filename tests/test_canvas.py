import io

import pytest
from PIL import Image

from painter_critic import config
from painter_critic.canvas import Canvas, get_canvas, parse_color, reset_canvas


def test_new_canvas_is_200x200_white():
    canvas = Canvas()
    assert canvas.image.size == (200, 200)
    assert canvas.pixel(0, 0) == (255, 255, 255)
    assert canvas.pixel(199, 199) == (255, 255, 255)


def test_parse_color_accepts_names_and_hex():
    assert parse_color("red") == (255, 0, 0)
    assert parse_color("#00ff00") == (0, 255, 0)
    assert parse_color("  SkyBlue ") == (135, 206, 235)
    assert parse_color('"yellow"') == (255, 255, 0)  # model sometimes adds quotes
    assert parse_color("'#00ff00'") == (0, 255, 0)


@pytest.mark.parametrize("bad", ["", "notacolor", "#12", None, 5])
def test_parse_color_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_color(bad)


def test_reset_clears_drawing_and_actions():
    canvas = Canvas()
    canvas.draw.rectangle((0, 0, 50, 50), fill=(255, 0, 0))
    canvas.record("something")
    canvas.reset("black")
    assert canvas.pixel(10, 10) == (0, 0, 0)
    assert canvas.actions == []


def test_png_bytes_round_trip():
    canvas = Canvas()
    canvas.draw.rectangle((10, 10, 20, 20), fill=(0, 0, 255))
    img = Image.open(io.BytesIO(canvas.to_png_bytes()))
    assert img.format == "PNG"
    assert img.size == (200, 200)
    assert img.convert("RGB").getpixel((15, 15)) == (0, 0, 255)


def test_grid_view_is_upscaled_and_keeps_drawing_visible():
    canvas = Canvas()
    canvas.draw.rectangle((100, 100, 150, 150), fill=(255, 0, 0))
    img = Image.open(io.BytesIO(canvas.to_grid_png_bytes())).convert("RGB")
    big = config.CANVAS_SIZE * config.MODEL_VIEW_SCALE
    assert img.width > big and img.height > big  # upscaled plus label margins
    margin = (img.width - big) // 2
    # Canvas pixel (125, 125) lands at margin + 125*scale (+1 to avoid a grid line).
    p = margin + 125 * config.MODEL_VIEW_SCALE + 1
    r, g, b = img.getpixel((p, p))
    assert r > 200 and g < 60 and b < 60


def test_save_writes_png_and_creates_folders(tmp_path):
    canvas = Canvas()
    out = canvas.save(tmp_path / "nested" / "round_001.png")
    assert out.exists()
    assert Image.open(out).size == (200, 200)


def test_shared_canvas_reset():
    shared = get_canvas()
    shared.draw.rectangle((0, 0, 10, 10), fill=(1, 2, 3))
    assert reset_canvas() is shared
    assert shared.pixel(5, 5) == (255, 255, 255)
