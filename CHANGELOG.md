# Changelog

## 0.1.0 — 2026-09-25

First tagged release. Everything below was built, tested, and (where noted)
verified against real infrastructure before this tag — nothing here is
aspirational.

- **v1 — amplitude-only lip-sync** (`ImageAvatarVideoGenerator`): the mouth
  toggles open/closed based on TTS audio loudness. Minimal latency (true
  per-frame streaming). Verified against the real
  `livekit.agents.voice.avatar.VideoGenerator` ABC (`livekit-agents==1.8.1`),
  modeled on `livekit-plugins-bithuman`'s reference implementation.
- **Phase 2a — real viseme timing** (`RhubarbVisemeVideoGenerator`, opt-in):
  buffers each utterance and runs it through
  [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) for
  accurate per-phoneme mouth shapes. Trades latency for accuracy (see
  README). Falls back to amplitude-only automatically if the `rhubarb`
  binary is missing or a given utterance's invocation fails/times out.
- **Phase 2b — blinking + idle heartbeat**: both generators blink
  periodically (`face_blink.png`), including between agent turns via a
  self-paced background task — not just while actively speaking.
- **Audio resampling + channel normalization** (fixes a silent correctness
  bug present in early development): pushed frames whose sample rate or
  channel count differ from the generator's configured
  `audio_sample_rate`/`audio_channels` are normalized (rate via LiveKit's
  SoX-backed `rtc.AudioResampler`, mono ↔ stereo via numpy) instead of
  being passed through and playing back at the wrong pitch/speed with only
  a warning. Flushed at each `AudioSegmentEnd` so utterance tails aren't
  lost, reset on interruption.
- **`background=(r, g, b)`** option on both `AvatarAssets.load` and
  `load_full_frames` to composite a transparent canvas onto a solid color
  (published video is RGB24, so transparency otherwise renders black).
- **Dedicated G/H viseme art**: `Viseme.G` (upper teeth on lower lip, F/V)
  and `Viseme.H` (raised tongue, L) are real enum members with their own
  placeholder shapes.
- **Photoreal/full-frame art support** (`AvatarAssets.load_full_frames`): a
  second asset-loading convention, alongside overlay compositing
  (`face.png` + transparent `mouth_<state>.png` overlays), for complete
  already-rendered images — e.g. from an identity-consistent AI photo
  generator (Ideogram Character, FLUX PuLID, InstantID/IP-Adapter-FaceID)
  taking one reference photo and producing one full image per required
  mouth shape. No compositing step, so no changes needed to either video
  generator. Per-state optional blink art, falling back to the non-blink
  frame for states without one.
- **Packaging**: default placeholder art ships inside the installed
  package (`visage.default_assets_dir()`), `py.typed` marker, version
  resolved dynamically from installed package metadata. A wheel built from
  this release installs cleanly into a fresh, isolated virtualenv with no
  repo checkout, and the packaged default assets are present and loadable
  from it — verified, not assumed.
- **GitHub Actions CI**: pytest on a Linux + Windows × Python 3.10/3.13
  matrix, plus a job that builds the wheel and installs it into a fresh
  venv.
- **Verified live against a real LiveKit Cloud room**
  (`scripts/live_test.py`): joins a fresh room with two participants — the
  avatar using the exact `AvatarRunner` wiring an agent would, and a
  viewer that subscribes and counts frames like a browser would — so
  pass/fail is based on what actually came back through the server. Run
  result: 151/162 expected video frames received at 512×512, real audio,
  ~1.8s first-frame latency (one-time per-session publish cost).
- **GitHub presentation**: logo, README demo images/GIFs (all generated
  from the real generator classes via `scripts/render_preview.py`, not
  mockups), CI/license/python badges, CONTRIBUTING.md, issue/PR templates.
- 37 tests total, none requiring the real `rhubarb` binary or a live
  LiveKit room.

**Known limitations** (see README for details): audio is resampled rather
than passed through when rates differ (extra CPU work, only mono↔stereo
channel conversion supported); published video has no alpha channel
(transparent canvases render black unless `background=` is set);
`open_threshold`/`amplitude_fallback_threshold` need per-voice tuning;
Rhubarb mode adds per-utterance latency; no idle head-sway (blinking only);
`load_full_frames` doesn't verify visual consistency across a generated
image set. **Not yet exercised live**: a full `AgentSession` with real
LLM/TTS behind it, and Rhubarb mode with the real `rhubarb` binary.
