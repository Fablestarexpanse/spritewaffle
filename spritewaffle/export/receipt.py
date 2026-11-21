"""Track the exact inputs and output files of a completed export."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ..core import fsutil


def _digest(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except FileNotFoundError:
        return None
    except OSError:
        if path.is_dir():
            return None
        raise


def snapshot(root: Path, files, settings: dict) -> dict:
    return {
        "settings": settings,
        "files": {Path(os.path.relpath(p, root)).as_posix(): digest for p in files
                  if (digest := _digest(p)) is not None},
    }


def load(path: Path) -> dict | None:
    try:
        record = json.loads(fsutil.read_text(path))
    except (FileNotFoundError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("version") != 1:
        return None
    if record.get("incomplete") is True:
        return record
    previous, outputs = record.get("inputs"), record.get("outputs")
    if (not isinstance(previous, dict) or not isinstance(previous.get("files"), dict) or
            not isinstance(previous.get("settings"), dict) or not isinstance(outputs, dict) or
            not outputs or not all(isinstance(digest, str) for digest in outputs.values())):
        return None
    return record


def incomplete(path: Path) -> None:
    fsutil.write_text(path, json.dumps({"version": 1, "incomplete": True}))


def save(path: Path, out_dir: Path, inputs: dict, files, *, options: dict | None = None) -> None:
    outputs = {file.relative_to(out_dir).as_posix(): _digest(file) for file in files}
    if not outputs or any(digest is None for digest in outputs.values()):
        raise RuntimeError("An export file disappeared before the bundle finished. Export again.")
    fsutil.write_text(path, json.dumps({
        "version": 1, "options": options or {}, "inputs": inputs, "outputs": outputs,
    }, indent=2))


def compare(record: dict, out_dir: Path, current: dict) -> dict:
    previous = record["inputs"]
    changed_inputs = sorted(name for name in previous["files"].keys() | current["files"].keys()
                            if previous["files"].get(name) != current["files"].get(name))
    settings_changed = sorted(name for name in previous["settings"].keys() | current["settings"].keys()
                              if previous["settings"].get(name) != current["settings"].get(name))
    changed_outputs = []
    resolved_out = out_dir.resolve()
    for name, digest in record["outputs"].items():
        path = (out_dir / name).resolve()
        if resolved_out not in path.parents or _digest(path) != digest:
            changed_outputs.append(name)
    return {"status": "stale" if changed_inputs or settings_changed or changed_outputs else "current",
            "changed_inputs": changed_inputs, "settings_changed": settings_changed,
            "changed_outputs": sorted(changed_outputs)}


def locked(out_dir: Path):
    """Serialize writes to one bundle across processes. Closing releases the OS lock."""
    return fsutil.locked(out_dir.with_name(f".{out_dir.name}.export.lock"),
                         "An export is already running for this bundle. Retry when it finishes.")
