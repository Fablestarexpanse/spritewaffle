"""Job folders: every stage reads/writes only inside jobs/<character>/<job_id>/."""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import fsutil, project
from .. import paths

STAGE_DIRS = ("01_anchor", "02_facings", "03_actions", "04_pixel", "05_qa", "06_export")

# job.json is read-modify-written by stages; the queue runs stages of one job on several threads.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(root: Path) -> threading.Lock:
    key = str(Path(root).resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


@dataclass
class Job:
    root: Path

    @classmethod
    def create(cls, character: str, job_id: str | None = None, base: Path | None = None, **inputs) -> "Job":
        job_id = job_id or time.strftime("%Y%m%d_%H%M%S")
        base = Path(base) if base else paths.jobs()
        job = cls(base / character / job_id)
        with _lock_for(job.root):
            exists = job.meta_path.exists()
            if not exists:
                inputs = project.creation_inputs(base, inputs)
            for d in STAGE_DIRS:
                (job.root / d).mkdir(parents=True, exist_ok=True)
            if not exists:
                job.write_meta({"character": character, "job_id": job_id, "inputs": inputs, "stages": {}, "provenance": []})
        return job

    @classmethod
    def open(cls, path: str | Path) -> "Job":
        root = Path(path)
        if not (root / "job.json").exists():
            raise FileNotFoundError(f"no job.json in {root}")
        return cls(root)

    @property
    def meta_path(self) -> Path:
        return self.root / "job.json"

    def read_meta(self) -> dict:
        return json.loads(fsutil.read_text(self.meta_path))

    def write_meta(self, meta: dict) -> None:
        """Atomic replace, so a concurrent reader never sees a half-written file."""
        fsutil.write_text(self.meta_path, json.dumps(meta, indent=2, default=str))

    @contextmanager
    def mutate(self):
        """Serialized read-modify-write of job.json: `with job.mutate() as meta: meta[...] = ...`."""
        with _lock_for(self.root):
            meta = self.read_meta()
            yield meta
            self.write_meta(meta)

    def update_inputs(self, **inputs) -> None:
        with self.mutate() as meta:
            meta["inputs"].update({k: v for k, v in inputs.items() if v is not None})

    def set_stage(self, stage: str, status: str, **info) -> None:
        with self.mutate() as meta:
            meta["stages"][stage] = {"status": status, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **info}

    def log_provenance(self, output: str, **info) -> None:
        """Record how an output was made (model, seed, prompt, source...)."""
        with self.mutate() as meta:
            meta["provenance"].append({"output": output, **info})

    def require_approved(self, stage: str) -> None:
        """Gate: refuse to build on a stage the human hasn't approved (rule 2: one approved anchor)."""
        st = self.read_meta()["stages"].get(stage, {}).get("status")
        if st != "approved":
            raise RuntimeError(f"stage '{stage}' is {st or 'not run yet'}; approve it first")

    def archive(self) -> Path:
        """Move the job to <jobs>/_archive/<character>/<job_id> (reversible: move it back)."""
        import shutil
        dest = self.root.parent.parent / "_archive" / self.root.parent.name / self.root.name
        if dest.exists():
            raise FileExistsError(f"already archived: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.root), dest)
        if not any(self.root.parent.iterdir()):
            self.root.parent.rmdir()
        return dest

    def action_dir(self, facing: str, action: str) -> Path:
        d = self.root / "03_actions" / facing / action
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stage_dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d
