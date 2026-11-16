"""Combines a run's round_NNN.png images into one labelled overview image.

Usage:  python scripts/make_contact_sheet.py output/run_20261116_120000 [--columns 6]
Writes <run folder>/progression.png
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GAP = 10
LABEL_H = 22


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError):
        return ImageFont.load_default()


def _scores(log: Path) -> dict[int, str]:
    """Reads the Critic's score for each round from conversation_log.md."""
    if not log.exists():
        return {}
    scores, current = {}, None
    for line in log.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"## Round (\d+)", line):
            current = int(m.group(1))
        elif current and current not in scores and (m := re.search(r"Score:\**\s*(\d+)\s*/\s*10", line)):
            scores[current] = m.group(1)
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--columns", type=int, default=6)
    args = parser.parse_args()

    images = sorted(args.run_dir.glob("round_*.png"))
    if not images:
        print(f"No round_*.png files in {args.run_dir}")
        return 1
    scores = _scores(args.run_dir / "conversation_log.md")

    w, h = Image.open(images[0]).size
    cols = min(args.columns, len(images))
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + GAP) + GAP, rows * (h + LABEL_H + GAP) + GAP), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    font = _font(14)
    for i, path in enumerate(images):
        x = GAP + (i % cols) * (w + GAP)
        y = GAP + (i // cols) * (h + LABEL_H + GAP)
        round_no = int(path.stem.split("_")[1])
        label = f"Round {round_no}" + (f"  -  {scores[round_no]}/10" if round_no in scores else "")
        draw.text((x + 2, y + 3), label, fill=(240, 240, 240), font=font)
        with Image.open(path) as img:
            sheet.paste(img.convert("RGB"), (x, y + LABEL_H))

    out = args.run_dir / "progression.png"
    sheet.save(out)
    print(f"Wrote {out} ({len(images)} rounds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
