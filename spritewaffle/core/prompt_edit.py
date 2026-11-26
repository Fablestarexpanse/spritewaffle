"""Edit the prompt of one generated still before re-rolling it.

Ronan, 2026-11-26: after a re-roll, show the prompt behind a view so a person (or an agent) can fix
it, e.g. the back three-quarter view of a fitted vest drew the front lacing and buckle on the back.

An override is stored per output file (inputs["prompt_overrides"]["02_facings/NE.png"]) and
generate._run uses it instead of the built prompt the next time that file is generated. The
prompt actually used each time is still recorded in provenance. Clearing the override goes back
to the built prompt.
"""
from __future__ import annotations

from pathlib import Path

from .job import Job

MAX_LEN = 6000


def _key(file: str | Path) -> str:
    key = str(file).replace("\\", "/").lstrip("/")
    if not key or ".." in key.split("/") or not key.endswith(".png"):
        raise ValueError("give the generated PNG inside the job, e.g. 02_facings/NE.png")
    return key


def used(job: Job, file: str | Path) -> str | None:
    """The prompt the latest generation of this file was made with (provenance), if any."""
    key = _key(file)
    for p in reversed(job.read_meta().get("provenance") or []):
        if str(p.get("output", "")).replace("\\", "/") == key:
            prompt = (p.get("values") or {}).get("prompt")
            if isinstance(prompt, str):
                return prompt
    return None


def get(job: Job, file: str | Path) -> dict:
    key = _key(file)
    custom = (job.read_meta()["inputs"].get("prompt_overrides") or {}).get(key)
    return {"file": key, "used": used(job, key), "custom": custom}


def set_prompt(job: Job, file: str | Path, text: str | None) -> dict:
    """Save the prompt for the next generation of this file; empty or None clears it."""
    key = _key(file)
    text = (text or "").strip()
    if len(text) > MAX_LEN:
        raise ValueError(f"the prompt is longer than {MAX_LEN} characters")
    with job.mutate() as meta:
        overrides = dict(meta["inputs"].get("prompt_overrides") or {})
        if text:
            overrides[key] = text
        else:
            overrides.pop(key, None)
        if overrides:
            meta["inputs"]["prompt_overrides"] = overrides
        else:
            meta["inputs"].pop("prompt_overrides", None)
    return get(job, key)


def apply(job: Job, dest: Path, values: dict) -> tuple[dict, bool]:
    """values with this file's saved prompt in place of the built one. Returns (values, custom)."""
    try:
        key = _key(Path(dest).relative_to(job.root))
    except ValueError:
        return values, False
    text = (job.read_meta()["inputs"].get("prompt_overrides") or {}).get(key)
    if not text or not isinstance(values.get("prompt"), str):
        return values, False
    return {**values, "prompt": text}, True
