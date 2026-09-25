"""Renders visual previews of what visage's generators actually output —
the images/GIFs used in the README's "See it in action" section, and handy
for eyeballing your own art after swapping it in.

No LiveKit room needed — drives the real generator classes directly with
synthetic audio, same technique as scripts/smoke_test.py.

Writes into docs/ (override with --out):
  - demo-shapes.png     every mouth shape + blink, laid out on one sheet
  - demo-amplitude.gif  ImageAvatarVideoGenerator "talking" to synthetic
                         loud/quiet audio (blinks included)
  - demo-viseme.gif     the 9 viseme shapes cycled the way Rhubarb mode
                         drives them from a real cue timeline

Run: python scripts/render_preview.py [--assets DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import numpy as np
from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd
from PIL import Image, ImageDraw

from visage import AvatarAssets, ImageAvatarVideoGenerator, MouthState, Viseme, default_assets_dir
from visage.blink import BlinkDriver

SR = 24000
BG = (28, 32, 40)  # matches docs/social-preview.png for a consistent look


def to_image(frame: rtc.VideoFrame) -> Image.Image:
    return Image.frombytes("RGB", (frame.width, frame.height), bytes(frame.data))


def synthetic_frame(seconds: float, loud: bool) -> rtc.AudioFrame:
    n = int(SR * seconds)
    if loud:
        t = np.linspace(0, seconds, n, endpoint=False)
        samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    return rtc.AudioFrame(data=samples.tobytes(), sample_rate=SR, num_channels=1, samples_per_channel=n)


def render_contact_sheet(assets: AvatarAssets, out_dir: Path) -> None:
    states = [MouthState.CLOSED, MouthState.OPEN, *Viseme]
    labels = [f"mouth: {s.value}" for s in states] + ["blink"]
    frames = [to_image(assets.video_frame(s)) for s in states] + [
        to_image(assets.video_frame(MouthState.CLOSED, blinking=True))
    ]
    thumb, cols = 200, 4
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb, rows * (thumb + 24)), BG)
    d = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(zip(frames, labels)):
        x, y = (i % cols) * thumb, (i // cols) * (thumb + 24)
        sheet.paste(img.resize((thumb, thumb)), (x, y))
        d.text((x + 6, y + thumb + 4), label, fill=(230, 230, 230))
    sheet.save(out_dir / "demo-shapes.png")


async def render_amplitude_gif(assets: AvatarAssets, out_dir: Path) -> None:
    gen = ImageAvatarVideoGenerator(assets, audio_sample_rate=SR, video_fps=25.0)
    gen._blink = BlinkDriver(min_interval=0.6, max_interval=1.0, blink_duration=0.16)  # blink often for a short clip
    try:
        for _ in range(3):
            await gen.push_audio(synthetic_frame(0.16, True))
            await gen.push_audio(synthetic_frame(0.08, False))
            await gen.push_audio(synthetic_frame(0.12, True))
            await gen.push_audio(synthetic_frame(0.20, False))
        await gen.push_audio(AudioSegmentEnd())

        frames = []
        async for item in gen:
            if isinstance(item, AudioSegmentEnd):
                break
            if isinstance(item, rtc.VideoFrame):
                frames.append(to_image(item).resize((256, 256)))
    finally:
        await gen.aclose()

    frames[0].save(out_dir / "demo-amplitude.gif", save_all=True, append_images=frames[1:], duration=40, loop=0)
    print(f"demo-amplitude.gif: {len(frames)} frames ({len(frames) / 25:.2f}s)")


def render_viseme_gif(assets: AvatarAssets, out_dir: Path) -> None:
    seq = [Viseme.X, Viseme.D, Viseme.B, Viseme.C, Viseme.A, Viseme.E, Viseme.F, Viseme.G, Viseme.H, Viseme.C, Viseme.B, Viseme.X]
    frames = []
    for v in seq:
        img = to_image(assets.video_frame(v)).resize((256, 256))
        ImageDraw.Draw(img).text((8, 8), f"viseme {v.value.upper()}", fill=(240, 240, 240))
        frames.extend([img] * 5)  # 200ms per shape @ 25fps
    frames[0].save(out_dir / "demo-viseme.gif", save_all=True, append_images=frames[1:], duration=40, loop=0)
    print(f"demo-viseme.gif: {len(frames)} frames")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", type=Path, default=None, help="asset folder (default: packaged default art)")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "docs")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    assets = AvatarAssets.load(
        args.assets or default_assets_dir(), states=(*MouthState, *Viseme), background=BG
    )

    render_contact_sheet(assets, args.out)
    await render_amplitude_gif(assets, args.out)
    render_viseme_gif(assets, args.out)
    print(f"written to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
