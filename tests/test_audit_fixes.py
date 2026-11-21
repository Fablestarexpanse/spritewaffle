"""Fixes from the fresh-eyes audit (docs/AUDIT_FRESH_EYES.md)."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spritewaffle.core.job import Job
from spritewaffle.core.queue import Queue
from spritewaffle.export import aseprite
from spritewaffle.ui.server import create_app

ROOT = Path(__file__).resolve().parents[1]


def _cli(*args, jobs: Path):
    import os
    return subprocess.run([sys.executable, "-m", "spritewaffle.cli", *args], capture_output=True, text=True,
                          env={**os.environ, "SPRITEWAFFLE_JOBS": str(jobs)})


def test_typo_job_is_an_error_not_a_new_job(tmp_path):
    Job.create("knight", "p2_002", base=tmp_path)
    r = _cli("export-character", "--job", "knight/p2_02", jobs=tmp_path)
    assert r.returncode != 0 and "no such job" in r.stderr and "knight/p2_002" in r.stderr
    assert not (tmp_path / "knight" / "p2_02").exists()


def test_one_shot_tags_play_once_loops_repeat_forever(tmp_path):
    idx = np.zeros((4, 8, 8), np.uint8)
    pal = np.array([[0, 0, 0], [255, 0, 0]], np.uint8)
    p = aseprite.write(tmp_path / "a.aseprite", idx, pal, [100] * 4,
                       tags=[("walk_S", 0, 1, "forward", 0), ("attack_S", 2, 3, "forward", 1), ("old", 0, 3, "forward")])
    doc = aseprite.read(p)
    assert [t[0] for t in doc.tags] == ["walk_S", "attack_S", "old"]
    assert doc.repeats == [0, 1, 0]


def test_queue_pins_running_and_filters_before_the_limit(tmp_path):
    job = Job.create("hero", "j1", base=tmp_path)
    q = Queue(tmp_path)
    first = q.submit(job.root, "qa")
    q.update(first["id"], status="running")
    old_fail = q.submit(job.root, "qa")
    q.update(old_fail["id"], status="failed", error="boom")
    for _ in range(5):
        q.submit(job.root, "qa")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        top = c.get("/api/queue?limit=3").json()
        assert top[0]["id"] == first["id"] and len(top) == 3          # running first even though oldest
        assert [t["id"] for t in c.get("/api/queue?status=failed&limit=3").json()] == [old_fail["id"]]
        assert {t["status"] for t in c.get("/api/queue?status=active").json()} == {"queued", "running"}


def test_profile_default_resolves():
    from spritewaffle.core.profile import resolve
    assert resolve("default").name == "default"


def test_readme_commands_copy_paste_cleanly():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "\t" not in readme
    assert "spritewaffle style <job>" not in readme and "spritewaffle writer <job>" not in readme
