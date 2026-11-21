"""Game profile (Stage 0): projection, cell size, palette, outline, directions, timing."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import paths

PROJECTIONS = ("side", "topdown_34", "iso_2to1")
OUTLINES = ("none", "dark_1px", "selout")



@dataclass
class GameProfile:
    name: str
    projection: str = "side"
    cell_size: int = 64
    sprite_height_px: int = 48
    palette: list[str] | int = 16          # hex list = locked master palette; int = size N
    outline: str = "none"
    light_dir: str = "top_left"
    directions: int = 8
    mirror_allowed: bool = True
    default_frames: int = 12
    fps_per_action: dict[str, int] = field(default_factory=lambda: {"idle": 8, "walk": 12, "run": 14, "attack": 12})
    pixel_size: int | None = None          # manual grid override (source px per art px)
    despill: str = "all"                   # all (default, Ronan 2026-11-20: video tints outlines green) | edge (rule 11)

    def __post_init__(self):
        if self.projection not in PROJECTIONS:
            raise ValueError(f"projection must be one of {PROJECTIONS}")
        if self.outline not in OUTLINES:
            raise ValueError(f"outline must be one of {OUTLINES}")
        if self.directions not in (4, 8):
            raise ValueError("directions must be 4 or 8")

    @property
    def palette_size(self) -> int:
        return len(self.palette) if isinstance(self.palette, list) else int(self.palette)

    @property
    def locked_palette(self) -> list[str] | None:
        return self.palette if isinstance(self.palette, list) else None

    def fps(self, action: str) -> int:
        return self.fps_per_action.get(action, 12)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, path: Path) -> "GameProfile":
        return cls(**json.loads(Path(path).read_text()))


def list_all(profiles_dir: Path | None = None) -> list[str]:
    d = Path(profiles_dir) if profiles_dir else paths.profiles()
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def resolve(name_or_path: str | None, profiles_dir: Path | None = None) -> GameProfile:
    """Load a profile by file path or by name from profiles/; default profile when None."""
    if not name_or_path or name_or_path == "default" and not (
            (Path(profiles_dir) if profiles_dir else paths.profiles()) / "default.json").exists():
        return GameProfile(name="default")          # the built-in one `profile list` shows
    p = Path(name_or_path)
    if p.suffix == ".json" and p.exists():
        return GameProfile.load(p)
    p = (Path(profiles_dir) if profiles_dir else paths.profiles()) / f"{name_or_path}.json"
    if not p.exists():
        raise FileNotFoundError(f"no profile '{name_or_path}' (looked in {p.parent})")
    return GameProfile.load(p)
