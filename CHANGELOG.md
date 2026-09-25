# Changelog

## Unreleased

- **Photoreal/full-frame art support** (`AvatarAssets.load_full_frames`): a
  second asset-loading convention, alongside the original overlay
  compositing (`face.png` + transparent `mouth_<state>.png` overlays), for
  complete already-rendered images — e.g. from an identity-consistent AI
  photo generator (Ideogram Character, FLUX PuLID, InstantID/IP-Adapter-FaceID)
  taking one reference photo and producing one full image per required mouth
  shape. No compositing step, so no changes needed to either video
  generator — both loading paths produce an identical `AvatarAssets`. Per-state
  optional blink art (`full_<state>_blink.png`), falling back to the non-blink
  frame for states without one. `RhubarbVisemeVideoGenerator`'s existing
  fail-fast validation now raises a clear, actionable `ValueError` (was a bare
  `KeyError`) if a photoreal set is missing the `MouthState` coverage its
  amplitude-fallback path needs.
- 6 new tests (`tests/test_assets_full_frames.py`), all synthetic fixtures,
  no real photos needed.
- **Audio resampling + channel normalization** (fixes a silent correctness
  bug): pushed frames whose sample rate or channel count differ from the
  generator's configured `audio_sample_rate`/`audio_channels` are now
  normalized (rate via LiveKit's SoX-backed `rtc.AudioResampler`, mono ↔ stereo
  via numpy) instead of being passed through and playing back at the wrong
  pitch/speed with only a warning. The resampler is flushed at each
  `AudioSegmentEnd` so utterance tails aren't lost, and reset on interruption.
- **`background=(r, g, b)`** option on both `AvatarAssets.load` and
  `load_full_frames` to composite a transparent canvas onto a solid color
  (published video is RGB24, so transparency otherwise rendered black).
- **Dedicated G/H viseme art**: `Viseme.G` (upper teeth on lower lip, F/V)
  and `Viseme.H` (raised tongue, L) are now real enum members with their own
  placeholder shapes, instead of being mapped to the nearest basic shape.
  Custom overlay/full-frame asset sets used with `RhubarbVisemeVideoGenerator`
  now need `mouth_g.png`/`mouth_h.png` (or `full_g.png`/`full_h.png`).
- **GitHub Actions CI**: pytest on a Linux + Windows × Python 3.10/3.13
  matrix, plus a job that builds the wheel and installs it into a fresh venv
  to prove the packaged default art is present and loadable.
- **`scripts/live_test.py`**: end-to-end verification against a real LiveKit
  server — no LLM/TTS needed. Joins a fresh room with two participants (the
  avatar, using the exact `AvatarRunner` wiring an agent would; a viewer that
  subscribes and counts frames like a browser would) so pass/fail is based
  on what actually came back through the server. Run against LiveKit Cloud:
  151/162 expected video frames received at 512×512, real audio, ~1.8s
  first-frame latency.
- 37 tests total.

## 0.1.0

Initial local release — everything built and verified so far, not yet published anywhere.

- **v1 — amplitude-only lip-sync** (`ImageAvatarVideoGenerator`): the mouth toggles
  open/closed based on TTS audio loudness. Minimal latency (true per-frame
  streaming). Verified against the real `livekit.agents.voice.avatar.VideoGenerator`
  ABC (`livekit-agents==1.8.1`), modeled on `livekit-plugins-bithuman`'s reference
  implementation.
- **Phase 2a — real viseme timing** (`RhubarbVisemeVideoGenerator`, opt-in): buffers
  each utterance and runs it through [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync)
  for accurate per-phoneme mouth shapes. Trades latency for accuracy (see README).
  Falls back to amplitude-only automatically if the `rhubarb` binary is missing or a
  given utterance's invocation fails/times out.
- **Phase 2b — blinking + idle heartbeat**: both generators blink periodically
  (`face_blink.png`), including between agent turns via a self-paced background
  task — not just while actively speaking.
- Packaging: default placeholder art now ships inside the installed package
  (`visage.default_assets_dir()`), `py.typed` marker added, version resolved
  dynamically from installed package metadata.
- 20 unit tests (WAV I/O, Rhubarb JSON parsing, viseme replay pacing, amplitude
  fallback, blink timing, idle-heartbeat state transitions) — none require the
  real `rhubarb` binary. Two smoke-test scripts for manual end-to-end checks
  (`scripts/smoke_test.py` synthetic-only, `scripts/smoke_test_rhubarb.py` needs
  the real binary + a real speech clip).
- Verified: a wheel built from this version installs cleanly into a fresh,
  isolated virtualenv with no repo checkout, and the packaged default assets are
  actually present and loadable from it.

**Known limitations** (see README for details): no audio resampling, RGB24 video
means a transparent background renders black, G/H extended visemes fall back to
the nearest basic shape, no idle head-sway (blinking only).
