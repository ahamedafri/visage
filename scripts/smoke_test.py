"""No-LiveKit-room smoke test for the compositing + chunking pipeline.

Validates the actual hard-ish part locally in a few seconds: loads the
default assets, runs a synthetic audio signal (alternating loud/quiet
bursts) through ImageAvatarVideoGenerator exactly as AvatarRunner would
call it, and:
  1. asserts the mouth actually toggles CLOSED/OPEN in step with the
     synthetic loud/quiet bursts
  2. saves one CLOSED and one OPEN composited frame as PNGs so you can look
     at the actual output, not just trust the assertion

Run: python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd

from visage import AvatarAssets, ImageAvatarVideoGenerator
from visage.assets import MouthState

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "default"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "_smoke_test_output"

SAMPLE_RATE = 24000
CHANNELS = 1


def synthetic_audio_frame(seconds: float, loud: bool) -> rtc.AudioFrame:
    n = int(SAMPLE_RATE * seconds)
    if loud:
        t = np.linspace(0, seconds, n, endpoint=False)
        samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    return rtc.AudioFrame(
        data=samples.tobytes(),
        sample_rate=SAMPLE_RATE,
        num_channels=CHANNELS,
        samples_per_channel=n,
    )


async def main() -> None:
    assets = AvatarAssets.load(ASSETS_DIR)
    gen = ImageAvatarVideoGenerator(
        assets, video_fps=25.0, audio_sample_rate=SAMPLE_RATE, audio_channels=CHANNELS
    )

    async def feed() -> None:
        await gen.push_audio(synthetic_audio_frame(0.4, loud=True))
        await gen.push_audio(synthetic_audio_frame(0.4, loud=False))
        await gen.push_audio(synthetic_audio_frame(0.4, loud=True))
        await gen.push_audio(AudioSegmentEnd())

    feed_task = asyncio.create_task(feed())

    states_seen: list[MouthState] = []
    video_frames_by_state: dict[MouthState, rtc.VideoFrame] = {}
    saw_segment_end = False

    async for item in gen:
        if isinstance(item, AudioSegmentEnd):
            saw_segment_end = True
            break
        if isinstance(item, rtc.VideoFrame):
            # infer which state this frame is by comparing bytes to the
            # known reference frames (cheap since these are tiny test images)
            for state in (MouthState.CLOSED, MouthState.OPEN):
                if bytes(item.data) == bytes(assets.video_frame(state).data):
                    states_seen.append(state)
                    video_frames_by_state.setdefault(state, item)
                    break

    await feed_task

    assert saw_segment_end, "AudioSegmentEnd never reached the generator output"
    assert MouthState.OPEN in states_seen, "mouth never opened for the loud segments"
    assert MouthState.CLOSED in states_seen, "mouth never closed for the quiet segment"
    # loud -> quiet -> loud should show up as OPEN ... CLOSED ... OPEN in order
    assert states_seen[0] == MouthState.OPEN
    assert MouthState.CLOSED in states_seen[len(states_seen) // 3 : -1]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for state, frame in video_frames_by_state.items():
        img_bytes = bytes(frame.data)
        from PIL import Image

        Image.frombytes("RGB", (frame.width, frame.height), img_bytes).save(
            OUT_DIR / f"mouth_{state.value}_composited.png"
        )

    print(f"OK — {len(states_seen)} video frames generated, states: "
          f"{[s.value for s in states_seen]}")
    print(f"composited frames written to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
