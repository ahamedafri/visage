# Changelog

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
