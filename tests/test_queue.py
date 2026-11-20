import threading
import time

import pytest

from spritewaffle.core.job import Job
from spritewaffle.core.queue import Queue, Worker
from synth import write_clip


class Recorder:
    """Fake stages: sleep, record concurrency per resource and start/finish order."""

    def __init__(self, delay=0.15):
        self.delay = delay
        self.lock = threading.Lock()
        self.now = {"gpu": 0, "cpu": 0}
        self.peak = {"gpu": 0, "cpu": 0}
        self.both = False
        self.events = []

    def make(self, resource, fail=False):
        def fn(job, prof, args):
            with self.lock:
                self.now[resource] += 1
                self.peak[resource] = max(self.peak[resource], self.now[resource])
                self.both |= self.now["gpu"] > 0 and self.now["cpu"] > 0
                self.events.append(("start", args.get("n")))
            time.sleep(self.delay)
            with self.lock:
                self.now[resource] -= 1
                self.events.append(("end", args.get("n")))
            if fail:
                raise RuntimeError("boom")
            return {"n": args.get("n")}
        return fn

    def registry(self):
        return {"action": ("gpu", self.make("gpu")), "facings": ("gpu", self.make("gpu", fail=True)),
                "pixelize": ("cpu", self.make("cpu")), "select": ("cpu", self.make("cpu"))}


@pytest.fixture
def env(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    return tmp_path, job, Queue(tmp_path)


def test_limits_per_resource_and_parallel_pools(env):
    base, job, q = env
    rec = Recorder()
    for i in range(3):
        q.submit(job.root, "action", {"n": f"g{i}"})
    for i in range(4):
        q.submit(job.root, "pixelize", {"n": f"c{i}"})
    Worker(q, {"gpu": 1, "cpu": 2}, poll=0.02, registry=rec.registry()).run_until_idle(timeout=10)
    assert rec.peak == {"gpu": 1, "cpu": 2} and rec.both
    assert all(t["status"] == "done" for t in q.list())


def test_after_chain_order_and_blocked_dependents(env):
    base, job, q = env
    rec = Recorder(0.05)
    a = q.submit(job.root, "action", {"n": "a"})
    b = q.submit(job.root, "select", {"n": "b"}, after=[a["id"]])
    bad = q.submit(job.root, "facings", {"n": "bad"})
    c = q.submit(job.root, "pixelize", {"n": "c"}, after=[bad["id"]])
    Worker(q, poll=0.02, registry=rec.registry()).run_until_idle(timeout=10)
    ev = rec.events
    assert ev.index(("end", "a")) < ev.index(("start", "b"))
    assert q.get(bad["id"])["status"] == "failed" and "boom" in q.get(bad["id"])["error"]
    assert q.get(c["id"])["status"] == "failed" and q.get(c["id"])["error"].startswith("blocked")
    assert ("start", "c") not in ev


def test_cancel_only_queued(env):
    base, job, q = env
    t = q.submit(job.root, "action", {"n": 1})
    assert q.cancel(t["id"])["status"] == "cancelled"
    with pytest.raises(ValueError):
        q.cancel(t["id"])
    with pytest.raises(ValueError):
        q.submit(job.root, "nope")


def test_crash_recovery_and_worker_lock(env):
    base, job, q = env
    t = q.submit(job.root, "action", {"n": "x"})
    q.update(t["id"], status="running", started="then")         # worker died mid-task
    (q.dir / "worker.lock").write_text("pid 1")
    rec = Recorder(0.01)
    with pytest.raises(RuntimeError, match="another worker"):
        Worker(q, registry=rec.registry()).run_until_idle()
    Worker(q, poll=0.02, registry=rec.registry()).run_until_idle(force=True, timeout=10)
    assert q.get(t["id"])["status"] == "done" and not (q.dir / "worker.lock").exists()


def test_concurrent_job_meta_writes_are_not_lost(env):
    base, job, q = env

    def spam(k):
        for i in range(40):
            job.log_provenance(f"{k}-{i}")
            job.set_stage(f"s{k}", "done", i=i)

    ths = [threading.Thread(target=spam, args=(k,)) for k in range(6)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    meta = job.read_meta()
    assert len(meta["provenance"]) == 240 and all(meta["stages"][f"s{k}"]["i"] == 39 for k in range(6))


def test_real_pipeline_on_synthetic_clip(env):
    base, job, q = env
    clip = base / "walk.mp4"
    write_clip(clip, frames=48)
    ex = q.submit(job.root, "extract", {"video": str(clip), "facing": "S", "action": "walk"})
    tasks = q.submit_action_pipeline(job.root, "S", "walk", generate=False)
    q.update(tasks[0]["id"], after=[ex["id"]])
    Worker(q, poll=0.05).run_until_idle(timeout=120)
    assert [q.get(t["id"])["status"] for t in [ex] + tasks] == ["done"] * 5
    assert (job.root / "06_export/S/walk/12f/walk_S_12f.aseprite").exists()
    assert q.get(tasks[2]["id"])["result"] == {"12f": "pass", "24f": "pass"}
