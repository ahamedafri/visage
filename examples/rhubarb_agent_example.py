"""Wiring example: attach visage's real-viseme (Rhubarb) avatar to an AgentSession.

Parallel to `local_agent_example.py` (amplitude-only, minimal latency) —
this one uses `RhubarbVisemeVideoGenerator` for accurate per-phoneme mouth
shapes, at the cost of added latency: the avatar will not start moving for
a given reply until that reply's FULL audio has arrived AND rhubarb has
finished processing it (subprocess start + processing time). If you need
minimal latency, use `local_agent_example.py` / `ImageAvatarVideoGenerator`
instead.

Requires the `rhubarb` binary installed separately — see README "Real
viseme timing (Rhubarb Lip Sync)". If it's missing (or a given utterance's
invocation fails/times out), this generator logs one warning and falls
back to amplitude-only lip-sync automatically — it will not crash your agent.
"""

from __future__ import annotations

from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice.avatar import AvatarOptions, AvatarRunner, QueueAudioOutput

from visage import AvatarAssets, MouthState, RhubarbVisemeVideoGenerator, Viseme, default_assets_dir

DEFAULT_ASSETS = default_assets_dir()  # swap for your own art: AvatarAssets.load("path/to/folder")

# Must match your TTS output's sample rate — see RhubarbVisemeVideoGenerator's
# docstring. e.g. Cartesia's sonic-2 over LiveKit Inference is commonly 24000.
TTS_SAMPLE_RATE = 24000


async def attach_avatar(room: rtc.Room, agent_session: AgentSession) -> tuple[AvatarRunner, RhubarbVisemeVideoGenerator]:
    # Needs BOTH Viseme (for real lip-sync) and MouthState (for the
    # amplitude fallback) frames loaded from the same asset folder.
    assets = AvatarAssets.load(DEFAULT_ASSETS, states=(*MouthState, *Viseme))

    video_gen = RhubarbVisemeVideoGenerator(
        assets,
        video_fps=25.0,
        audio_sample_rate=TTS_SAMPLE_RATE,
        audio_channels=1,
        # rhubarb_path="C:/tools/rhubarb/rhubarb.exe",  # or set RHUBARB_PATH env var
    )

    avatar_options = AvatarOptions(
        video_width=video_gen.video_resolution[0],
        video_height=video_gen.video_resolution[1],
        video_fps=video_gen.video_fps,
        audio_sample_rate=video_gen.audio_sample_rate,
        audio_channels=1,
    )

    audio_bridge = QueueAudioOutput(sample_rate=TTS_SAMPLE_RATE, wait_playback_start=True)

    avatar_runner = AvatarRunner(
        room=room,
        video_gen=video_gen,
        audio_recv=audio_bridge,
        options=avatar_options,
    )
    await avatar_runner.start()

    agent_session.output.replace_audio_tail(audio_bridge)

    return avatar_runner, video_gen


# In your entrypoint, after `agent_session.start(...)`:
#
#     avatar_runner, video_gen = await attach_avatar(ctx.room, agent_session)
#
#     # Optional but recommended: if you already have the exact reply text
#     # at the point you trigger speech (e.g. calling session.say(text) or
#     # generate_reply yourself), tell the generator about it right before —
#     # this is passed to rhubarb as `-d` dialog text for much better
#     # recognition than the default recognizer:
#     #
#     #     video_gen.set_next_utterance_text(text)
#     #     await session.say(text)
#     #
#     # There's no automatic wiring for this from a generic AgentSession
#     # event yet (verifying a safe hook for that is a documented fast-follow
#     # — see README roadmap) — without it, the "phonetic" recognizer is used,
#     # which still works, just less precisely.
#
#     ...
#     # on shutdown:
#     await avatar_runner.aclose()
#     await video_gen.aclose()  # stops the worker + idle-heartbeat/blink background tasks
