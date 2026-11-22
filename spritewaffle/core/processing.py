"""Read-only freshness checks for processed action frames and their source clips."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..export import receipt
from ..frames import video
from ..prompts import styles
from . import fsutil, job_palette
from .profile import GameProfile, resolve


def _read(path: Path) -> dict:
    data = json.loads(fsutil.read_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return data


def extracted_source(directory: Path) -> tuple[Path, str | None] | None:
    report = directory / "extracted" / "extraction_report.json"
    try:
        source = _read(report).get("clip_source")
    except (FileNotFoundError, ValueError):
        return None
    if isinstance(source, dict):
        name, digest = source.get("name"), source.get("sha256")
        if (isinstance(name, str) and re.fullmatch(r"raw\.[A-Za-z0-9]+", name) and
                (source.get("incomplete") is True or
                 (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)))):
            return directory / name, digest
    return None


def changed_clip(directory: Path) -> Path | None:
    source = extracted_source(directory)
    if source and (source[1] is None or receipt.digest(source[0]) != source[1]):
        return source[0]
    return None


def require_extracted(directory: Path) -> None:
    if raw := changed_clip(directory):
        raise RuntimeError(f"{raw.name} changed, is missing, or was not fully decoded. Re-process frames from the saved clip.")


def clip_to_decode(directory: Path) -> Path | None:
    """Reselect from a replaced clip, and establish a source record for legacy MP4s."""
    source = changed_clip(directory)
    legacy = directory / "raw.mp4"
    if source is None and extracted_source(directory) is None and legacy.is_file():
        return legacy
    return source


def selection(directory: Path) -> tuple[dict, bool, dict[int, Path]]:
    report = _read(directory / "selection_report.json")
    sets = {n: [row["source"] for row in rows] for n, rows in report["sets"].items()}
    frames = video.list_frames(directory / "extracted")
    paths = {i: frames[i] for i in sorted({i for indices in sets.values() for i in indices})}
    return sets, report["loop"], paths


def snapshot(job, profile: GameProfile, directory: Path, inputs: tuple, override: int | None, palette=None) -> dict:
    sets, loop, paths = inputs
    style = styles.get(styles.of_job(job))
    settings = {"selection": sets, "loop": loop, "style": style["name"]}
    if style["post"] == "pixel":
        if palette is None:
            fixed = None if override else job_palette.current(job, profile)
            palette = override or (fixed["colours"] if fixed else profile.palette_size)
        settings["palette"] = [c.lower() for c in palette] if isinstance(palette, list) else palette
    files = list(paths.values())
    if source := extracted_source(directory):
        files.append(source[0])
    return receipt.snapshot(job.root, files, settings)


def status(job, profile: GameProfile | None, facing: str, action: str) -> dict:
    pixel_report = job.root / "04_pixel" / facing / action / "pixel_report.json"
    try:
        record = _read(pixel_report).get("processing")
    except FileNotFoundError:
        return {"status": "untracked"}
    except ValueError:
        return {"status": "incomplete", "step": "pixelize"}
    if not isinstance(record, dict) or record.get("version") != 1:
        return {"status": "untracked"}
    if record.get("incomplete"):
        return {"status": "incomplete", "step": "pixelize"}
    directory = job.root / "03_actions" / facing / action
    if raw := changed_clip(directory):
        return {"status": "stale", "step": "extract", "changed_inputs": [raw.relative_to(job.root).as_posix()],
                "settings_changed": []}
    try:
        previous = record["inputs"]
        # Character exporters can be called with a standalone FPS callback and no profile.
        # In that case an explicit processing profile's palette cannot be resolved from the callback.
        palette = previous["settings"].get("palette") if profile is None and record.get("profile_palette") else None
        current = snapshot(job, profile or resolve(None), directory, selection(directory), record.get("palette_override"), palette)
        changes = receipt.input_changes(record["inputs"], current)
    except (FileNotFoundError, ValueError, IndexError, KeyError, AttributeError, TypeError):
        return {"status": "incomplete", "step": "pixelize"}
    if any(changes.values()):
        return {"status": "stale", "step": "pixelize", **changes}
    return {"status": "current"}


def require_current(result: dict, clip: str) -> None:
    if result["status"] in ("stale", "incomplete"):
        raise RuntimeError(f"Processed frames for {clip} need updating. Re-process frames from the saved clip before exporting.")
