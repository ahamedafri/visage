"""Renders the visage logo (docs/logo.svg) as PNGs, kept pixel-consistent
with the SVG by using the exact same coordinates. No new dependency
(Pillow only) — avoids needing an SVG rasterizer.

Writes into docs/:
  - logo.png              512x512, transparent background (README/badges)
  - favicon-32.png        32x32
  - social-preview.png    1280x640, opaque background (GitHub repo Settings
                           -> Social preview; there's no API for this one,
                           it has to be uploaded by hand)

Run: python scripts/generate_logo.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "docs"

FACE_COLOR = (247, 202, 24, 255)
OUTLINE = (40, 40, 40, 255)
EYE_COLOR = (40, 40, 40, 255)
MOUTH_COLOR = (120, 40, 40, 255)
SOCIAL_BG = (28, 32, 40, 255)  # matches the dark background used in demo renders
TEXT_COLOR = (240, 240, 240, 255)
SUBTEXT_COLOR = (170, 176, 186, 255)

# Segoe UI ships on Windows; social-preview.png is a one-time generated
# asset (committed to the repo), so this only needs to run once on a
# machine that has it — falls back to Pillow's default font elsewhere
# (uglier, but still generates something rather than crashing).
_FONT_CANDIDATES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
_FONT_LIGHT_CANDIDATES = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]


def _font(candidates: list[str], size: int) -> ImageFont.ImageFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# same coordinate space as docs/logo.svg's 240x240 viewBox
BARS = [(70, 155, 14, 10), (90, 145, 14, 20), (110, 133, 14, 32), (130, 145, 14, 20), (150, 155, 14, 10)]


def draw_face(size: int, supersample: int = 4) -> Image.Image:
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    scale = s / 240

    c = s // 2
    r = round(95 * scale)
    d.ellipse((c - r, c - r, c + r, c + r), fill=FACE_COLOR, outline=OUTLINE, width=round(8 * scale))

    eye_r = round(9 * scale)
    for ex in (95, 145):
        ex, ey = round(ex * scale), round(92 * scale)
        d.ellipse((ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r), fill=EYE_COLOR)

    for x, y, w, h in BARS:
        x, y, w, h = round(x * scale), round(y * scale), round(w * scale), round(h * scale)
        d.rounded_rectangle((x, y, x + w, y + h), radius=w // 2, fill=MOUTH_COLOR)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    draw_face(512).save(OUT_DIR / "logo.png")
    draw_face(32).save(OUT_DIR / "favicon-32.png")

    # social preview: opaque background, logo left, title + tagline right
    # (GitHub just displays this image as-is, no text overlay of its own)
    canvas = Image.new("RGB", (1280, 640), SOCIAL_BG[:3])
    face = draw_face(420)
    canvas.paste(face, (100, 110), face)

    d = ImageDraw.Draw(canvas)
    d.text((580, 230), "visage", font=_font(_FONT_CANDIDATES, 92), fill=TEXT_COLOR)
    d.text(
        (582, 340),
        "Free, self-hosted lip-synced avatars\nfor LiveKit voice agents",
        font=_font(_FONT_LIGHT_CANDIDATES, 34),
        fill=SUBTEXT_COLOR,
        spacing=14,
    )
    canvas.save(OUT_DIR / "social-preview.png")

    print(f"wrote logo.png, favicon-32.png, social-preview.png to {OUT_DIR}")


if __name__ == "__main__":
    main()
