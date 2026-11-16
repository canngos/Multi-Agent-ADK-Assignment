"""The 200x200 digital canvas the Painter draws on.

One process runs one drawing session, so a single module-level canvas is shared
by the tools (which draw on it) and the callbacks (which show it to the models
and save it each round).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from . import config


def parse_color(color: str) -> tuple[int, int, int]:
    """Turns a color name ("red") or hex code ("#ff8800") into an RGB tuple.

    Raises ValueError with a readable message if the color is unknown.
    """
    if not isinstance(color, str) or not color.strip():
        raise ValueError("color must be a color name like 'red' or a hex code like '#ff8800'.")
    try:
        rgb = ImageColor.getrgb(color.strip().strip("\"'").strip())  # tolerate '"yellow"'
    except ValueError:
        raise ValueError(
            f"unknown color '{color}'. Use a color name like 'red' or a hex code like '#ff8800'."
        ) from None
    return rgb[:3]


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError):  # Pillow without FreeType support
        return ImageFont.load_default()


class Canvas:
    """A square RGB image plus records of the drawing commands applied to it.

    - `actions`: successful drawing actions in the current round (callbacks
      clear it at the start of each round).
    - `history`: every successful command since the last fill_background, as
      'tool_name {json args}' strings. The Painter sees this list
      so it can redraw the scene with corrections instead of patching pixels.
    """

    def __init__(self, size: int = config.CANVAS_SIZE, background: str = config.CANVAS_BACKGROUND):
        self.size = size
        self.actions: list[str] = []
        self.history: list[str] = []
        self.reset(background)

    def reset(self, background: str = config.CANVAS_BACKGROUND) -> None:
        """Clears the canvas to a single background color."""
        self.image = Image.new("RGB", (self.size, self.size), parse_color(background))
        self.draw = ImageDraw.Draw(self.image)
        self.actions.clear()
        self.history.clear()

    def record(self, action: str, command: str | None = None) -> None:
        """Remembers a successful drawing action and its command."""
        self.actions.append(action)
        if command:
            self.history.append(command)

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return self.image.getpixel((x, y))

    def to_png_bytes(self, scale: int = 1) -> bytes:
        """The plain canvas as PNG bytes, optionally upscaled (pixel-exact)."""
        img = self.image
        if scale > 1:
            img = img.resize((self.size * scale, self.size * scale), Image.Resampling.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def to_grid_png_bytes(
        self, scale: int = config.MODEL_VIEW_SCALE, step: int = config.GRID_STEP
    ) -> bytes:
        """The canvas upscaled, with a light coordinate grid and axis labels.

        This is the version shown to the models: the labels let them name and
        target coordinates instead of guessing.
        """
        margin = 34
        big = self.size * scale
        scaled = self.image.resize((big, big), Image.Resampling.NEAREST).convert("RGBA")

        overlay = Image.new("RGBA", scaled.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for v in range(0, self.size + 1, step):
            p = min(v * scale, big - 1)
            major = v % (step * 2) == 0
            colour = (0, 0, 0, 90) if major else (0, 0, 0, 45)
            od.line([(p, 0), (p, big)], fill=colour, width=1)
            od.line([(0, p), (big, p)], fill=colour, width=1)
        scaled = Image.alpha_composite(scaled, overlay).convert("RGB")

        view = Image.new("RGB", (big + 2 * margin, big + 2 * margin), (235, 235, 235))
        view.paste(scaled, (margin, margin))
        vd = ImageDraw.Draw(view)
        font = _load_font(14)
        for v in range(0, self.size + 1, step * 2):
            p = margin + min(v * scale, big - 1)
            label = str(v)
            w = vd.textlength(label, font=font)
            vd.text((p - w / 2, 8), label, fill=(0, 0, 0), font=font)  # top: x
            vd.text((p - w / 2, big + margin + 8), label, fill=(0, 0, 0), font=font)  # bottom: x
            vd.text((margin - w - 6, p - 8), label, fill=(0, 0, 0), font=font)  # left: y
            vd.text((big + margin + 6, p - 8), label, fill=(0, 0, 0), font=font)  # right: y
        vd.rectangle(
            (margin - 1, margin - 1, margin + big, margin + big), outline=(0, 0, 0), width=1
        )

        buf = io.BytesIO()
        view.save(buf, format="PNG")
        return buf.getvalue()

    def save(self, path: str | Path) -> Path:
        """Saves the plain canvas as a PNG file, creating folders if needed."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path, format="PNG")
        return path


_canvas = Canvas()


def get_canvas() -> Canvas:
    """The shared canvas for this run."""
    return _canvas


def reset_canvas(background: str = config.CANVAS_BACKGROUND) -> Canvas:
    """Clears the shared canvas (start of a run, and between tests)."""
    _canvas.reset(background)
    return _canvas
