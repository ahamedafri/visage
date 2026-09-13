# visage

Free, self-hosted 2D lip-synced avatars for [LiveKit](https://livekit.io) voice
agents — no per-minute avatar-provider fees.

LiveKit's [avatar plugin directory](https://docs.livekit.io/agents/integrations/avatar/)
lists a dozen+ hosted avatar providers, all billed per minute. If you just
want a simple animated face that reacts to your agent's speech — not
photorealistic video — you shouldn't have to pay for that. `visage` runs
entirely on CPU, in-process with your agent or as a separate worker, using
flat 2D art you can swap for your own — hand-drawn, or a realistic set
generated from a photo (see [Using AI-generated / photoreal art](#using-ai-generated--photoreal-art)).

## Status

`pip install`-able (see [Quickstart](#quickstart)). **v1 (amplitude-only
lip-sync) — working**, **Phase 2a (real viseme timing via Rhubarb Lip
Sync) — working, opt-in**, and **Phase 2b (blinking + idle heartbeat) —
working.** `ImageAvatarVideoGenerator` (amplitude, minimal latency) is
still the default; `RhubarbVisemeVideoGenerator` (real per-phoneme mouth
shapes, added latency) is a drop-in alternative — see
[Real viseme timing](#real-viseme-timing-rhubarb-lip-sync) below. Both
generators blink periodically — including between agent turns, not just
while speaking — if blink art is present (see [Blinking](#blinking)).
Built and verified against `livekit-agents==1.8.1`.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -e .

# exercises the full compositing + audio-chunking pipeline with no LiveKit
# room needed, against the packaged default face — writes example output
# frames to _smoke_test_output/
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

**Idle heartbeat:** when blink art is loaded, each generator also runs a
background task that keeps blinking between agent turns — not just while
audio is flowing — by pushing blink-only video frames (no audio) at a slow
`idle_fps` (default 5, tunable) whenever no utterance is buffering or
replaying. It pauses the instant real speech starts and resumes as soon as
that utterance is fully emitted (or immediately, on interruption via
`clear_buffer`). This relies on `livekit.rtc.AVSynchronizer`'s own internal
bounded queue + real-time pacing (verified by reading its source) to safely
absorb whatever we push — our heartbeat still self-paces with `asyncio.sleep`
so it doesn't pre-queue idle frames far into the future and become
unresponsive to an interruption. If you construct short-lived generator
instances yourself (e.g. in tests), call `await video_gen.aclose()` to stop
this background task — not needed for the normal one-generator-per-agent-process
case, since `asyncio.run`/job shutdown cancels it anyway.

Idle head-sway (subtle bobbing/movement) was considered for this phase too
and deferred — it needs off-canvas padding/transform work disproportionate
to the visual payoff. Documented as a "won't do yet," not a partial attempt.

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

The bundled default face (`visage.default_assets_dir()`) is generated by
[`scripts/generate_placeholder_assets.py`](scripts/generate_placeholder_assets.py) —
run it again after editing that script if you want to tweak the placeholder
art itself rather than swapping in a whole new folder.

## Using AI-generated / photoreal art

`visage` doesn't generate any images itself — this is about loading art you
made elsewhere. If you want a realistic face instead of the flat placeholder
style, you can use an identity-consistent AI photo generator — tools like
Ideogram Character, FLUX PuLID, or InstantID/IP-Adapter-FaceID-style
workflows (run via their own web UI, or an API like Replicate) — to take one
reference photo and generate a handful of images of the same person/identity
in different mouth shapes.

**Why this needs a different loading function:** these tools output a
complete, already-composed photo per generation ("the same person, mouth
open") — not a transparent, precisely-aligned mouth-only overlay cropped
against a separate base face. Getting an aligned alpha cutout out of a
generative photo tool isn't practical, so the `face.png` + `mouth_<state>.png`
overlay convention above doesn't apply here. Use `AvatarAssets.load_full_frames`
instead, which takes complete images with no compositing step:

- `full_<state>.png` — required, one complete image per state you need
  (`closed`/`open` for amplitude mode, `x`/`a`/`b`/`c`/`d`/`e`/`f` for viseme mode)
- `full_<state>_blink.png` — OPTIONAL per state, eyes closed — you don't
  need a blink variant for every state; missing ones just don't blink

```python
assets = AvatarAssets.load_full_frames("path/to/your/folder", states=(*MouthState, *Viseme))
```

**Workflow:** starting from one reference photo, generate one full image per
required state, keeping framing/crop/lighting/head position as consistent as
you can across all of them — there's no compositing step to hide
misalignment here, unlike overlay mode where a single shared `face.png`
makes drift impossible by construction. `load_full_frames` only checks that
the right files exist and share one pixel size; it can't and doesn't verify
that your generated images actually look consistent with each other — a
subtly misaligned set will visibly "jump" between frames during playback.

If you're using `RhubarbVisemeVideoGenerator`, it still needs `MouthState`
frames loaded too (for its amplitude-fallback path when Rhubarb is
unavailable or fails) — generate `full_closed.png`/`full_open.png` as well,
or use `ImageAvatarVideoGenerator` instead if you only need viseme coverage.

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
- **No idle head-sway**, only blinking — see [Blinking](#blinking)
  (deferred, not attempted).
- **`load_full_frames` does no consistency checking** — it only validates
  that required files exist and share one pixel size; visual consistency
  (identity, framing, lighting) across your generated set is entirely your
  responsibility, unlike overlay mode where a single shared `face.png`
  makes drift impossible by construction. See
  [Using AI-generated / photoreal art](#using-ai-generated--photoreal-art).

## Roadmap

- [x] Phase 0/1 — pipeline proof + amplitude-only MVP
- [x] Phase 2a — real viseme timing via Rhubarb Lip Sync (opt-in `RhubarbVisemeVideoGenerator`)
- [x] Phase 2b — blinking + idle heartbeat (keeps blinking between agent turns)
- [x] Phase 3 — pip packaging (`default_assets_dir()`, packaged default art, `py.typed`)
- [x] Photoreal/full-frame art support (`AvatarAssets.load_full_frames`) for
      AI-generated identity-consistent images, alongside the original
      overlay-compositing convention
- [ ] Phase 4 — demo video, community distribution
- [ ] fast-follow — dedicated G/H viseme art; verify a safe `AgentSession`
      hook to auto-wire known TTS transcript text into rhubarb's `-d` flag;
      idle head-sway

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
