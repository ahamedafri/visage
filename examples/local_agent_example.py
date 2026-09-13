"""Minimal wiring example: attach visage to a LiveKit AgentSession.

This is "local mode" — the avatar's video/audio are generated and published
in the same process as your agent (no separate avatar worker/service). This
is the simplest way to try visage; it mirrors the pattern used internally by
livekit-plugins-bithuman's local mode (QueueAudioOutput as both the agent's
audio sink and the AvatarRunner's audio source).

This file is a template, not a runnable app on its own — plug it into
wherever your agent currently builds its `AgentSession` (see LiveKit's
`agents` quickstart for the surrounding `entrypoint`/`cli.run_app` scaffold).
"""

from __future__ import annotations

from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice.avatar import AvatarOptions, AvatarRunner, QueueAudioOutput

from visage import AvatarAssets, ImageAvatarVideoGenerator, default_assets_dir

DEFAULT_ASSETS = default_assets_dir()  # swap for your own art: AvatarAssets.load("path/to/folder")

# Must match your TTS output's sample rate — see ImageAvatarVideoGenerator's
# docstring. e.g. Cartesia's sonic-2 over LiveKit Inference is commonly 24000.
TTS_SAMPLE_RATE = 24000


async def attach_avatar(
    room: rtc.Room, agent_session: AgentSession
) -> tuple[AvatarRunner, ImageAvatarVideoGenerator]:
    assets = AvatarAssets.load(DEFAULT_ASSETS)
    video_gen = ImageAvatarVideoGenerator(
        assets,
        video_fps=25.0,
        audio_sample_rate=TTS_SAMPLE_RATE,
        audio_channels=1,
    )

    avatar_options = AvatarOptions(
        video_width=video_gen.video_resolution[0],
        video_height=video_gen.video_resolution[1],
        video_fps=video_gen.video_fps,
        audio_sample_rate=video_gen.audio_sample_rate,
        audio_channels=1,
    )

    # QueueAudioOutput is both: what the AgentSession writes TTS audio into,
    # and what AvatarRunner reads audio from.
    audio_bridge = QueueAudioOutput(sample_rate=TTS_SAMPLE_RATE, wait_playback_start=True)

    avatar_runner = AvatarRunner(
        room=room,
        video_gen=video_gen,
        audio_recv=audio_bridge,
        options=avatar_options,
    )
    await avatar_runner.start()

    # Redirect the agent's spoken audio into the avatar pipeline instead of
    # straight into the room.
    agent_session.output.replace_audio_tail(audio_bridge)

    return avatar_runner, video_gen


# In your entrypoint, after `agent_session.start(...)`:
#
#     avatar_runner, video_gen = await attach_avatar(ctx.room, agent_session)
#     ...
#     # on shutdown:
#     await avatar_runner.aclose()
#     await video_gen.aclose()  # stops the idle-heartbeat/blink background task
