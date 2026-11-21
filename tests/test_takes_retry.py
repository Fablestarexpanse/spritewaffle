"""Ronan's notes: keep re-roll takes, show what's running, re-run a failed render."""
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import generate, takes
from spritewaffle.core.job import Job
from spritewaffle.core.queue import Queue, Worker
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render


class FakeComfy:
    """run_template writes a green-background still, a different one each call."""

    def __init__(self):
        self.n = 0

    def run_template(self, slot, values, out_dir):
        self.n += 1
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "o.png"
        Image.fromarray(render(draw_sprite(self.n % 3), canvas=(256, 256), seed=self.n)).save(p)
        return {"files": [str(p)], "values": {"seed": 100 + self.n}, "template": slot}


def test_rerolling_keeps_the_previous_take_and_restore_swaps_back(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    dest = job.stage_dir("01_anchor") / "anchor.png"
    c = FakeComfy()
    generate._run(c, job, "anchor_still", {}, dest)
    first = dest.read_bytes()
    generate._run(c, job, "anchor_still", {}, dest)
    assert dest.read_bytes() != first
    ts = takes.list_takes(job, "01_anchor/anchor.png")
    assert len(ts) == 1 and ts[0]["values"]["seed"] == 101          # the take keeps its seed
    job.set_stage("anchor", "approved")
    what = takes.restore(job, "01_anchor/anchor.png", ts[0]["take"])
    assert dest.read_bytes() == first and what == {"stage": "anchor"}
    assert job.read_meta()["stages"]["anchor"]["status"] == "review"  # restoring un-approves
    assert len(takes.list_takes(job, "01_anchor/anchor.png")) == 2    # the replaced one is a take too


def test_only_anchor_facings_and_clips_are_kept(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    p = job.stage_dir("01_anchor") / "other.png"
    p.write_bytes(b"x")
    assert takes.stash(job, p) is None
    with pytest.raises(FileNotFoundError):
        takes.restore(job, "01_anchor/anchor.png", "nope.png")


def test_restoring_a_clip_reprocesses_it(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    d = job.action_dir("S", "walk")
    (d / "raw.mp4").write_bytes(b"one")
    takes.stash(job, d / "raw.mp4")
    (d / "raw.mp4").write_bytes(b"two")
    take = takes.list_takes(job, "03_actions/S/walk/raw.mp4")[0]["take"]
    with TestClient(create_app(tmp_path, worker=False)) as c:
        j = c.get("/api/jobs/hero/j").json()
        assert [a["takes"][0]["take"] for a in j["actions"]] == [take]
        r = c.post("/api/jobs/hero/j/restore", json={"file": "03_actions/S/walk/raw.mp4", "take": take}).json()
        assert r["stage"] == "action" and len(r["tasks"]) == 5
        assert [t["stage"] for t in c.get("/api/queue").json()][::-1] == ["extract", "select", "pixelize", "qa", "export"]
        assert c.post("/api/jobs/hero/j/restore", json={"file": "../x", "take": take}).status_code == 404
    assert (d / "raw.mp4").read_bytes() == b"one"


def test_status_says_what_is_running(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    q = Queue(tmp_path)
    t = q.submit(job.root, "action", {"facing": "E", "action": "walk"})
    q.update(t["id"], status="running", started="2026-11-20T10:00:00")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.get("/api/status").json()["running"]
        assert r == [{"id": t["id"], "job": "hero/j", "stage": "action", "facing": "E", "action": "walk",
                      "started": "2026-11-20T10:00:00", "attempt": 1}]


def test_failed_render_is_retried_once_with_a_new_seed(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    q = Queue(tmp_path)
    calls = []

    def flaky(job, prof, args):
        calls.append(dict(args))
        if len(calls) == 1:
            raise RuntimeError("ComfyUI dropped the connection")
        return {"ok": True}

    def bad_input(job, prof, args):
        calls.append("bad")
        raise ValueError("no such facing")

    reg = {"action": ("gpu", flaky), "anchor": ("gpu", bad_input)}
    a = q.submit(job.root, "action", {"facing": "S", "action": "walk", "seed": 7})
    b = q.submit(job.root, "anchor", {})
    Worker(q, poll=0.02, registry=reg, lock=False).run_until_idle(timeout=10)
    ta, tb = q.get(a["id"]), q.get(b["id"])
    assert ta["status"] == "done" and ta["attempt"] == 2 and "seed" not in calls[-1] and calls[0]["seed"] == 7
    assert tb["status"] == "failed" and calls.count("bad") == 1        # bad input is not retried


def test_render_failing_twice_stays_failed(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    q = Queue(tmp_path)

    def always(job, prof, args):
        raise RuntimeError("out of memory")

    t = q.submit(job.root, "action", {})
    Worker(q, poll=0.02, registry={"action": ("gpu", always)}, lock=False).run_until_idle(timeout=10)
    t = q.get(t["id"])
    assert t["status"] == "failed" and t["attempt"] == 2 and "out of memory" in t["error"]


def test_restored_file_is_newer_than_what_it_replaced(tmp_path):
    import os
    import time as _t
    job = Job.create("hero", "j", base=tmp_path)
    p = job.stage_dir("02_facings") / "E.png"
    p.write_bytes(b"old")
    os.utime(p, (1_000_000, 1_000_000))                       # an old take
    takes.stash(job, p)
    p.write_bytes(b"new")
    before = p.stat().st_mtime
    _t.sleep(0.01)
    takes.restore(job, "02_facings/E.png", takes.list_takes(job, "02_facings/E.png")[0]["take"])
    assert p.read_bytes() == b"old" and p.stat().st_mtime >= before     # thumbnails refresh


def test_swapping_back_and_forth_keeps_one_copy_each(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    p = job.stage_dir("01_anchor") / "anchor.png"
    p.write_bytes(b"A")
    takes.stash(job, p)
    p.write_bytes(b"B")
    for _ in range(3):
        takes.restore(job, "01_anchor/anchor.png", takes.list_takes(job, "01_anchor/anchor.png")[-1]["take"])
    assert len(takes.list_takes(job, "01_anchor/anchor.png")) == 2
