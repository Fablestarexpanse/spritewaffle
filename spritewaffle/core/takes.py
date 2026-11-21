"""Every re-roll keeps the take it replaces, so nothing generated is lost (Ronan: "re-roll
originals should still be there in case I decide I want it").

Kept: the anchor, each facing, each action's raw clip. A take lives in a `takes/` folder next to
the file, with its provenance (seed, prompt, model) in `takes/index.json`. Restoring swaps it back
in (the current version becomes a take too) and puts the stage back to review.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .job import Job

KEPT_SUFFIXES = (".png", ".mp4")


def _keepable(job: Job, path: Path) -> bool:
    rel = path.relative_to(job.root).as_posix()
    return (rel == "01_anchor/anchor.png"
            or (rel.startswith("02_facings/") and rel.count("/") == 1 and path.suffix == ".png"
                and path.stem in ("S", "SE", "E", "NE", "N", "NW", "W", "SW"))
            or (rel.startswith("03_actions/") and path.name == "raw.mp4"))


def _index(folder: Path) -> list[dict]:
    p = folder / "index.json"
    return json.loads(p.read_text()) if p.exists() else []


def _latest_provenance(job: Job, rel: str) -> dict:
    for e in reversed(job.read_meta().get("provenance", [])):
        if str(e.get("output", "")).replace("\\", "/") == rel:     # older entries use Windows separators
            return {k: v for k, v in e.items() if k != "output"}
    return {}


def stash(job: Job, path: Path) -> Path | None:
    """Move an existing kept file aside before it is overwritten. Returns the take's path."""
    path = Path(path)
    if not path.exists() or not _keepable(job, path):
        return None
    folder = path.parent / "takes"
    folder.mkdir(exist_ok=True)
    data = path.read_bytes()
    for t in _index(folder):                       # swapping back and forth doesn't pile up copies
        old = folder / t["take"]
        if t.get("of") == path.name and old.exists() and old.stat().st_size == len(data) and old.read_bytes() == data:
            return old
    stamp = time.strftime("%Y%m%d_%H%M%S")
    take = folder / f"{path.stem}_{stamp}{path.suffix}"
    n = 2
    while take.exists():
        take = folder / f"{path.stem}_{stamp}_{n}{path.suffix}"
        n += 1
    shutil.copy2(path, take)
    rel = path.relative_to(job.root).as_posix()
    idx = _index(folder)
    idx.append({"take": take.name, "of": path.name, "kept": stamp, **_latest_provenance(job, rel)})
    (folder / "index.json").write_text(json.dumps(idx, indent=2, default=str))
    return take


def list_takes(job: Job, rel: str) -> list[dict]:
    """Takes of one file (rel to the job root), newest first."""
    path = job.root / rel
    return [t for t in reversed(_index(path.parent / "takes")) if t.get("of") == path.name
            and (path.parent / "takes" / t["take"]).exists()]


def restore(job: Job, rel: str, take: str) -> dict:
    """Put a take back. The current file is kept as a take first. Returns the stage to re-run."""
    path = job.root / rel
    src = path.parent / "takes" / Path(take).name
    if not src.exists() or not _keepable(job, path):
        raise FileNotFoundError(f"no take {take} for {rel}")
    entry = next((t for t in _index(src.parent) if t["take"] == src.name), {})
    stash(job, path)
    shutil.copyfile(src, path)          # fresh mtime: cached thumbnails and ?t= URLs must refresh
    job.log_provenance(rel, restored_from=f"takes/{src.name}",
                       **{k: v for k, v in entry.items() if k not in ("take", "of", "kept")})
    parts = Path(rel).parts
    if parts[0] == "01_anchor":
        job.set_stage("anchor", "review", restored=src.name)
        return {"stage": "anchor"}
    if parts[0] == "02_facings":
        job.set_stage("facings", "review", restored=f"{path.stem} <- {src.name}")
        return {"stage": "facings", "facing": path.stem}
    facing, action = parts[1], parts[2]
    job.set_stage(f"action:{facing}/{action}", "review", restored=src.name)
    return {"stage": "action", "facing": facing, "action": action}
