import asyncio

import numpy as np
from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd

from visage import AvatarAssets, ImageAvatarVideoGenerator, default_assets_dir
from visage._audio_normalize import AudioNormalizer


def _frame(seconds: float, rate: int, channels: int = 1) -> rtc.AudioFrame:
    n = int(rate * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    mono = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    samples = np.repeat(mono, channels) if channels > 1 else mono
    return rtc.AudioFrame(
        data=samples.tobytes(), sample_rate=rate, num_channels=channels, samples_per_channel=n
    )


def test_passthrough_when_rate_and_channels_match():
    norm = AudioNormalizer(sample_rate=24000, channels=1)
    frame = _frame(0.1, 24000)
    assert norm.push(frame) == bytes(frame.data)
    assert norm.flush() == b""


def test_resamples_to_configured_rate():
    norm = AudioNormalizer(sample_rate=24000, channels=1)
    out = norm.push(_frame(0.5, 16000)) + norm.flush()
    samples = len(out) // 2
    # 0.5s at 24kHz = 12000 samples; SoX may be off by a handful at the edges
    assert abs(samples - 12000) < 50


def test_downmixes_stereo_to_mono():
    norm = AudioNormalizer(sample_rate=24000, channels=1)
    stereo = _frame(0.1, 24000, channels=2)
    out = norm.push(stereo)
    assert len(out) == len(bytes(stereo.data)) // 2
    # both channels were identical, so the average equals the original mono
    mono = np.frombuffer(out, dtype=np.int16)
    src_left = np.frombuffer(bytes(stereo.data), dtype=np.int16)[::2]
    assert np.array_equal(mono, src_left)


def test_upmixes_mono_to_stereo():
    norm = AudioNormalizer(sample_rate=24000, channels=2)
    mono = _frame(0.1, 24000)
    out = norm.push(mono)
    assert len(out) == len(bytes(mono.data)) * 2


def test_unsupported_channel_conversion_raises():
    norm = AudioNormalizer(sample_rate=24000, channels=1)
    n = 100
    frame = rtc.AudioFrame(
        data=bytes(n * 6 * 2), sample_rate=24000, num_channels=6, samples_per_channel=n
    )
    try:
        norm.push(frame)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "6 channel" in str(e)


def test_reset_drops_buffered_resampler_state():
    norm = AudioNormalizer(sample_rate=24000, channels=1)
    norm.push(_frame(0.01, 16000))  # tiny push; some samples stay buffered
    norm.reset()
    assert norm.flush() == b""


def test_generator_emits_configured_rate_when_fed_a_different_rate():
    """End-to-end: 16kHz frames into a 24kHz-configured generator must come
    out as 24kHz audio frames of the right total duration — the bug this
    fixes was them coming out at 24kHz but containing 16kHz samples
    (i.e. playing back 1.5x too fast / pitched up)."""

    async def run() -> tuple[int, float]:
        assets = AvatarAssets.load(default_assets_dir())
        gen = ImageAvatarVideoGenerator(
            assets, audio_sample_rate=24000, audio_channels=1, enable_blink=False
        )
        try:
            await gen.push_audio(_frame(1.0, 16000))
            await gen.push_audio(AudioSegmentEnd())

            total_samples = 0
            rates = set()
            async for item in gen:
                if isinstance(item, AudioSegmentEnd):
                    break
                if isinstance(item, rtc.AudioFrame):
                    rates.add(item.sample_rate)
                    total_samples += item.samples_per_channel
            assert rates == {24000}
            return total_samples, total_samples / 24000
        finally:
            await gen.aclose()

    total_samples, seconds = asyncio.run(run())
    # 1.0s in -> ~1.0s out (padded up to a whole video-frame window at most)
    assert 0.98 <= seconds <= 1.05, f"got {seconds:.3f}s ({total_samples} samples)"
