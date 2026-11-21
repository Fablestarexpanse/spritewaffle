"""Camera profile: how a project's assets are seen and lit (one per project, overridable per asset).

Project = a jobs folder. Its camera profile lives in <jobs>/project.json; an asset's override in
job.json inputs.camera (only the fields that differ). Missing everywhere -> the values the job's
GameProfile already implies (projection -> elevation, sprite height -> scale, light_dir word), so
an asset made before camera profiles existed is described exactly as it was made, and prompts
don't change (plan R3, docs/PLAN_DIRECTIONAL.md).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .profile import GameProfile, resolve

SCHEMA_VERSION = 1
PROJECTION_ELEVATION = {"side": 0.0, "topdown_34": 45.0, "iso_2to1": 30.0}
# light_dir word -> (yaw, elevation): yaw in the unit convention (0 = from the camera's side,
# clockwise seen from above), the direction the light comes FROM
LIGHT_WORDS = {"top_left": (45.0, 50.0), "top_right": (315.0, 50.0), "top": (0.0, 70.0), "front": (0.0, 30.0)}
BACKGROUNDS = ("green", "black", "transparent")


@dataclass
class CameraProfile:
    camera_elevation_degrees: float = 0.0
    framing: float = 0.45               # character height as a fraction of the generated frame
    character_scale: int = 48           # target character height in px at final size
    light_yaw: float = 45.0
    light_elevation: float = 50.0
    background_mode: str = "green"      # what generation keys out (generation itself always draws green)
    canvas_border_px: int = 2           # transparent border at final size (used by the align step)
    style_notes: str = ""

    def __post_init__(self):
        checks = [(-10 <= float(self.camera_elevation_degrees) <= 90, "camera_elevation_degrees must be -10..90"),
                  (0.1 <= float(self.framing) <= 0.9, "framing must be 0.1..0.9"),
                  (4 <= int(self.character_scale) <= 1024, "character_scale must be 4..1024 px"),
                  (0 <= float(self.light_yaw) <= 360, "light_yaw must be 0..360"),
                  (0 <= float(self.light_elevation) <= 90, "light_elevation must be 0..90"),
                  (self.background_mode in BACKGROUNDS, f"background_mode must be one of {BACKGROUNDS}"),
                  (0 <= int(self.canvas_border_px) <= 64, "canvas_border_px must be 0..64")]
        for ok, msg in checks:
            if not ok:
                raise ValueError(msg)


FIELDS = tuple(f.name for f in fields(CameraProfile))


def clean(d: dict | None) -> dict:
    """Only known fields; unknown keys are refused so typos don't silently do nothing."""
    d = dict(d or {})
    bad = sorted(set(d) - set(FIELDS))
    if bad:
        raise ValueError(f"unknown camera fields {bad}; known: {list(FIELDS)}")
    return d


def implied(profile: GameProfile) -> CameraProfile:
    yaw, elev = LIGHT_WORDS.get(profile.light_dir, LIGHT_WORDS["top_left"])
    return CameraProfile(camera_elevation_degrees=PROJECTION_ELEVATION.get(profile.projection, 0.0),
                         character_scale=int(profile.sprite_height_px), light_yaw=yaw, light_elevation=elev)


def project_path(base: Path) -> Path:
    return Path(base) / "project.json"


def project(base: Path) -> dict:
    """{"schema_version", "id", "camera": {...} | None}. Missing file -> id = folder name."""
    p = project_path(base)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"schema_version": d.get("schema_version", SCHEMA_VERSION), "id": d.get("id") or Path(base).resolve().name,
            "camera": d.get("camera")}


def set_project(base: Path, camera: dict | None, project_id: str | None = None) -> dict:
    """Set (or with None clear) the project's camera profile. Fields are validated."""
    cur = project(base)
    cam = clean(camera) if camera is not None else None
    if cam is not None:
        CameraProfile(**cam)                                   # validate the given values
    d = {"schema_version": SCHEMA_VERSION, "id": project_id or cur["id"], "camera": cam}
    project_path(base).parent.mkdir(parents=True, exist_ok=True)
    project_path(base).write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d


def job_profile(job) -> GameProfile:
    try:
        return resolve(job.read_meta()["inputs"].get("profile"))
    except (FileNotFoundError, ValueError):
        return GameProfile(name="default")


def effective(job, profile: GameProfile | None = None) -> tuple[CameraProfile, str]:
    """(camera profile, source): source = 'asset' | 'project' | 'implied'."""
    profile = profile or job_profile(job)
    base = job.root.parent.parent
    proj = project(base)["camera"] or {}
    over = (job.read_meta()["inputs"].get("camera") or {})
    vals = asdict(implied(profile)) | clean(proj) | clean(over)
    return CameraProfile(**vals), ("asset" if over else "project" if proj else "implied")


def prompt_sentence(job, profile: GameProfile | None = None) -> str:
    """Extra prompt text, only for what the GameProfile doesn't already say (plan R3): a camera
    elevation different from the projection's, a different framing, style notes. '' otherwise."""
    profile = profile or job_profile(job)
    cam, source = effective(job, profile)
    if source == "implied":
        return ""
    imp = implied(profile)
    out = []
    if abs(cam.camera_elevation_degrees - imp.camera_elevation_degrees) > 0.5:
        e = cam.camera_elevation_degrees
        out.append(f"The camera looks down at the character from {e:g} degrees above the horizon." if e > 0.5
                   else "The camera is at eye level with the character.")
    if abs(cam.framing - imp.framing) > 0.005:
        out.append(f"The character occupies about {round(cam.framing * 100)} percent of the image height.")
    if cam.style_notes.strip():
        out.append(cam.style_notes.strip().rstrip(".") + ".")
    return " ".join(out)


def character_height(job, profile: GameProfile) -> int:
    """Target sprite height for the pixel stage: the camera profile's character_scale when one is
    set for this asset or project (and it fits the cell), else the GameProfile's sprite height."""
    cam, source = effective(job, profile)
    if source != "implied" and 4 <= int(cam.character_scale) <= int(profile.cell_size) - 2:
        return int(cam.character_scale)
    return int(profile.sprite_height_px)


def snapshot(job, profile: GameProfile | None = None) -> dict:
    cam, source = effective(job, profile)
    return {"source": source, **asdict(cam)}


def set_asset(job, camera: dict | None) -> dict:
    """Set (or with None clear) one asset's override; validated against the merged result."""
    cam = clean(camera) if camera else None
    if cam:
        CameraProfile(**(asdict(effective(job)[0]) | cam))
    with job.mutate() as meta:
        if cam:
            meta["inputs"]["camera"] = cam
        else:
            meta["inputs"].pop("camera", None)
    return snapshot(job)
