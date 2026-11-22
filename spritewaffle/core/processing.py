"""Read-only freshness checks for processed action frames and their source clips."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..export import receipt
from ..frames import video
from ..prompts import styles
from . import fsutil, job_palette, motion
from .profile import GameProfile, resolve


def _read(path: Path) -> dict:
    data = json.loads(fsutil.read_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return data


def pixel_report(job, facing: str, action: str) -> dict:
    for name in (facing, action):
        if not isinstance(name, str) or name in ("", ".", "..") or any(c in name for c in "/\\:\0"):
            raise ValueError("Facing and action must each be a single name.")
    path = job.root / "04_pixel" / facing / action / "pixel_report.json"
    if not path.resolve().is_relative_to(job.root.resolve()):
        raise ValueError("The processing report must stay inside the job.")
    try:
        return _read(path)
    except FileNotFoundError:
        return {}


def active_sets(directory: Path) -> set[str] | None:
    """The sets from the latest completed processing run, or None for legacy frame folders."""
    try:
        report = _read(directory / "pixel_report.json")
    except (FileNotFoundError, ValueError):
        return None
    tracked = report.get("processing")
    sets = report.get("sets")
    if isinstance(tracked, dict) and tracked.get("version") == 1 and not tracked.get("incomplete") and isinstance(sets, dict):
        return {f"{n}f" for n in sets if n.isdecimal()}
    return None


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


def _effective_palette(job, profile: GameProfile, override=None, palette=None):
    if palette is None:
        fixed = None if override else job_palette.current(job, profile)
        palette = override or (fixed["colours"] if fixed else profile.palette_size)
    return [c.lower() for c in palette] if isinstance(palette, list) else palette


def snapshot(job, profile: GameProfile, directory: Path, inputs: tuple, override: int | None, palette=None) -> dict:
    sets, loop, paths = inputs
    style = styles.get(styles.of_job(job))
    settings = {"selection": sets, "loop": loop, "style": style["name"]}
    if style["post"] == "pixel":
        settings["palette"] = _effective_palette(job, profile, override, palette)
    files = list(paths.values())
    if source := extracted_source(directory):
        files.append(source[0])
    return receipt.snapshot(job.root, files, settings)


def flow_snapshot(job, profile: GameProfile, facing: str, guide: dict, palette=None) -> dict:
    settings = {"palette": _effective_palette(job, profile, palette=palette), "style": styles.of_job(job),
                "motion_approved": guide["status"] == "approved",
                "facing_approved": job.read_meta()["stages"].get("facings", {}).get("status") == "approved"}
    return receipt.snapshot(job.root, [job.root / "02_facings" / f"{facing}.png", Path(guide["clip"])], settings)


def mirror_inputs(job, source: str, action: str) -> tuple[dict, dict[str, list[Path]], Path]:
    report = pixel_report(job, source, action)
    if not report:
        raise FileNotFoundError(f"{action} {source} is not pixelized yet.")
    sets = report["sets"]
    if not all(n.isdecimal() for n in sets):
        raise ValueError("Mirror source frame sets must be numbered.")
    directory = job.root / "04_pixel" / source / action
    frames = {n: video.colour_frames(directory / f"{n}f" / "frames") for n in sets}
    selection_path = job.root / "03_actions" / source / action / "selection_report.json"
    settings = {"sources": {n: info["sources"] for n, info in sets.items()},
                "palette": report["palette"], "cell": report.get("cell"), "style": report.get("style"),
                "grid": report.get("grid")}
    before = receipt.snapshot(job.root, [selection_path, *(path for paths in frames.values() for path in paths)], settings)
    return before, frames, selection_path


def validate_mirror(job, facing: str, action: str, source: str) -> None:
    seen = {facing}
    while isinstance(source, str) and source not in seen:
        seen.add(source)
        report = pixel_report(job, source, action)
        if report.get("method") != "mirror":
            return
        source = report.get("source")
    if not isinstance(source, str):
        raise ValueError("A mirrored action is missing a valid source facing.")
    raise ValueError(f"Mirroring {facing}/{action} from this source would create a cycle.")


def status(job, profile: GameProfile | None, facing: str, action: str, *, _seen=frozenset()) -> dict:
    try:
        report = pixel_report(job, facing, action)
    except ValueError:
        return {"status": "incomplete", "step": "pixelize"}
    record = report.get("processing")
    if not isinstance(record, dict) or record.get("version") != 1:
        return {"status": "untracked"}
    method = report.get("method")
    step = method if method in ("mirror", "flow") else "pixelize"
    result = {"step": step}
    if step == "mirror":
        result["source_facing"] = report.get("source")
    if record.get("incomplete") or facing in _seen:
        return {"status": "incomplete", **result}
    directory = job.root / "03_actions" / facing / action
    try:
        previous = record["inputs"]
        # Character exporters can be called with a standalone FPS callback and no profile.
        # In that case an explicit processing profile's palette cannot be resolved from the callback.
        palette = previous["settings"].get("palette") if profile is None and record.get("profile_palette") else None
        if step == "mirror":
            source = result["source_facing"]
            current, _, _ = mirror_inputs(job, source, action)
            if status(job, profile, source, action, _seen=_seen | {facing})["status"] in ("stale", "incomplete"):
                return {"status": "stale", **result, "source_needs_processing": True}
        elif step == "flow":
            guide = motion.get(report.get("motion"), job.root.parent.parent)
            current = flow_snapshot(job, profile or resolve(None), facing, guide, palette)
        else:
            if raw := changed_clip(directory):
                return {"status": "stale", "step": "extract", "changed_inputs": [raw.relative_to(job.root).as_posix()],
                        "settings_changed": []}
            current = snapshot(job, profile or resolve(None), directory, selection(directory), record.get("palette_override"), palette)
        changes = receipt.input_changes(previous, current)
    except (FileNotFoundError, ValueError, IndexError, KeyError, AttributeError, TypeError):
        return {"status": "incomplete", **result}
    if any(changes.values()):
        return {"status": "stale", **result, **changes}
    return {"status": "current"}


def require_current(result: dict, clip: str) -> None:
    if result["status"] in ("stale", "incomplete"):
        if result.get("step") == "mirror" and result.get("source_facing"):
            source = result["source_facing"] + "/" + clip.split("/", 1)[1]
            raise RuntimeError(f"Re-process {clip} from its mirrored source {source}. Update {source} first if needed.")
        if result.get("step") == "flow":
            raise RuntimeError(f"Re-process {clip} using its approved facing and motion-library clip before exporting.")
        raise RuntimeError(f"Processed frames for {clip} need updating. Re-process frames from the saved clip before exporting.")
