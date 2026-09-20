"""Phase 2 VideoGenerator: real viseme timing via Rhubarb Lip Sync.

Unlike ``ImageAvatarVideoGenerator`` (v1, amplitude-only, per-frame
streaming with minimal latency), Rhubarb is a batch tool that needs a
complete utterance's audio before it can produce any viseme timing at all.
So this generator necessarily buffers a whole utterance, runs Rhubarb as a
subprocess once ``AudioSegmentEnd`` arrives, then replays the buffered
audio paired with the now-known viseme timeline — meaning the avatar does
not start moving for a given reply until that reply's full audio has
arrived AND Rhubarb has finished processing it. If you need minimal
latency, use ``ImageAvatarVideoGenerator`` instead.

If the ``rhubarb`` binary is missing, or a given utterance's invocation
fails or times out, this generator logs a warning and falls back to
amplitude-only lip-sync (reusing ``MouthState.OPEN/CLOSED`` from the same
``AvatarAssets``) for that utterance rather than dropping audio or crashing
the agent.

Phase 2b (idle heartbeat): when blink art is loaded, a background task
pushes ``Viseme.X`` (idle/rest) blink-only video frames at a slow
``idle_fps`` while no utterance is buffering/replaying, so the avatar keeps
blinking between agent turns instead of freezing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from math import ceil
from typing import Literal

from livekit import rtc
from livekit.agents.voice.avatar import AudioSegmentEnd, VideoGenerator

from ._audio_normalize import AudioNormalizer
from ._pcm_windowing import bytes_per_window, make_audio_frame, pad_to_window, rms_amplitude
from .assets import AvatarAssets, MouthState, Viseme
from .blink import BlinkDriver
from .rhubarb import (
    RhubarbError,
    RhubarbNotFoundError,
    VisemeCue,
    find_rhubarb_executable,
    plan_viseme_sequence,
    run_rhubarb,
)

logger = logging.getLogger("visage")


@dataclass
class _UtteranceJob:
    pcm_bytes: bytes
    num_channels: int
    dialog_text: str | None


class RhubarbVisemeVideoGenerator(VideoGenerator):
    def __init__(
        self,
        assets: AvatarAssets,
        *,
        video_fps: float = 25.0,
        audio_sample_rate: int = 24000,
        audio_channels: int = 1,
        rhubarb_path: str | None = None,
        recognizer: Literal["pocketSphinx", "phonetic"] = "phonetic",
        rhubarb_timeout: float = 15.0,
        amplitude_fallback_threshold: float = 500.0,
        enable_blink: bool = True,
        idle_fps: float = 5.0,
    ) -> None:
        """
        Args:
            assets: must have BOTH `Viseme` and `MouthState` frames loaded
                (e.g. ``AvatarAssets.load(dir, states=(*MouthState, *Viseme))``)
                — `MouthState` is needed for the amplitude fallback path.
            audio_sample_rate / audio_channels: the format the avatar's
                audio track is published at (and the WAV handed to
                rhubarb). Pushed frames at any other rate/channel count are
                normalized to this — see `ImageAvatarVideoGenerator`.
            rhubarb_path: explicit path to the rhubarb executable. Falls
                back to the RHUBARB_PATH env var, then PATH, if unset.
            recognizer: used only when no per-utterance dialog text is set
                via `set_next_utterance_text` — "phonetic" is
                language-independent; "pocketSphinx" is English-only but
                more accurate on English speech.
            rhubarb_timeout: seconds to wait for one rhubarb invocation
                before treating it as failed and falling back.
            amplitude_fallback_threshold: same meaning as
                `ImageAvatarVideoGenerator`'s `open_threshold`, used only
                when falling back.
            enable_blink: periodically blink if `assets` has `face_blink.png`
                loaded. Also gates the idle heartbeat (below) — both are
                no-ops without blink art.
            idle_fps: frame rate for the idle-heartbeat blink loop between
                utterances (while no audio is buffering or replaying).
        """
        # fail fast at construction, not deep inside an async replay
        for shape in (*Viseme, *MouthState):
            try:
                assets.video_frame(shape)
            except KeyError as e:
                raise ValueError(
                    "RhubarbVisemeVideoGenerator requires assets with a frame for "
                    "every Viseme AND every MouthState — MouthState frames back the "
                    "amplitude-fallback path used when rhubarb is unavailable or a "
                    f"given utterance's invocation fails. {e}. If you built a "
                    "photoreal/full-frame set covering only Viseme shapes, either "
                    "add full_closed.png and full_open.png too (see README "
                    "'Using AI-generated / photoreal art'), or use "
                    "ImageAvatarVideoGenerator instead if you don't need Rhubarb's "
                    "fallback safety net."
                ) from e

        self._assets = assets
        self._video_fps = video_fps
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels
        self._rhubarb_path = rhubarb_path
        self._recognizer = recognizer
        self._rhubarb_timeout = rhubarb_timeout
        self._amplitude_fallback_threshold = amplitude_fallback_threshold
        self._idle_fps = idle_fps
        self._blink = BlinkDriver() if enable_blink else None

        self._bytes_per_window = bytes_per_window(audio_sample_rate, video_fps, audio_channels)
        self._normalizer = AudioNormalizer(sample_rate=audio_sample_rate, channels=audio_channels)

        self._pcm_buffer = bytearray()
        self._pending_text: str | None = None

        self._pending_jobs: asyncio.Queue[_UtteranceJob] = asyncio.Queue()
        self._out_queue: asyncio.Queue[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd] = (
            asyncio.Queue()
        )
        self._interrupted = asyncio.Event()
        self._current_proc: asyncio.subprocess.Process | None = None

        # None = not yet probed, "unavailable" = probed and missing (don't
        # re-probe every utterance), else the resolved Path.
        self._resolved_rhubarb: object = None
        self._warned_missing_once = False

        self._worker_task = asyncio.create_task(self._run_worker())

        # Idle heartbeat: only meaningful if we can actually blink.
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        self._idle_task: asyncio.Task[None] | None = None
        if self._blink is not None and assets.has_blink_art:
            self._idle_task = asyncio.create_task(self._idle_loop())

    def set_next_utterance_text(self, text: str | None) -> None:
        """Best-effort known TTS transcript for the *next* utterance (i.e.
        the audio pushed up to the next AudioSegmentEnd). Passed to rhubarb
        as `-d` dialog text for significantly better recognition than the
        default recognizer. Consumed once. Call this right before/while
        pushing that utterance's audio — e.g. at your own `session.say(text)`
        call site. Leave unset to use `recognizer` instead."""
        self._pending_text = text

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
            self._pcm_buffer.extend(self._normalizer.flush())
            job = _UtteranceJob(
                pcm_bytes=bytes(self._pcm_buffer),
                num_channels=self._audio_channels,
                dialog_text=self._pending_text,
            )
            self._pcm_buffer.clear()
            self._pending_text = None
            await self._pending_jobs.put(job)
            return

        self._idle_event.clear()  # speech is flowing — pause idle heartbeat
        self._pcm_buffer.extend(self._normalizer.push(frame))

    def clear_buffer(self) -> None:
        """Drop everything buffered/queued and kill any in-flight rhubarb
        subprocess — called on barge-in/interruption."""
        self._pcm_buffer.clear()
        self._normalizer.reset()
        self._pending_text = None
        while True:
            try:
                self._pending_jobs.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._current_proc is not None:
            try:
                self._current_proc.kill()
            except ProcessLookupError:
                pass
        self._interrupted.set()
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

    async def _run_worker(self) -> None:
        while True:
            job = await self._pending_jobs.get()
            self._interrupted.clear()
            cues = await self._resolve_cues(job)
            await self._replay(job, cues)
            await self._out_queue.put(AudioSegmentEnd())
            if self._pending_jobs.empty():
                self._idle_event.set()  # nothing else queued — resume idle heartbeat

    async def _resolve_cues(self, job: _UtteranceJob) -> list[VisemeCue] | None:
        if not job.pcm_bytes:
            return []

        if self._resolved_rhubarb == "unavailable":
            return None
        if self._resolved_rhubarb is None:
            try:
                self._resolved_rhubarb = find_rhubarb_executable(self._rhubarb_path)
            except RhubarbNotFoundError as e:
                self._resolved_rhubarb = "unavailable"
                if not self._warned_missing_once:
                    logger.warning(
                        "%s — falling back to amplitude-only lip-sync for all utterances", e
                    )
                    self._warned_missing_once = True
                return None

        def _register_proc(proc: asyncio.subprocess.Process) -> None:
            self._current_proc = proc

        try:
            cues = await run_rhubarb(
                self._resolved_rhubarb,  # type: ignore[arg-type]
                job.pcm_bytes,
                sample_rate=self._audio_sample_rate,
                channels=job.num_channels,
                dialog_text=job.dialog_text,
                recognizer=self._recognizer,
                timeout=self._rhubarb_timeout,
                on_process_started=_register_proc,
            )
        except RhubarbError as e:
            logger.warning(
                "rhubarb failed for this utterance (%s) — falling back to "
                "amplitude-only lip-sync",
                e,
            )
            return None
        finally:
            self._current_proc = None

        return cues

    async def _replay(self, job: _UtteranceJob, cues: list[VisemeCue] | None) -> None:
        if not job.pcm_bytes:
            return

        total_windows = max(1, ceil(len(job.pcm_bytes) / self._bytes_per_window))
        visemes = (
            plan_viseme_sequence(cues, total_windows, self._video_fps) if cues is not None else None
        )

        for i in range(total_windows):
            if self._interrupted.is_set():
                return

            start = i * self._bytes_per_window
            window = pad_to_window(
                job.pcm_bytes[start : start + self._bytes_per_window], self._bytes_per_window
            )

            if visemes is not None:
                shape = visemes[i]
            else:
                shape = (
                    MouthState.OPEN
                    if rms_amplitude(window) > self._amplitude_fallback_threshold
                    else MouthState.CLOSED
                )
            blinking = self._blink.advance(1.0 / self._video_fps) if self._blink is not None else False

            await self._out_queue.put(self._assets.video_frame(shape, blinking=blinking))
            await self._out_queue.put(
                make_audio_frame(
                    window, sample_rate=self._audio_sample_rate, num_channels=job.num_channels
                )
            )

    async def _idle_loop(self) -> None:
        assert self._blink is not None
        interval = 1.0 / self._idle_fps
        while True:
            await self._idle_event.wait()
            await asyncio.sleep(interval)
            if not self._idle_event.is_set():
                continue  # speech started mid-sleep — skip this tick, don't fight it
            blinking = self._blink.advance(interval)
            await self._out_queue.put(self._assets.video_frame(Viseme.X, blinking=blinking))

    async def aclose(self) -> None:
        """Stop the background worker and idle-heartbeat tasks.

        Not called automatically by `AvatarRunner` — call this yourself on
        job shutdown if you construct short-lived generator instances (e.g.
        in tests); for the common case of one generator per agent process,
        it's fine to just let the process exit.
        """
        for task in (self._worker_task, self._idle_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
