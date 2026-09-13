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

**v1 (amplitude-only lip-sync) — working**, **Phase 2a (real viseme timing
via Rhubarb Lip Sync) — working, opt-in**, and **Phase 2b (blinking) —
working.** `ImageAvatarVideoGenerator` (amplitude, minimal latency) is
still the default; `RhubarbVisemeVideoGenerator` (real per-phoneme mouth
shapes, added latency) is a drop-in alternative — see
[Real viseme timing](#real-viseme-timing-rhubarb-lip-sync) below. Both
generators blink periodically if `face_blink.png` is present (see
[Blinking](#blinking)). Built and verified against `livekit-agents==1.8.1`.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -e .

# generates assets/default/: face.png, mouth_closed/open.png (amplitude mode),
# mouth_x/a/b/c/d/e/f.png (viseme mode)
python scripts/generate_placeholder_assets.py

# exercises the full compositing + audio-chunking pipeline with no LiveKit
# room needed, and writes example output frames to assets/_smoke_test_output/
python scripts/smoke_test.py

# unit tests (WAV writing, rhubarb JSON parsing, replay pacing, fallback
# behavior) — no rhubarb binary needed for any of these
pip install -e ".[dev]"
pytest
```

Then wire it into your agent — see [`examples/local_agent_example.py`](examples/local_agent_example.py)
for the minimal `AgentSession` integration (co-located "local mode": the
avatar runs in the same process as your agent, no separate worker needed).

## Real viseme timing (Rhubarb Lip Sync)

For accurate per-phoneme mouth shapes instead of amplitude-only open/closed,
use `RhubarbVisemeVideoGenerator` — see
[`examples/rhubarb_agent_example.py`](examples/rhubarb_agent_example.py).
It's a drop-in alternative to `ImageAvatarVideoGenerator`, sharing the same
`AvatarAssets`/`AgentSession` wiring pattern.

**Install Rhubarb Lip Sync** (not pip-installable — a separate compiled
binary): download the zip for your platform from its
[releases page](https://github.com/DanielSWolf/rhubarb-lip-sync/releases),
extract `rhubarb`/`rhubarb.exe`, then either put it on your `PATH` or set
`RHUBARB_PATH=/full/path/to/rhubarb`.

**Latency tradeoff:** Rhubarb is a *batch* tool — it needs a complete
utterance's audio before it can produce any timing at all, unlike v1's
per-frame streaming. So this generator buffers a full utterance, then runs
Rhubarb as a subprocess, then replays the buffered audio against the now-known
viseme timeline — meaning the avatar does not start moving for a reply until
that reply's full audio has arrived *and* Rhubarb has finished processing it.
Use `ImageAvatarVideoGenerator` instead if minimal latency matters more than
lip-sync accuracy for your use case.

**Graceful fallback:** if the `rhubarb` binary is missing, or a given
utterance's invocation fails or times out, `RhubarbVisemeVideoGenerator` logs
one warning and falls back to amplitude-only lip-sync for that utterance
(reusing `MouthState.OPEN/CLOSED` from the same loaded assets) rather than
dropping audio or crashing your agent.

**Known transcript text:** since this is TTS output, you typically know the
exact words about to be spoken *before* they're synthesized — unlike Rhubarb's
usual use case. Call `video_gen.set_next_utterance_text(text)` right before
triggering that speech (e.g. before `session.say(text)`) to pass it through
to Rhubarb as `-d` dialog text, which recognizes speech far more accurately
than the default recognizer. This isn't wired automatically to any generic
`AgentSession` event yet (see Roadmap) — without it, the language-independent
`"phonetic"` recognizer is used, which still works, just less precisely.

Verify your own install end-to-end with a real speech clip (a synthetic tone
won't produce meaningful visemes):

```bash
python scripts/smoke_test_rhubarb.py path/to/short_speech_clip.wav
```

## Blinking

Both generators periodically blink — a small `BlinkDriver` ([`blink.py`](src/visage/blink.py))
picks randomized intervals (default 2.5–6s between blinks, ~150ms closed)
and swaps in `face_blink.png` for the duration. It's automatic and needs no
wiring: `AvatarAssets.load(...)` picks up `face_blink.png` if it's present
in your asset folder, and both generators use it unless you pass
`enable_blink=False`.

**No blink art, no blinking** — if `face_blink.png` is missing, `blinking=True`
is silently ignored rather than raising, so existing custom asset folders
keep working unchanged.

**Known limitation: blinking (and all animation) only happens while audio
is actively flowing.** Both generators only produce video frames from
pushed audio windows — there's no continuous idle frame-publishing loop, so
the avatar freezes on its last frame between agent turns rather than
blinking while silently waiting. Fixing that needs a separate
heartbeat/idle frame source feeding `AvatarRunner` even with no speech
happening, which is a real architecture addition, not a tuning knob —
deferred (see Roadmap). Idle head-sway (subtle bobbing/movement) was also
considered for this phase and deferred for the same reason plus the extra
transform/canvas-padding work it needs — call it a documented "won't do
yet" rather than a partial attempt.

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
- `face_blink.png` — OPTIONAL, same size, eyes closed — enables blinking
- `mouth_closed.png`, `mouth_open.png` — RGBA overlays for
  `ImageAvatarVideoGenerator` (amplitude mode)
- `mouth_x.png` .. `mouth_f.png` — RGBA overlays for
  `RhubarbVisemeVideoGenerator` (viseme mode) — only needed if you use it

All overlays must be **the same pixel dimensions as `face.png`**, transparent
everywhere except the mouth. Then `AvatarAssets.load("path/to/your/folder", states=(*MouthState, *Viseme))`
(or just `MouthState/Viseme` alone if you only need one mode). Any flat
illustration tool (Figma, Canva, Aseprite) works — no 3D, no rigging.

## Known limitations

- **No audio resampling** — `audio_sample_rate` must match your TTS
  provider's actual output rate exactly, or audio will play at the wrong
  pitch/speed. `push_audio` logs a warning on mismatch but does not correct it.
- **Transparent background becomes black** — published video frames are
  RGB24 (no alpha channel), so anything outside your face art renders black.
  Fine against a dark UI; needs a background color/image if you want
  something else.
- **`open_threshold`/`amplitude_fallback_threshold` are unit-less relative to
  int16 PCM RMS** and will need tuning per TTS voice/provider — loudness
  varies a lot.
- **Rhubarb mode adds per-utterance latency** (subprocess start + processing
  time) before the avatar starts moving for that reply — see
  [Real viseme timing](#real-viseme-timing-rhubarb-lip-sync).
- **G/H extended viseme shapes have no dedicated art** — they map to the
  nearest basic shape we do have art for (G→F, H→C) rather than being drawn
  distinctly.
- **Blinking (and all animation) stops between agent turns** — see
  [Blinking](#blinking); there's no idle head-sway either (deferred, not
  attempted).

## Roadmap

- [x] Phase 0/1 — pipeline proof + amplitude-only MVP
- [x] Phase 2a — real viseme timing via Rhubarb Lip Sync (opt-in `RhubarbVisemeVideoGenerator`)
- [x] Phase 2b — blinking
- [ ] Phase 3 — swappable art-set packaging, published as a pip package
- [ ] Phase 4 — demo video, community distribution
- [ ] fast-follow — dedicated G/H viseme art; verify a safe `AgentSession`
      hook to auto-wire known TTS transcript text into rhubarb's `-d` flag;
      continuous idle animation (blink/sway between turns) via a heartbeat
      frame source

## License

MIT — see [LICENSE](LICENSE).
