from importlib.metadata import PackageNotFoundError, version as _version

from .assets import AvatarAssets, MouthState, Viseme
from .paths import default_assets_dir
from .rhubarb import RhubarbError, RhubarbNotFoundError, find_rhubarb_executable
from .rhubarb_video_generator import RhubarbVisemeVideoGenerator
from .video_generator import ImageAvatarVideoGenerator

__all__ = [
    "AvatarAssets",
    "MouthState",
    "Viseme",
    "ImageAvatarVideoGenerator",
    "RhubarbVisemeVideoGenerator",
    "RhubarbError",
    "RhubarbNotFoundError",
    "find_rhubarb_executable",
    "default_assets_dir",
]

try:
    __version__ = _version("visage")
except PackageNotFoundError:
    # not installed (e.g. running straight from a source checkout without
    # `pip install -e .`) — not expected in normal use, but don't crash import
    __version__ = "0.0.0+unknown"
