"""Job folders: every stage reads/writes only inside jobs/<character>/<job_id>/."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

STAGE_DIRS = ("01_anchor", "02_facings", "03_actions", "04_pixel", "05_qa", "06_export")


@dataclass
class Job:
    root: Path

    @classmethod
    def create(cls, character: str, job_id: str | None = None, base: Path = Path("jobs"), **inputs) -> "Job":
        job_id = job_id or time.strftime("%Y%m%d_%H%M%S")
        root = base / character / job_id
        for d in STAGE_DIRS:
            (root / d).mkdir(parents=True, exist_ok=True)
        job = cls(root)
        if not job.meta_path.exists():
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
        return json.loads(self.meta_path.read_text())

    def write_meta(self, meta: dict) -> None:
        self.meta_path.write_text(json.dumps(meta, indent=2))

    def update_inputs(self, **inputs) -> None:
        meta = self.read_meta()
        meta["inputs"].update({k: v for k, v in inputs.items() if v is not None})
        self.write_meta(meta)

    def set_stage(self, stage: str, status: str, **info) -> None:
        meta = self.read_meta()
        meta["stages"][stage] = {"status": status, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **info}
        self.write_meta(meta)

    def log_provenance(self, output: str, **info) -> None:
        """Record how an output was made (model, seed, prompt, source...)."""
        meta = self.read_meta()
        meta["provenance"].append({"output": output, **info})
        self.write_meta(meta)

    def action_dir(self, facing: str, action: str) -> Path:
        d = self.root / "03_actions" / facing / action
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stage_dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d
