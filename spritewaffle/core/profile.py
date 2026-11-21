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
        if not 8 <= int(self.cell_size) <= 1024:
            raise ValueError("cell size must be 8-1024 px")
        if not 4 <= int(self.sprite_height_px) <= int(self.cell_size) - 2:
            raise ValueError(f"sprite height must be 4 to {int(self.cell_size) - 2} px (cell size minus a 1 px "
                             "margin top and bottom)")
        if not isinstance(self.palette, list) and not 2 <= int(self.palette) <= 256:
            raise ValueError("palette size must be 2-256 colours")
        if any(not 1 <= int(v) <= 60 for v in self.fps_per_action.values()):
            raise ValueError("fps must be 1-60")

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


EDITABLE = ("projection", "cell_size", "sprite_height_px", "palette", "outline", "directions",
            "mirror_allowed", "fps_per_action")


def save_named(name: str, fields: dict, profiles_dir: Path | None = None) -> GameProfile:
    """Create or update profiles/<name>.json from the editable fields (others kept)."""
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", name or ""):
        raise ValueError("profile name: lowercase letters, digits, - and _ (max 40)")
    if name == "default":
        raise ValueError("'default' is the built-in profile; save under another name")
    d = Path(profiles_dir) if profiles_dir else paths.profiles()
    p = d / f"{name}.json"
    base = asdict(GameProfile.load(p)) if p.exists() else asdict(GameProfile(name=name))
    for k in EDITABLE:
        if k in fields and fields[k] is not None:
            v = fields[k]
            if k in ("cell_size", "sprite_height_px", "directions"):
                v = int(v)
            elif k == "palette" and not isinstance(v, list):
                v = int(v)
            elif k == "mirror_allowed":
                v = bool(v)
            elif k == "fps_per_action":
                v = {str(a): int(f) for a, f in dict(v).items()}
            base[k] = v
    base["name"] = name
    prof = GameProfile(**base)                      # validates
    prof.save(p)
    return prof


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
