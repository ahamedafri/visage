import asyncio
import logging

import numpy as np
from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd

from visage import AvatarAssets, MouthState, RhubarbVisemeVideoGenerator, Viseme, default_assets_dir

ASSETS_DIR = default_assets_dir()
SAMPLE_RATE = 24000


def _synthetic_frame(seconds: float, loud: bool) -> rtc.AudioFrame:
    n = int(SAMPLE_RATE * seconds)
    if loud:
        t = np.linspace(0, seconds, n, endpoint=False)
        samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    return rtc.AudioFrame(
        data=samples.tobytes(), sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=n
    )


def test_falls_back_to_amplitude_when_rhubarb_missing(caplog):
    """No real rhubarb binary needed — points rhubarb_path at a path that
    can't possibly exist, and (assuming this machine has no `rhubarb` on
    PATH/RHUBARB_PATH, true for CI and most contributors) confirms the
    generator degrades to amplitude-only rather than dropping audio."""

    async def run() -> tuple[bool, list[MouthState]]:
        assets = AvatarAssets.load(ASSETS_DIR, states=(*MouthState, *Viseme))
        gen = RhubarbVisemeVideoGenerator(
            assets,
            video_fps=25.0,
            audio_sample_rate=SAMPLE_RATE,
            audio_channels=1,
            rhubarb_path="/definitely/not/a/real/path/to/rhubarb",
        )
        await gen.push_audio(_synthetic_frame(0.2, loud=True))
        await gen.push_audio(AudioSegmentEnd())

        states_seen: list[MouthState] = []
        saw_end = False
        async for item in gen:
            if isinstance(item, AudioSegmentEnd):
                saw_end = True
                break
            if isinstance(item, rtc.VideoFrame):
                for state in (MouthState.CLOSED, MouthState.OPEN):
                    if bytes(item.data) == bytes(assets.video_frame(state).data):
                        states_seen.append(state)
                        break
        return saw_end, states_seen

    with caplog.at_level(logging.WARNING, logger="visage"):
        saw_end, states_seen = asyncio.run(run())

    assert saw_end, "AudioSegmentEnd never reached the generator output"
    assert states_seen, "no MouthState frames were emitted — fallback path didn't run"
    assert all(isinstance(s, MouthState) for s in states_seen)
    assert "falling back to amplitude-only" in caplog.text
    assert caplog.text.count("falling back to amplitude-only") == 1  # warned exactly once
