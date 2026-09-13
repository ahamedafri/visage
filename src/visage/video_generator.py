"""v1 (Phase 1) VideoGenerator: amplitude-only open/closed mouth.

Implements the real ``livekit.agents.voice.avatar.VideoGenerator`` ABC
(verified against livekit-agents==1.8.1 — see
``livekit/agents/voice/avatar/_types.py`` and the reference implementation
in ``livekit-plugins-bithuman``'s ``BithumanGenerator``).

Design: ``push_audio`` is called sequentially and awaited by
``AvatarRunner._read_audio``, so it can safely do the chunking work inline
rather than needing a separate producer task — it slices incoming PCM into
fixed-size windows matching one video frame's duration, picks a mouth shape
per window from that window's RMS amplitude, and enqueues a
(video frame, audio frame) pair per window onto an internal queue that
``__aiter__`` drains.

This gets audio and video roughly frame-accurate to each other (they're
derived from the same PCM window) — LiveKit's ``AVSynchronizer`` (used
inside ``AvatarRunner``) handles the actual realtime pacing once frames are
pushed. See the project README for the known limits of amplitude-only sync
vs. real viseme timing (Phase 2, ``RhubarbVisemeVideoGenerator``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd, VideoGenerator

from ._pcm_windowing import bytes_per_window, make_audio_frame, pad_to_window, rms_amplitude
from .assets import AvatarAssets, MouthState
from .blink import BlinkDriver

logger = logging.getLogger("visage")


class ImageAvatarVideoGenerator(VideoGenerator):
    def __init__(
        self,
        assets: AvatarAssets,
        *,
        video_fps: float = 25.0,
        audio_sample_rate: int = 24000,
        audio_channels: int = 1,
        open_threshold: float = 500.0,
        enable_blink: bool = True,
    ) -> None:
        """
        Args:
            assets: pre-loaded face + mouth-shape images (see ``AvatarAssets.load``).
            video_fps: output video frame rate.
            audio_sample_rate: MUST match the sample rate of the audio frames
                that will actually be pushed (i.e. your agent's TTS output
                rate). There is no resampling in v1 — a mismatch will not
                raise here, but will play back at the wrong pitch/speed.
                Verify this against your `AgentSession` TTS config.
            audio_channels: channel count of pushed audio frames.
            open_threshold: RMS amplitude (on int16 PCM, 0-32768 range) above
                which the mouth is considered "open". Tune per-voice — TTS
                loudness varies a lot by provider/voice.
            enable_blink: periodically blink if `assets` has `face_blink.png`
                loaded (no-op otherwise). Note blinking only happens while
                audio is actively flowing — see README "Known limitations".
        """
        self._assets = assets
        self._video_fps = video_fps
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels
        self._open_threshold = open_threshold
        self._blink = BlinkDriver() if enable_blink else None

        self._bytes_per_window = bytes_per_window(audio_sample_rate, video_fps, audio_channels)

        self._pcm_buffer = bytearray()
        self._out_queue: asyncio.Queue[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd] = (
            asyncio.Queue()
        )

    @property
    def video_resolution(self) -> tuple[int, int]:
        return self._assets.resolution

    @property
    def video_fps(self) -> float:
        return self._video_fps

    @property
    def audio_sample_rate(self) -> int:
        return self._audio_sample_rate

    async def push_audio(self, frame: rtc.AudioFrame | AudioSegmentEnd) -> None:
        if isinstance(frame, AudioSegmentEnd):
            if self._pcm_buffer:
                # flush a final, silence-padded partial window rather than
                # dropping the tail of the last word
                padded = pad_to_window(bytes(self._pcm_buffer), self._bytes_per_window)
                self._pcm_buffer.clear()
                await self._emit_window(padded, self._audio_channels)
            await self._out_queue.put(AudioSegmentEnd())
            return

        if frame.sample_rate != self._audio_sample_rate:
            logger.warning(
                "pushed audio sample_rate=%d does not match configured "
                "audio_sample_rate=%d — set audio_sample_rate to match your "
                "TTS output, no resampling is done in v1",
                frame.sample_rate,
                self._audio_sample_rate,
            )

        self._pcm_buffer.extend(bytes(frame.data))
        while len(self._pcm_buffer) >= self._bytes_per_window:
            window = bytes(self._pcm_buffer[: self._bytes_per_window])
            del self._pcm_buffer[: self._bytes_per_window]
            await self._emit_window(window, frame.num_channels)

    async def _emit_window(self, pcm_bytes: bytes, num_channels: int) -> None:
        state = MouthState.OPEN if rms_amplitude(pcm_bytes) > self._open_threshold else MouthState.CLOSED
        blinking = self._blink.advance(1.0 / self._video_fps) if self._blink is not None else False

        video_frame = self._assets.video_frame(state, blinking=blinking)
        audio_frame = make_audio_frame(
            pcm_bytes, sample_rate=self._audio_sample_rate, num_channels=num_channels
        )
        await self._out_queue.put(video_frame)
        await self._out_queue.put(audio_frame)

    def clear_buffer(self) -> None:
        """Drop everything buffered — called on barge-in/interruption."""
        self._pcm_buffer.clear()
        while True:
            try:
                self._out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def __aiter__(self) -> AsyncIterator[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd]:
        while True:
            yield await self._out_queue.get()
