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
pushed: it paces output to real wall-clock time via a bounded internal
queue regardless of how fast we push (verified by reading the installed
``livekit.rtc.synchronizer.AVSynchronizer``/``_FPSController``), which is
also what makes the idle heartbeat below safe to just push into.
See the project README for the known limits of amplitude-only sync vs.
real viseme timing (Phase 2, ``RhubarbVisemeVideoGenerator``).

Phase 2b (idle heartbeat): when blink art is loaded, a background task
pushes blink-only video frames (no audio) at a slow ``idle_fps`` while no
speech is flowing, so the avatar keeps blinking between agent turns instead
of freezing on its last frame. It paces itself with real ``asyncio.sleep``
(unlike the speech path, nothing here naturally throttles production) and
pauses immediately once real speech resumes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd, VideoGenerator

from ._audio_normalize import AudioNormalizer
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
        idle_fps: float = 5.0,
    ) -> None:
        """
        Args:
            assets: pre-loaded face + mouth-shape images (see ``AvatarAssets.load``).
            video_fps: output video frame rate.
            audio_sample_rate: the rate the avatar's audio track is
                published at. Pushed frames at any other rate are resampled
                to this (via LiveKit's `rtc.AudioResampler`), so it no
                longer has to match your TTS output exactly — but matching
                it avoids the resampling work entirely.
            audio_channels: channel count for the published audio track.
                Pushed mono/stereo frames are up/downmixed to match.
            open_threshold: RMS amplitude (on int16 PCM, 0-32768 range) above
                which the mouth is considered "open". Tune per-voice — TTS
                loudness varies a lot by provider/voice.
            enable_blink: periodically blink if `assets` has `face_blink.png`
                loaded. Also gates the idle heartbeat (below) — both are
                no-ops without blink art, since there'd be nothing to
                animate while idle.
            idle_fps: frame rate for the idle-heartbeat blink loop between
                utterances. Deliberately lower than `video_fps` — only the
                eyes are moving, no need for full rate.
        """
        self._assets = assets
        self._video_fps = video_fps
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels
        self._open_threshold = open_threshold
        self._idle_fps = idle_fps
        self._blink = BlinkDriver() if enable_blink else None

        self._bytes_per_window = bytes_per_window(audio_sample_rate, video_fps, audio_channels)
        self._normalizer = AudioNormalizer(sample_rate=audio_sample_rate, channels=audio_channels)

        self._pcm_buffer = bytearray()
        self._out_queue: asyncio.Queue[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd] = (
            asyncio.Queue()
        )

        # Idle heartbeat: only meaningful if we can actually blink.
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        self._idle_task: asyncio.Task[None] | None = None
        if self._blink is not None and assets.has_blink_art:
            self._idle_task = asyncio.create_task(self._idle_loop())

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
            # drain anything the resampler is still holding, then emit any
            # full windows that produced
            self._pcm_buffer.extend(self._normalizer.flush())
            await self._emit_full_windows()
            if self._pcm_buffer:
                # flush a final, silence-padded partial window rather than
                # dropping the tail of the last word
                padded = pad_to_window(bytes(self._pcm_buffer), self._bytes_per_window)
                self._pcm_buffer.clear()
                await self._emit_window(padded)
            await self._out_queue.put(AudioSegmentEnd())
            self._idle_event.set()  # utterance fully emitted — resume idle heartbeat
            return

        self._idle_event.clear()  # speech is flowing — pause idle heartbeat

        self._pcm_buffer.extend(self._normalizer.push(frame))
        await self._emit_full_windows()

    async def _emit_full_windows(self) -> None:
        while len(self._pcm_buffer) >= self._bytes_per_window:
            window = bytes(self._pcm_buffer[: self._bytes_per_window])
            del self._pcm_buffer[: self._bytes_per_window]
            await self._emit_window(window)

    async def _emit_window(self, pcm_bytes: bytes) -> None:
        state = MouthState.OPEN if rms_amplitude(pcm_bytes) > self._open_threshold else MouthState.CLOSED
        blinking = self._blink.advance(1.0 / self._video_fps) if self._blink is not None else False

        video_frame = self._assets.video_frame(state, blinking=blinking)
        audio_frame = make_audio_frame(
            pcm_bytes, sample_rate=self._audio_sample_rate, num_channels=self._audio_channels
        )
        await self._out_queue.put(video_frame)
        await self._out_queue.put(audio_frame)

    def clear_buffer(self) -> None:
        """Drop everything buffered — called on barge-in/interruption."""
        self._pcm_buffer.clear()
        self._normalizer.reset()
        while True:
            try:
                self._out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._idle_event.set()  # interrupted -> no more speech incoming, resume idle heartbeat

    def __aiter__(self) -> AsyncIterator[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd]:
        while True:
            yield await self._out_queue.get()

    async def _idle_loop(self) -> None:
        assert self._blink is not None
        interval = 1.0 / self._idle_fps
        while True:
            await self._idle_event.wait()
            await asyncio.sleep(interval)
            if not self._idle_event.is_set():
                continue  # speech started mid-sleep — skip this tick, don't fight it
            blinking = self._blink.advance(interval)
            await self._out_queue.put(self._assets.video_frame(MouthState.CLOSED, blinking=blinking))

    async def aclose(self) -> None:
        """Stop the idle-heartbeat background task, if one is running.

        Not called automatically by `AvatarRunner` — call this yourself on
        job shutdown if you construct short-lived generator instances (e.g.
        in tests); for the common case of one generator per agent process,
        it's fine to just let the process exit.
        """
        if self._idle_task is not None:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
