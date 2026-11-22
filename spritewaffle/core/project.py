"""Settings shared by assets under a single jobs folder."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from ..prompts import styles
from . import fsutil, profile

SCHEMA_VERSION = 1
STYLE_DEFAULTS = {"default_style": None, "default_profile": None, "target_engine": "", "art_direction": ""}


def project_path(base: Path) -> Path:
    return Path(base) / "project.json"


def read(base: Path) -> dict:
    try:
        record = json.loads(fsutil.read_text(project_path(base)))
    except FileNotFoundError:
        record = {}
    if not isinstance(record, dict):
        raise ValueError("project.json must contain a JSON object")
    return {"schema_version": SCHEMA_VERSION, **record, "id": record.get("id") or Path(base).resolve().name}


@contextmanager
def edit(base: Path):
    path = project_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with fsutil.locked(path.with_name(".project.lock"), "Project settings are being saved. Try again."):
        record = read(base)
        version = record["schema_version"]
        if type(version) is not int or version < 1:
            raise ValueError("Invalid project schema_version")
        if version > SCHEMA_VERSION:
            raise ValueError(f"Project schema {version} is newer than this SpriteWaffle ({SCHEMA_VERSION})")
        yield record
        fsutil.write_text(path, json.dumps(record, indent=2, ensure_ascii=False))


def _style_fields(record: dict) -> dict:
    fields = record.get("style", {})
    if not isinstance(fields, dict):
        raise ValueError("Project style must be a JSON object")
    return fields


def _style_view(record: dict) -> dict:
    fields = _style_fields(record)
    return {"project_id": record["id"], "style": {key: fields.get(key, default) for key, default in STYLE_DEFAULTS.items()}}


def style(base: Path) -> dict:
    return _style_view(read(base))


def _check_profile(name: str) -> None:
    if name != "default" and (name.endswith(".json") or name not in profile.list_all()):
        raise ValueError(f"Project default game profile '{name}' is unavailable. Choose an installed profile in Project style.")
    try:
        profile.resolve(name)
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"Cannot load project default game profile '{name}': {error}") from error


def set_style(base: Path, changes: dict | None) -> dict:
    """Patch the known style fields, or clear them all with None."""
    if changes is not None and not isinstance(changes, dict):
        raise ValueError("Style settings must be a JSON object or null")
    changes = STYLE_DEFAULTS.copy() if changes is None else changes.copy()
    if unknown := changes.keys() - STYLE_DEFAULTS.keys():
        raise ValueError(f"Unknown project style settings: {', '.join(sorted(unknown))}")
    for key, value in changes.items():
        if not isinstance(value, str) and not (value is None and STYLE_DEFAULTS[key] is None):
            raise ValueError(f"{key} must be text" + (" or null" if STYLE_DEFAULTS[key] is None else ""))
        if isinstance(value, str):
            changes[key] = value.strip() or STYLE_DEFAULTS[key]
    if name := changes.get("default_style"):
        if name not in styles.STYLES:
            raise ValueError(f"Unknown project art style '{name}'")
    if name := changes.get("default_profile"):
        _check_profile(name)
    with edit(base) as record:
        fields = _style_fields(record).copy()
        for key, value in changes.items():
            if value == STYLE_DEFAULTS[key]:
                fields.pop(key, None)
            else:
                fields[key] = value
        if fields:
            record["style"] = fields
        else:
            record.pop("style", None)
        return _style_view(record)


def creation_inputs(base: Path, inputs: dict) -> dict:
    """Apply project defaults to new independent assets and save the creation-time guide."""
    if inputs.get("base_job"):
        return inputs
    guide = style(base)["style"]
    if guide == STYLE_DEFAULTS:
        return inputs
    result = {**inputs, "style_guide": guide}
    if "style" not in result and guide["default_style"]:
        result["style"] = styles.get(guide["default_style"])["name"]
    if "profile" not in result and (name := guide["default_profile"]):
        _check_profile(name)
        result["profile"] = name
    return result
