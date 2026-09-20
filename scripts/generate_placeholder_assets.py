"""Generates placeholder art for the default asset set.

Flat, emoji-style shapes drawn with Pillow — no artist needed. Run:

    python scripts/generate_placeholder_assets.py

Writes into src/visage/default_assets/ — the packaged default asset set
(shipped with `pip install visage` via package-data, see pyproject.toml):
  - face.png, mouth_closed.png, mouth_open.png       (v1, MouthState)
  - mouth_x.png .. mouth_f.png                        (Phase 2a, Viseme)
  - face_blink.png                                    (Phase 2b, blinking)

This is only for regenerating/tweaking the *placeholder* art during
development. To use your own art in a project depending on visage, load a
separate folder with `AvatarAssets.load("path/to/your/folder")` instead —
anything with the same canvas size and the same file names works as a
drop-in replacement (see README "Custom art").
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from visage.assets import Viseme
from visage.paths import default_assets_dir

SIZE = (512, 512)
OUT_DIR = default_assets_dir()

FACE_COLOR = (247, 202, 24, 255)  # warm yellow, emoji-ish
OUTLINE = (40, 40, 40, 255)
EYE_COLOR = (40, 40, 40, 255)
MOUTH_COLOR = (120, 40, 40, 255)
TEETH_COLOR = (255, 255, 255, 255)


def make_face(*, blink: bool = False) -> Image.Image:
    img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy, r = SIZE[0] // 2, SIZE[1] // 2, 200
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FACE_COLOR, outline=OUTLINE, width=6)

    eye_r = 18
    ey = cy - 40
    for ex in (cx - 75, cx + 75):
        if blink:
            # closed eye: a thin horizontal line instead of a filled circle
            draw.line((ex - eye_r, ey, ex + eye_r, ey), fill=EYE_COLOR, width=6)
        else:
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


TONGUE_COLOR = (220, 110, 120, 255)

# (half_width, top_offset, bottom_offset, teeth, tongue) per viseme, offsets
# relative to face center — bigger spread = more open. Loosely: X/A closed,
# B/G barely parted, C/E/H medium, D widest, F puckered round.
#   teeth:  "none" | "top" (upper teeth row) | "bite" (upper teeth resting
#           on the lower lip — the F/V shape)
#   tongue: draw a raised tongue inside the mouth (the L shape)
_VISEME_SHAPE_PARAMS: dict[Viseme, tuple[int, int, int, str, bool]] = {
    Viseme.X: (55, 80, 100, "none", False),  # idle/rest — same as closed
    Viseme.A: (55, 80, 100, "none", False),  # closed lips (P/B/M) — same as closed
    Viseme.B: (50, 78, 108, "top", False),  # slightly parted, teeth (consonants/"EE")
    Viseme.C: (52, 68, 122, "top", False),  # medium open ("EH"/"AE")
    Viseme.D: (58, 55, 145, "top", False),  # widest open ("AA")
    Viseme.E: (60, 65, 128, "none", False),  # medium open, rounder/wider ("AO"/"ER")
    Viseme.F: (28, 75, 115, "none", False),  # small puckered "O" (UW/OW/W)
    Viseme.G: (52, 82, 104, "bite", False),  # upper teeth on lower lip (F/V)
    Viseme.H: (52, 66, 124, "top", True),  # tongue raised behind teeth (L)
}


def make_mouth_viseme(shape: Viseme) -> Image.Image:
    half_width, top_offset, bottom_offset, teeth, tongue = _VISEME_SHAPE_PARAMS[shape]
    img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE[0] // 2, SIZE[1] // 2

    top, bottom = cy + top_offset, cy + bottom_offset
    draw.ellipse((cx - half_width, top, cx + half_width, bottom), fill=MOUTH_COLOR)

    if tongue:
        # a raised tongue: pink ellipse filling the lower-middle of the mouth
        draw.ellipse(
            (cx - half_width + 14, top + (bottom - top) // 2, cx + half_width - 14, bottom - 6),
            fill=TONGUE_COLOR,
        )

    if teeth == "top":
        teeth_bottom = top + (bottom - top) // 3
        draw.rectangle((cx - half_width + 10, top + 5, cx + half_width - 10, teeth_bottom), fill=TEETH_COLOR)
    elif teeth == "bite":
        # upper teeth overhanging the lower lip: a teeth row that extends
        # slightly below the (thin) mouth opening
        draw.rectangle((cx - half_width + 8, top + 2, cx + half_width - 8, bottom + 4), fill=TEETH_COLOR)
        # thin lower-lip line under the teeth so it reads as "teeth on lip"
        draw.rounded_rectangle(
            (cx - half_width + 4, bottom + 2, cx + half_width - 4, bottom + 12), radius=6, fill=MOUTH_COLOR
        )
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_face().save(OUT_DIR / "face.png")
    make_face(blink=True).save(OUT_DIR / "face_blink.png")
    make_mouth_closed().save(OUT_DIR / "mouth_closed.png")
    make_mouth_open().save(OUT_DIR / "mouth_open.png")
    for viseme in Viseme:
        make_mouth_viseme(viseme).save(OUT_DIR / f"mouth_{viseme.value}.png")
    print(f"wrote placeholder assets to {OUT_DIR}")


if __name__ == "__main__":
    main()
