"""Locating the default (placeholder) asset set shipped inside the package.

Packaged as `visage/default_assets/*.png` (see `pyproject.toml`'s
`[tool.setuptools.package-data]`) so `pip install visage` gives you a
working default face without needing to clone the repo or run
`scripts/generate_placeholder_assets.py` yourself. That script is still
there for regenerating/customizing the placeholder art during development —
it writes into this same package directory.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def default_assets_dir() -> Path:
    """Directory containing the packaged default face/mouth placeholder art.

    Pass this straight to `AvatarAssets.load(...)`.
    """
    return Path(str(files("visage") / "default_assets"))
