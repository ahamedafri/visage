"""Loading and compositing of avatar art assets.

Two loading conventions, both producing the same :class:`AvatarAssets`:

**Overlay mode** — :meth:`AvatarAssets.load` — for hand-drawn/vector art. A
folder containing:
  - ``face.png``   — the base face/head, RGBA, defines the canvas size
  - ``face_blink.png`` — OPTIONAL, same canvas size as ``face.png``, eyes
    closed. If present, enables blinking (see ``blink.py``); if absent,
    blinking is silently a no-op (the normal face is always used) rather
    than raising.
  - ``mouth_<state>.png`` — one RGBA overlay per mouth-shape enum member
    requested (:class:`MouthState` and/or :class:`Viseme`), same canvas
    size as ``face.png``, transparent everywhere except the mouth

v1 (amplitude-only lip-sync, see ``video_generator.py``) only needs
``mouth_closed.png`` and ``mouth_open.png`` (:class:`MouthState`).
Phase 2 (real viseme timing, see ``rhubarb_video_generator.py``) adds
``mouth_x.png``..``mouth_f.png`` (:class:`Viseme`, matching Rhubarb Lip
Sync's basic Preston Blair-style codes). A single :class:`AvatarAssets`
instance can hold both sets loaded together — that's what lets the Rhubarb
generator fall back to amplitude mode using the *same* loaded assets.

**Full-frame mode** — :meth:`AvatarAssets.load_full_frames` — for
already-composed photos (e.g. from an AI identity-consistent photo
generator), which can't produce an alignable transparent mouth-only
overlay. See its docstring and the README's "Using AI-generated /
photoreal art" section.

`AvatarAssets` itself doesn't care which loading path built it — both just
populate the same internal ``dict[Enum, bytes]`` shape, so
`ImageAvatarVideoGenerator`/`RhubarbVisemeVideoGenerator` work unchanged
either way.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from livekit import rtc
from PIL import Image


class MouthState(str, Enum):
    """Named mouth shapes for amplitude-only lip-sync (v1)."""

    CLOSED = "closed"
    OPEN = "open"


class Viseme(str, Enum):
    """Preston Blair-style viseme codes, matching Rhubarb Lip Sync's JSON
    ``mouthCues[].value`` output (basic set only — no dedicated art for the
    optional extended G/H shapes; see ``rhubarb.py`` for how those map onto
    these instead). X = idle/rest/silence."""

    X = "x"
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    E = "e"
    F = "f"


class AvatarAssets:
    """Pre-rendered per-mouth-shape [+ blink] frames, ready to hand to
    ``rtc.VideoFrame``. Build one via :meth:`load` (overlay-composited,
    hand-drawn/vector art) or :meth:`load_full_frames` (complete
    already-rendered images, e.g. AI photo generator output) — both
    produce an identical, format-agnostic instance."""

    def __init__(
        self,
        width: int,
        height: int,
        frames_rgb: dict[Enum, bytes],
        frames_rgb_blink: dict[Enum, bytes] | None = None,
    ) -> None:
        self._width = width
        self._height = height
        self._frames_rgb = frames_rgb
        self._frames_rgb_blink = frames_rgb_blink

    @property
    def resolution(self) -> tuple[int, int]:
        return self._width, self._height

    @property
    def has_blink_art(self) -> bool:
        return self._frames_rgb_blink is not None

    @classmethod
    def load(
        cls,
        assets_dir: str | Path,
        states: tuple[Enum, ...] = (MouthState.CLOSED, MouthState.OPEN),
    ) -> "AvatarAssets":
        assets_dir = Path(assets_dir)
        face_path = assets_dir / "face.png"
        if not face_path.exists():
            raise FileNotFoundError(
                f"missing {face_path} — an asset folder needs a face.png "
                "(RGBA) plus one mouth_<state>.png per requested mouth shape"
            )

        face = Image.open(face_path).convert("RGBA")
        width, height = face.size

        blink_face_path = assets_dir / "face_blink.png"
        blink_face: Image.Image | None = None
        if blink_face_path.exists():
            blink_face = Image.open(blink_face_path).convert("RGBA")
            if blink_face.size != face.size:
                raise ValueError(
                    f"{blink_face_path} is {blink_face.size}, but face.png is "
                    f"{face.size} — face_blink.png must match face.png's size exactly"
                )

        frames_rgb: dict[Enum, bytes] = {}
        frames_rgb_blink: dict[Enum, bytes] | None = {} if blink_face is not None else None
        for state in states:
            mouth_path = assets_dir / f"mouth_{state.value}.png"
            if not mouth_path.exists():
                raise FileNotFoundError(
                    f"missing {mouth_path} — expected one mouth image per requested "
                    f"shape ({', '.join(s.value for s in states)})"
                )
            mouth = Image.open(mouth_path).convert("RGBA")
            if mouth.size != face.size:
                raise ValueError(
                    f"{mouth_path} is {mouth.size}, but face.png is {face.size} — "
                    "mouth overlays must match the face canvas size exactly"
                )
            frames_rgb[state] = Image.alpha_composite(face, mouth).convert("RGB").tobytes()
            if blink_face is not None:
                frames_rgb_blink[state] = (
                    Image.alpha_composite(blink_face, mouth).convert("RGB").tobytes()
                )

        return cls(width, height, frames_rgb, frames_rgb_blink)

    @classmethod
    def load_full_frames(
        cls,
        assets_dir: str | Path,
        states: tuple[Enum, ...] = (MouthState.CLOSED, MouthState.OPEN),
    ) -> "AvatarAssets":
        """Load a folder of COMPLETE, already-rendered face images — one
        whole image per requested state, used directly as that state's
        frame with no compositing step at all.

        For art from identity-consistent AI photo generators (Ideogram
        Character, FLUX PuLID, InstantID/IP-Adapter-FaceID, etc.) that only
        ever output a whole composed photo per generation — never an
        alignable, transparent mouth-only overlay. If your art IS separate
        base+overlay layers (hand-drawn/vector), use :meth:`load` instead.

        Expects, per requested state:
          - ``full_<state>.png`` — required, one whole face image
          - ``full_<state>_blink.png`` — OPTIONAL, same size, eyes closed.
            Missing for a given state just means no blink animation for
            that state's frames (falls back to the non-blink image) — you
            do NOT need the full state x blink cross product.

        All ``full_<state>.png`` images across the requested states must be
        exactly the same pixel size as each other — there's no single base
        image to define canvas size, and no compositing step to hide a
        mismatch, so this is checked explicitly.

        Unlike :meth:`load`, images are converted straight to RGB — no
        alpha compositing, since there's no overlay. A source PNG with
        semi-transparent pixels will NOT be blended against any
        background; export fully-opaque images.
        """
        assets_dir = Path(assets_dir)
        if not states:
            raise ValueError("load_full_frames requires at least one state to load")

        frames_rgb: dict[Enum, bytes] = {}
        size: tuple[int, int] | None = None
        first_path: Path | None = None

        for state in states:
            full_path = assets_dir / f"full_{state.value}.png"
            if not full_path.exists():
                raise FileNotFoundError(
                    f"missing {full_path} — a full-frame asset folder needs one "
                    "full_<state>.png (a complete, already-rendered face image, "
                    "no compositing) per requested state "
                    f"({', '.join(s.value for s in states)})"
                )
            img = Image.open(full_path).convert("RGB")
            if size is None:
                size, first_path = img.size, full_path
            elif img.size != size:
                raise ValueError(
                    f"{full_path} is {img.size}, but {first_path} is {size} — "
                    "all full_<state>.png images must be the same size as each "
                    "other (full-frame mode has no compositing step to hide a "
                    "mismatch)"
                )
            frames_rgb[state] = img.tobytes()

        width, height = size  # type: ignore[misc]

        blink_paths = {state: assets_dir / f"full_{state.value}_blink.png" for state in states}
        frames_rgb_blink: dict[Enum, bytes] | None = None
        if any(p.exists() for p in blink_paths.values()):
            frames_rgb_blink = {}
            for state in states:
                blink_path = blink_paths[state]
                if not blink_path.exists():
                    # optional per-state blink art — missing = fall back to
                    # the non-blink frame for this state, rather than
                    # requiring every state to have its own blink variant
                    frames_rgb_blink[state] = frames_rgb[state]
                    continue
                blink_img = Image.open(blink_path).convert("RGB")
                if blink_img.size != (width, height):
                    raise ValueError(
                        f"{blink_path} is {blink_img.size}, but "
                        f"full_{state.value}.png is {(width, height)} — "
                        "full_<state>_blink.png must match its base image's "
                        "size exactly"
                    )
                frames_rgb_blink[state] = blink_img.tobytes()

        return cls(width, height, frames_rgb, frames_rgb_blink)

    def video_frame(self, state: Enum, *, blinking: bool = False) -> rtc.VideoFrame:
        """A fresh ``rtc.VideoFrame`` for the given mouth shape.

        ``blinking=True`` uses the eyes-closed face variant if one was
        loaded (``face_blink.png`` present); otherwise it's silently
        ignored and the normal face is used — no ``face_blink.png`` simply
        means no blinking, not an error.

        Built fresh from cached bytes each call (cheap — no re-compositing)
        so callers never share a mutable frame instance across pushes.
        """
        frames = self._frames_rgb_blink if (blinking and self._frames_rgb_blink is not None) else self._frames_rgb
        data = frames.get(state)
        if data is None:
            raise KeyError(f"no frame loaded for mouth shape {state!r}")
        return rtc.VideoFrame(
            width=self._width,
            height=self._height,
            type=rtc.VideoBufferType.RGB24,
            data=data,
        )
