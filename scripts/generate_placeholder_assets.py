"""Generates placeholder art for the default asset set.

Flat, emoji-style shapes drawn with Pillow — no artist needed for v1. Run:

    python scripts/generate_placeholder_assets.py

Writes into assets/default/: face.png, mouth_closed.png, mouth_open.png.
Swap these for real art later; anything with the same canvas size and the
same file names works as a drop-in replacement (see README "Custom art").
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = (512, 512)
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "default"

FACE_COLOR = (247, 202, 24, 255)  # warm yellow, emoji-ish
OUTLINE = (40, 40, 40, 255)
EYE_COLOR = (40, 40, 40, 255)
MOUTH_COLOR = (120, 40, 40, 255)
TEETH_COLOR = (255, 255, 255, 255)


def make_face() -> Image.Image:
    img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy, r = SIZE[0] // 2, SIZE[1] // 2, 200
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FACE_COLOR, outline=OUTLINE, width=6)

    eye_r = 18
    for ex in (cx - 75, cx + 75):
        ey = cy - 40
        draw.ellipse((ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r), fill=EYE_COLOR)

    return img


def make_mouth_closed() -> Image.Image:
    img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE[0] // 2, SIZE[1] // 2
    draw.rounded_rectangle(
        (cx - 55, cy + 80, cx + 55, cy + 100), radius=10, fill=MOUTH_COLOR
    )
    return img


def make_mouth_open() -> Image.Image:
    img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE[0] // 2, SIZE[1] // 2
    draw.ellipse((cx - 55, cy + 60, cx + 55, cy + 140), fill=MOUTH_COLOR)
    draw.rectangle((cx - 40, cy + 65, cx + 40, cy + 85), fill=TEETH_COLOR)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_face().save(OUT_DIR / "face.png")
    make_mouth_closed().save(OUT_DIR / "mouth_closed.png")
    make_mouth_open().save(OUT_DIR / "mouth_open.png")
    print(f"wrote placeholder assets to {OUT_DIR}")


if __name__ == "__main__":
    main()
