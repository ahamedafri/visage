import asyncio

import numpy as np
from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd

from visage import (
    AvatarAssets,
    ImageAvatarVideoGenerator,
    MouthState,
    RhubarbVisemeVideoGenerator,
    Viseme,
    default_assets_dir,
)

ASSETS_DIR = default_assets_dir()
SAMPLE_RATE = 24000


def _frame(seconds: float, loud: bool) -> rtc.AudioFrame:
    n = int(SAMPLE_RATE * seconds)
    if loud:
        t = np.linspace(0, seconds, n, endpoint=False)
        samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    return rtc.AudioFrame(
        data=samples.tobytes(), sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=n
    )


def test_image_generator_idle_event_toggles_with_speech_lifecycle():
    async def run() -> None:
        assets = AvatarAssets.load(ASSETS_DIR)
        gen = ImageAvatarVideoGenerator(assets, audio_sample_rate=SAMPLE_RATE, idle_fps=50.0)
        try:
            assert gen._idle_event.is_set(), "should start idle"

            await gen.push_audio(_frame(0.05, loud=True))
            assert not gen._idle_event.is_set(), "should pause idle heartbeat while speech is flowing"

            await gen.push_audio(AudioSegmentEnd())
            assert gen._idle_event.is_set(), "should resume idle heartbeat once utterance is fully emitted"

            # interruption mid-speech should also resume idle immediately
            await gen.push_audio(_frame(0.05, loud=True))
            assert not gen._idle_event.is_set()
            gen.clear_buffer()
            assert gen._idle_event.is_set(), "clear_buffer (barge-in) should resume idle heartbeat"
        finally:
            await gen.aclose()

    asyncio.run(run())


def test_image_generator_idle_loop_actually_produces_frames():
    async def run() -> None:
        assets = AvatarAssets.load(ASSETS_DIR)
        gen = ImageAvatarVideoGenerator(assets, audio_sample_rate=SAMPLE_RATE, idle_fps=50.0)
        try:
            stream = gen.__aiter__()
            # never called push_audio — any frame that arrives must come
            # from the idle heartbeat, not the speech path
            frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert isinstance(frame, rtc.VideoFrame)
            assert bytes(frame.data) == bytes(assets.video_frame(MouthState.CLOSED).data)
        finally:
            await gen.aclose()

    asyncio.run(run())


def test_rhubarb_generator_idle_event_toggles_with_speech_lifecycle():
    async def run() -> None:
        assets = AvatarAssets.load(ASSETS_DIR, states=(*MouthState, *Viseme))
        gen = RhubarbVisemeVideoGenerator(
            assets, audio_sample_rate=SAMPLE_RATE, idle_fps=50.0, rhubarb_path="/nope"
        )
        try:
            assert gen._idle_event.is_set()

            await gen.push_audio(_frame(0.05, loud=True))
            assert not gen._idle_event.is_set()

            await gen.push_audio(AudioSegmentEnd())
            # worker runs asynchronously — wait for it to actually finish
            # replaying and resume the idle heartbeat
            for _ in range(100):
                if gen._idle_event.is_set():
                    break
                await asyncio.sleep(0.01)
            assert gen._idle_event.is_set(), "should resume idle heartbeat once utterance is fully replayed"
        finally:
            await gen.aclose()

    asyncio.run(run())


def test_rhubarb_generator_idle_loop_produces_viseme_x_frames():
    async def run() -> None:
        assets = AvatarAssets.load(ASSETS_DIR, states=(*MouthState, *Viseme))
        gen = RhubarbVisemeVideoGenerator(
            assets, audio_sample_rate=SAMPLE_RATE, idle_fps=50.0, rhubarb_path="/nope"
        )
        try:
            stream = gen.__aiter__()
            frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert isinstance(frame, rtc.VideoFrame)
            assert bytes(frame.data) == bytes(assets.video_frame(Viseme.X).data)
        finally:
            await gen.aclose()

    asyncio.run(run())


def test_idle_heartbeat_disabled_without_blink_art(tmp_path):
    from PIL import Image

    Image.new("RGBA", (16, 16), (255, 255, 0, 255)).save(tmp_path / "face.png")
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(tmp_path / "mouth_closed.png")
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(tmp_path / "mouth_open.png")

    async def run() -> None:
        assets = AvatarAssets.load(tmp_path)
        assert not assets.has_blink_art
        gen = ImageAvatarVideoGenerator(assets, audio_sample_rate=SAMPLE_RATE, idle_fps=50.0)
        try:
            assert gen._idle_task is None, "no blink art -> no idle heartbeat task at all"
        finally:
            await gen.aclose()

    asyncio.run(run())
