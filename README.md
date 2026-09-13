# visage

Free, self-hosted 2D lip-synced avatars for [LiveKit](https://livekit.io) voice
agents — no per-minute avatar-provider fees.

LiveKit's [avatar plugin directory](https://docs.livekit.io/agents/integrations/avatar/)
lists a dozen+ hosted avatar providers, all billed per minute. If you just
want a simple animated face that reacts to your agent's speech — not
photorealistic video — you shouldn't have to pay for that. `visage` runs
entirely on CPU, in-process with your agent or as a separate worker, using
flat 2D art you can swap for your own.

## Status

**v1 (amplitude-only lip-sync) — working.** The mouth toggles open/closed
based on audio loudness; no real viseme/phoneme timing yet (see
[Roadmap](#roadmap)). Built and verified against `livekit-agents==1.8.1`.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -e .

# generates assets/default/{face,mouth_closed,mouth_open}.png
python scripts/generate_placeholder_assets.py

# exercises the full compositing + audio-chunking pipeline with no LiveKit
# room needed, and writes example output frames to assets/_smoke_test_output/
python scripts/smoke_test.py
```

Then wire it into your agent — see [`examples/local_agent_example.py`](examples/local_agent_example.py)
for the minimal `AgentSession` integration (co-located "local mode": the
avatar runs in the same process as your agent, no separate worker needed).

## How it works

```
   your AgentSession's TTS audio
              │
              ▼
     QueueAudioOutput  ──────────────►  AvatarRunner
     (agent's audio sink,                  │
      AvatarRunner's audio source)         ▼
                                  ImageAvatarVideoGenerator
                                  ─────────────────────────
                                  chunk PCM into per-video-frame
                                  windows → RMS amplitude → pick
                                  mouth_open.png or mouth_closed.png
                                  → composite onto face.png → RGB24
                                  video frame
                                            │
                                            ▼
                                  published video + audio track,
                                  synced by LiveKit's AVSynchronizer
```

`ImageAvatarVideoGenerator` implements LiveKit Agents' real
`voice.avatar.VideoGenerator` ABC (`push_audio` / `clear_buffer` /
`__aiter__`), modeled on the same pattern used internally by
`livekit-plugins-bithuman`.

## Custom art

Drop a folder anywhere with:
- `face.png` — RGBA, defines the canvas size
- `mouth_closed.png`, `mouth_open.png` — RGBA overlays, **same pixel
  dimensions as `face.png`**, transparent everywhere except the mouth

then `AvatarAssets.load("path/to/your/folder")`. Any flat illustration tool
(Figma, Canva, Aseprite) works — no 3D, no rigging.

## Known limitations (v1)

- **No real viseme timing** — amplitude-only open/closed is a rough
  approximation, not per-phoneme lip-sync. Planned for Phase 2 (Rhubarb Lip
  Sync integration).
- **No audio resampling** — `audio_sample_rate` must match your TTS
  provider's actual output rate exactly, or audio will play at the wrong
  pitch/speed. `push_audio` logs a warning on mismatch but does not correct it.
- **Transparent background becomes black** — published video frames are
  RGB24 (no alpha channel), so anything outside your face art renders black.
  Fine against a dark UI; needs a background color/image if you want
  something else.
- **`open_threshold` is unit-less relative to int16 PCM RMS** and will need
  tuning per TTS voice/provider — loudness varies a lot.

## Roadmap

- [x] Phase 0/1 — pipeline proof + amplitude-only MVP (this repo, today)
- [ ] Phase 2 — real viseme timing via Rhubarb Lip Sync, more mouth shapes,
      blink/idle-sway polish
- [ ] Phase 3 — swappable art-set packaging, published as a pip package
- [ ] Phase 4 — demo video, community distribution

## License

MIT — see [LICENSE](LICENSE).
