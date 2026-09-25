"""Live end-to-end test against a REAL LiveKit server (no LLM/TTS needed).

Two participants join a fresh room on your LiveKit server:

  1. "visage-avatar" — runs the exact publish path an agent would use:
     QueueAudioOutput -> AvatarRunner -> ImageAvatarVideoGenerator, fed
     with synthetic "speech" (or a WAV you pass in), and publishes the
     avatar's video + audio tracks.
  2. "visage-viewer" — subscribes like a browser client would and counts
     the video/audio frames it actually receives, so the pass/fail is
     based on what came back through the server, not on what we sent.

Credentials: LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET from the
environment, or from a .env file via --env-file (values are never printed).

    python scripts/live_test.py --env-file path/to/.env [--wav speech.wav] [--seconds 6]

It also prints a room name + writes a viewer token to _live_test_token.txt
(gitignored) so you can watch the same room yourself at https://meet.livekit.io
(Custom tab) while it runs, or afterwards with --hold to keep it open.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np
from livekit import api, rtc
from livekit.agents.voice.avatar import AvatarOptions, AvatarRunner, QueueAudioOutput

from visage import AvatarAssets, ImageAvatarVideoGenerator, MouthState, Viseme, default_assets_dir

SR = 24000
ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def synthetic_speech(seconds: float) -> list[rtc.AudioFrame]:
    """Syllable-like bursts: 120ms tone / 80ms silence, in 20ms frames."""
    frames = []
    t_total = 0.0
    while t_total < seconds:
        for dur, loud in ((0.12, True), (0.08, False), (0.16, True), (0.14, False)):
            n = int(SR * 0.02)
            for _ in range(int(dur / 0.02)):
                if loud:
                    t = np.linspace(t_total, t_total + 0.02, n, endpoint=False)
                    s = (np.sin(2 * np.pi * 180 * t) * 7000).astype(np.int16)
                else:
                    s = np.zeros(n, dtype=np.int16)
                frames.append(rtc.AudioFrame(data=s.tobytes(), sample_rate=SR, num_channels=1, samples_per_channel=n))
                t_total += 0.02
    return frames


def wav_frames(path: Path) -> list[rtc.AudioFrame]:
    with wave.open(str(path), "rb") as wf:
        assert wf.getsampwidth() == 2, "need 16-bit PCM WAV"
        rate, ch = wf.getframerate(), wf.getnchannels()
        pcm = wf.readframes(wf.getnframes())
    step = int(rate * 0.02) * ch * 2
    return [
        rtc.AudioFrame(data=pcm[i : i + step], sample_rate=rate, num_channels=ch,
                       samples_per_channel=len(pcm[i : i + step]) // 2 // ch)
        for i in range(0, len(pcm) - step + 1, step)
    ]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("--wav", type=Path, help="16-bit PCM WAV to speak instead of synthetic audio")
    ap.add_argument("--seconds", type=float, default=6.0, help="synthetic speech length")
    ap.add_argument("--hold", type=float, default=0.0, help="keep the room open N extra seconds so you can watch")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)
    url, key, secret = (os.environ.get(k) for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))
    if not (url and key and secret):
        print("missing LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET (env or --env-file)")
        return 2

    room_name = f"visage-live-test-{int(time.time())}"

    def token(identity: str) -> str:
        return (
            api.AccessToken(key, secret)
            .with_identity(identity)
            .with_name(identity)
            .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
            .to_jwt()
        )

    viewer_token_path = ROOT / "_live_test_token.txt"
    viewer_token_path.write_text(token("you"), encoding="utf-8")
    print(f"room: {room_name}")
    print(f"server: {url}")
    print(f"to watch: https://meet.livekit.io -> Custom -> paste server URL + token from {viewer_token_path.name}")

    # ---- viewer participant (what a browser would see) -------------------
    started = time.time()

    def t() -> str:
        return f"[t+{time.time() - started:5.2f}s]"

    stats = {"video": 0, "audio_secs": 0.0, "voiced_secs": 0.0, "audio_rate": 0, "w": 0, "h": 0,
             "first_video_at": None, "first_voiced_at": None, "publisher": None}
    tasks: list[asyncio.Task] = []

    async def read_video(track: rtc.Track) -> None:
        async for ev in rtc.VideoStream(track):
            if stats["first_video_at"] is None:
                stats["first_video_at"] = time.time() - started
                print(f"{t()} viewer: first VIDEO frame")
            stats["video"] += 1
            stats["w"], stats["h"] = ev.frame.width, ev.frame.height

    async def read_audio(track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track):
            # WebRTC decodes at its own rate (typically 48 kHz), not ours —
            # measure in seconds using the frame's rate, not SR
            secs = ev.frame.samples_per_channel / ev.frame.sample_rate
            stats["audio_secs"] += secs
            stats["audio_rate"] = ev.frame.sample_rate
            samples = np.frombuffer(bytes(ev.frame.data), dtype=np.int16)
            if len(samples) and np.sqrt(np.mean(samples.astype(np.float64) ** 2)) > 300:
                if stats["first_voiced_at"] is None:
                    stats["first_voiced_at"] = time.time() - started
                    print(f"{t()} viewer: first non-silent AUDIO")
                stats["voiced_secs"] += secs

    viewer = rtc.Room()

    @viewer.on("track_subscribed")
    def _on_sub(track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant) -> None:
        stats["publisher"] = participant.identity
        kind = "VIDEO" if track.kind == rtc.TrackKind.KIND_VIDEO else "AUDIO"
        print(f"{t()} viewer: subscribed to {kind} track from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_VIDEO:
            tasks.append(asyncio.create_task(read_video(track)))
        elif track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(asyncio.create_task(read_audio(track)))

    await viewer.connect(url, token("visage-viewer"))
    print(f"{t()} viewer connected")

    # ---- avatar participant (exactly the agent-side wiring) --------------
    avatar_room = rtc.Room()

    @avatar_room.on("local_track_published")
    def _on_pub(pub: rtc.LocalTrackPublication, track: rtc.Track) -> None:
        kind = "VIDEO" if track.kind == rtc.TrackKind.KIND_VIDEO else "AUDIO"
        print(f"{t()} avatar: published {kind} track")

    await avatar_room.connect(url, token("visage-avatar"))
    print(f"{t()} avatar connected")

    assets = AvatarAssets.load(default_assets_dir(), states=(*MouthState, *Viseme), background=(28, 32, 40))
    gen = ImageAvatarVideoGenerator(assets, audio_sample_rate=SR, video_fps=25.0)
    bridge = QueueAudioOutput(sample_rate=SR)
    runner = AvatarRunner(
        avatar_room,
        video_gen=gen,
        audio_recv=bridge,
        options=AvatarOptions(
            video_width=gen.video_resolution[0],
            video_height=gen.video_resolution[1],
            video_fps=gen.video_fps,
            audio_sample_rate=SR,
            audio_channels=1,
        ),
    )
    await runner.start()
    print(f"{t()} avatar runner started")

    frames = wav_frames(args.wav) if args.wav else synthetic_speech(args.seconds)
    speech_seconds = sum(f.samples_per_channel / f.sample_rate for f in frames)
    print(f"{t()} pushing {speech_seconds:.1f}s of audio ({len(frames)} frames)")
    for f in frames:
        await bridge.capture_frame(f)
    bridge.flush()
    push_done = time.time() - started
    print(f"{t()} audio queued; waiting for real-time playout")

    await asyncio.sleep(speech_seconds + 3.0 + args.hold)

    # ---- report ----------------------------------------------------------
    for t in tasks:
        t.cancel()
    await runner.aclose()
    await gen.aclose()
    await avatar_room.disconnect()
    await viewer.disconnect()

    voiced_s = stats["voiced_secs"]
    # the synthetic pattern is ~56% voiced (0.28s tone per 0.50s cycle)
    expected_voiced = speech_seconds * (0.56 if not args.wav else 0.4)
    print("\n=== viewer received ===")
    print(f"publisher identity   : {stats['publisher']}")
    print(f"video frames         : {stats['video']}  ({stats['w']}x{stats['h']})")
    print(f"audio, total         : {stats['audio_secs']:.2f}s @ {stats['audio_rate']} Hz (includes silence around speech)")
    print(f"audio, non-silent    : {voiced_s:.2f}s (expected ~{expected_voiced:.1f}s)")
    if stats["first_video_at"] is not None:
        print(f"first video frame    : {stats['first_video_at'] - push_done:.2f}s after audio was queued")
    if stats["first_voiced_at"] is not None:
        print(f"first non-silent audio: {stats['first_voiced_at'] - push_done:.2f}s after audio was queued")

    expected_video = speech_seconds * 25
    ok = (
        stats["publisher"] == "visage-avatar"
        and stats["video"] >= 0.5 * expected_video
        and voiced_s >= 0.5 * expected_voiced
        and (stats["w"], stats["h"]) == gen.video_resolution
    )
    print("\nRESULT:", "PASS" if ok else "FAIL", f"(expected ~{expected_video:.0f} video frames)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
