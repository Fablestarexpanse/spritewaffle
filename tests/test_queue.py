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
    import subprocess, sys
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (q.dir / "worker.lock").write_text(f"pid {live.pid} since now")
        rec = Recorder(0.01)
        with pytest.raises(RuntimeError, match="another worker"):
            Worker(q, registry=rec.registry()).run_until_idle()
    finally:
        live.kill(); live.wait()
    # holder is dead now -> taken over without --force
    Worker(q, poll=0.02, registry=rec.registry()).run_until_idle(timeout=10)
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
    got = [q.get(t["id"]) for t in [ex] + tasks]
    assert [t["status"] for t in got] == ["done"] * 5, [(t["stage"], t["error"], t.get("trace")) for t in got]
    assert (job.root / "06_export/S/walk/12f/walk_S_12f.aseprite").exists()
    assert q.get(tasks[2]["id"])["result"] == {"12f": "pass", "24f": "pass"}


def test_concurrent_task_updates_and_reads_do_not_fail(env):
    """Windows: os.replace onto a file being read raises PermissionError -> fsutil retries."""
    base, job, q = env
    t = q.submit(job.root, "action", {"n": 1})
    errors = []

    def writer():
        try:
            for i in range(300):
                q.update(t["id"], result={"i": i})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(300):
                q.list()
                q.get(t["id"])
        except Exception as e:
            errors.append(e)

    ths = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(3)]
    [th.start() for th in ths]
    [th.join() for th in ths]
    assert not errors, errors
    assert q.get(t["id"])["result"] == {"i": 299}


def test_stack_pipeline_chain(env):
    base, job, q = env
    ts = q.submit_stack_pipeline(job.root, height=16)                     # default: real 3D model
    assert [(t["stage"], t["resource"]) for t in ts] == [("model3d", "gpu"), ("stack", "cpu")]
    assert ts[1]["after"] == [ts[0]["id"]] and ts[1]["args"] == {"height": 16, "method": "3d"}
    ts = q.submit_stack_pipeline(job.root, height=16, method="carve")
    assert [t["stage"] for t in ts] == ["ortho", "stack"] and ts[1]["args"]["method"] == "carve"
    only = q.submit_stack_pipeline(job.root, views=False)
    assert [t["stage"] for t in only] == ["stack"] and only[0]["after"] == []


def test_worker_steps_aside_when_another_takes_the_lock_and_resumes_after(env):
    """2026-11-26: the web UI took the lock with force while an MCP worker (older code) kept
    claiming tasks; it failed a texture_retile it didn't know. A worker that loses the lock now
    stops claiming, and takes the queue back once the holder is gone."""
    import subprocess, sys, time
    base, job, q = env
    rec = Recorder(0.01)
    w = Worker(q, poll=0.02, registry=rec.registry())
    w.start()
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (q.dir / "worker.lock").write_text(f"pid {live.pid} since now")      # another worker took over
        t = q.submit(job.root, "select", {"n": "later"})
        time.sleep(0.3)
        assert q.get(t["id"])["status"] == "queued"                           # not claimed
    finally:
        live.kill(); live.wait()
    deadline = time.time() + 5
    while q.get(t["id"])["status"] != "done" and time.time() < deadline:
        time.sleep(0.05)
    w.stop()
    assert q.get(t["id"])["status"] == "done"
    assert not (q.dir / "worker.lock").exists()


def test_rerendering_a_view_also_refreshes_its_mirrors(env):
    """2026-11-26: re-rendering NE (a walk that turned mid-clip) left NW a flip of the old clip."""
    import json
    base, job, q = env
    d = job.root / "04_pixel" / "NW" / "walk"
    d.mkdir(parents=True)
    (d / "pixel_report.json").write_text(json.dumps({"method": "mirror", "source": "NE"}))
    tasks = q.submit_action_pipeline(job.root, "NE", "walk")
    chain = [(t["stage"], t["args"]["facing"]) for t in tasks]
    assert chain == [("action", "NE"), ("select", "NE"), ("pixelize", "NE"), ("qa", "NE"), ("export", "NE"),
                     ("mirror", "NW"), ("qa", "NW"), ("export", "NW")]
    assert tasks[5]["args"]["source"] == "NE" and tasks[5]["after"] == [tasks[4]["id"]]
    assert [t["stage"] for t in q.submit_action_pipeline(job.root, "S", "walk")] == ["action", "select", "pixelize", "qa", "export"]


def test_task_without_profile_uses_the_jobs_profile(env, tmp_path):
    """`spritewaffle animate` without --profile queued profile=None; the worker then used the
    built-in 64 px profile for a 104 px job (2026-11-26)."""
    import json
    from dataclasses import asdict
    from spritewaffle.core.profile import resolve
    base, job, q = env
    prof = {**asdict(resolve(None)), "name": "t104", "cell_size": 104}
    path = tmp_path / "t104.json"
    path.write_text(json.dumps(prof), encoding="utf-8")
    job.update_inputs(profile=str(path))
    seen = []
    reg = {"pixelize": ("cpu", lambda j, p, a: seen.append(p.cell_size) or {})}
    q.submit(job.root, "pixelize", {})
    q.submit(job.root, "pixelize", {}, str(resolve(None).name))   # an explicit profile still wins
    Worker(q, poll=0.02, registry=reg).run_until_idle(timeout=10)
    assert sorted(seen) == sorted([104, resolve(None).cell_size])
