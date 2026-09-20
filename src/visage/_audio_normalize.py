"""Normalize incoming TTS audio to the generator's configured rate/channels.

Before this existed, `audio_sample_rate` had to match the TTS provider's
output exactly or audio silently played back at the wrong pitch/speed (the
generators only logged a warning). Now any mismatch is corrected:

  - sample rate: via LiveKit's own ``rtc.AudioResampler`` (SoX-backed,
    native). It's stateful/streaming, so we keep one instance per observed
    input rate and ``flush()`` it at the end of each utterance so the last
    few samples aren't left inside its buffer.
  - channel count: mono <-> stereo via numpy (average pairs to downmix,
    duplicate to upmix). Anything else is unsupported and raises.

Pure-ish: no asyncio, no queues — takes an ``rtc.AudioFrame``, returns
normalized int16 PCM bytes. Shared by both video generators.
"""

from __future__ import annotations

import logging

import numpy as np
from livekit import rtc

logger = logging.getLogger("visage")


class AudioNormalizer:
    def __init__(self, *, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._resampler: rtc.AudioResampler | None = None
        self._resampler_input_rate: int | None = None
        self._warned_rates: set[int] = set()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    def push(self, frame: rtc.AudioFrame) -> bytes:
        """Normalize one frame. May return fewer bytes than pushed (or none)
        while the resampler is buffering — call ``flush()`` at utterance end."""
        pcm = self._normalize_channels(bytes(frame.data), frame.num_channels)

        if frame.sample_rate == self._sample_rate:
            return pcm

        if frame.sample_rate not in self._warned_rates:
            self._warned_rates.add(frame.sample_rate)
            logger.info(
                "resampling pushed audio from %d Hz to configured %d Hz",
                frame.sample_rate,
                self._sample_rate,
            )

        if self._resampler is None or self._resampler_input_rate != frame.sample_rate:
            # input rate changed mid-stream (unusual) — drain the old one
            # rather than feeding it wrong-rate data
            leftover = self._flush_resampler()
            self._resampler = rtc.AudioResampler(
                frame.sample_rate, self._sample_rate, num_channels=self._channels
            )
            self._resampler_input_rate = frame.sample_rate
            return leftover + self._drain(self._resampler.push(bytearray(pcm)))

        return self._drain(self._resampler.push(bytearray(pcm)))

    def flush(self) -> bytes:
        """Drain any samples still buffered in the resampler. Call at the end
        of each utterance (``AudioSegmentEnd``)."""
        return self._flush_resampler()

    def reset(self) -> None:
        """Drop resampler state without emitting — for interruption/barge-in."""
        self._resampler = None
        self._resampler_input_rate = None

    def _flush_resampler(self) -> bytes:
        if self._resampler is None:
            return b""
        out = self._drain(self._resampler.flush())
        # SoX resampler is a one-shot stream once flushed; recreate lazily
        self._resampler = None
        self._resampler_input_rate = None
        return out

    @staticmethod
    def _drain(frames: list[rtc.AudioFrame]) -> bytes:
        return b"".join(bytes(f.data) for f in frames)

    def _normalize_channels(self, pcm: bytes, src_channels: int) -> bytes:
        if src_channels == self._channels:
            return pcm
        samples = np.frombuffer(pcm, dtype=np.int16)
        if src_channels == 2 and self._channels == 1:
            stereo = samples.reshape(-1, 2).astype(np.int32)
            return ((stereo[:, 0] + stereo[:, 1]) // 2).astype(np.int16).tobytes()
        if src_channels == 1 and self._channels == 2:
            return np.repeat(samples, 2).tobytes()
        raise ValueError(
            f"unsupported channel conversion: pushed audio has {src_channels} "
            f"channel(s), generator configured for {self._channels}"
        )
