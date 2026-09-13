"""Raw PCM -> WAV file, using stdlib ``wave`` (no extra dependency).

Rhubarb Lip Sync is a batch CLI tool that needs a real WAV file; LiveKit's
``rtc.AudioFrame`` only carries raw int16 PCM bytes, with no container.
"""

from __future__ import annotations

import wave
from pathlib import Path

from ._pcm_windowing import SAMPLE_WIDTH_BYTES


def write_wav(
    path: str | Path,
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int = SAMPLE_WIDTH_BYTES,
) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
