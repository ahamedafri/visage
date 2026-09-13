"""Pure PCM-window helpers shared by both video generators.

No asyncio, no I/O — kept trivially unit-testable and reusable between
``ImageAvatarVideoGenerator`` (amplitude-only) and
``RhubarbVisemeVideoGenerator`` (real viseme timing), which both slice raw
int16 PCM into fixed-size windows matching one video frame's duration.
"""

from __future__ import annotations

import numpy as np
from livekit import rtc

SAMPLE_WIDTH_BYTES = 2  # int16 PCM, matching rtc.AudioFrame's data layout


def bytes_per_window(
    sample_rate: int, video_fps: float, channels: int, sample_width: int = SAMPLE_WIDTH_BYTES
) -> int:
    """Byte size of one video frame's worth of audio."""
    samples = max(1, round(sample_rate / video_fps))
    return samples * channels * sample_width


def pad_to_window(window: bytes, window_bytes: int) -> bytes:
    """Zero-pad a short tail window (silence) rather than dropping it."""
    if len(window) >= window_bytes:
        return window
    return window + b"\x00" * (window_bytes - len(window))


def make_audio_frame(
    pcm_bytes: bytes, *, sample_rate: int, num_channels: int
) -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=pcm_bytes,
        sample_rate=sample_rate,
        num_channels=num_channels,
        samples_per_channel=len(pcm_bytes) // SAMPLE_WIDTH_BYTES // num_channels,
    )


def rms_amplitude(pcm_bytes: bytes) -> float:
    """RMS of int16 PCM. 0.0 for empty input."""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
