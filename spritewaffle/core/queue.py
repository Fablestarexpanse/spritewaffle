"""Job queue with per-resource concurrency limits.

Tasks are JSON files in <base>/_queue/ (shared by CLI and web UI). One worker process at a time
(lock file). Resources: 'gpu' (ComfyUI stages; one GPU -> default limit 1) and 'cpu' (frame
processing; default limit 2). A task may wait for other tasks (`after`); if one of those fails or
is cancelled, the task fails as 'blocked'.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Callable

from .job import Job
from .profile import resolve

STATUSES = ("queued", "running", "done", "failed", "cancelled")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# --- stage registry ---------------------------------------------------------------------------

def _stages():
    from . import generate, stages

    def need(args, *keys):
        missing = [k for k in keys if not args.get(k)]
        if missing:
            raise ValueError(f"missing args {missing}")

    def anchor(job, prof, a):
        return str(generate.anchor(job, prof, description=a.get("describe"), image=a.get("image"), seed=a.get("seed")))

    def facings(job, prof, a):
        return generate.facings(job, prof, only=a.get("only"), seed=a.get("seed"),
                                diagonals=a.get("diagonals", "nearest"))

    def action(job, prof, a):
        need(a, "facing", "action")
        return generate.action(job, prof, a["facing"], a["action"], seconds=a.get("seconds", 2.0),
                               mode=a.get("mode", "fl2va"), seed=a.get("seed"))

    def bridge(job, prof, a):
        need(a, "facing", "action", "a", "b")
        dest = job.action_dir(a["facing"], a["action"]) / "bridges" / f"{a.get('name', 'bridge')}.png"
        return str(generate.bridge(job, a["a"], a["b"], dest, seed=a.get("seed"), method=a.get("method", "video")))

    def extract(job, prof, a):
        need(a, "video", "facing", "action")
        return stages.extract(job, a["video"], a["facing"], a["action"])

    def select(job, prof, a):
        need(a, "facing", "action")
        return stages.select(job, a["facing"], a["action"], indices=a.get("indices"), loop=a.get("loop"))

    def pixelize(job, prof, a):
        need(a, "facing", "action")
        return stages.pixel(job, prof, a["facing"], a["action"], palette=a.get("palette"))

    def qa(job, prof, a):
        need(a, "facing", "action")
        return stages.qa(job, prof, a["facing"], a["action"])

    def export(job, prof, a):
        need(a, "facing", "action")
        return stages.export(job, prof, a["facing"], a["action"], a.get("format", "both"))

    gpu = {"anchor": anchor, "facings": facings, "action": action, "bridge": bridge}
    cpu = {"extract": extract, "select": select, "pixelize": pixelize, "qa": qa, "export": export}
    return {**{k: ("gpu", f) for k, f in gpu.items()}, **{k: ("cpu", f) for k, f in cpu.items()}}


STAGE_NAMES = ("anchor", "facings", "action", "bridge", "extract", "select", "pixelize", "qa", "export")
POST_ACTION = ("select", "pixelize", "qa", "export")


# --- store ------------------------------------------------------------------------------------

class Queue:
    def __init__(self, base: str | Path = "jobs"):
        self.dir = Path(base) / "_queue"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, tid: str) -> Path:
        return self.dir / f"{tid}.json"

    def get(self, tid: str) -> dict:
        return json.loads(self._path(tid).read_text())

    def _put(self, t: dict) -> dict:
        tmp = self._path(t["id"]).with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(t, indent=2, default=str))
        os.replace(tmp, self._path(t["id"]))
        return t

    def list(self, status: str | None = None) -> list[dict]:
        tasks = []
        for p in self.dir.glob("*.json"):
            try:
                tasks.append(json.loads(p.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        tasks.sort(key=lambda t: (t["created"], t["seq"]))
        return [t for t in tasks if status is None or t["status"] == status]

    def submit(self, job: str | Path, stage: str, args: dict | None = None, profile: str | None = None,
               after: list[str] | None = None) -> dict:
        if stage not in STAGE_NAMES:
            raise ValueError(f"unknown stage {stage}; known: {STAGE_NAMES}")
        for a in after or []:
            if not self._path(a).exists():
                raise ValueError(f"unknown task in after: {a}")
        with self._lock:
            t = {"id": uuid.uuid4().hex[:10], "seq": time.time_ns(), "job": str(job), "stage": stage,
                 "resource": "gpu" if stage in ("anchor", "facings", "action", "bridge") else "cpu",
                 "args": args or {}, "profile": profile, "after": list(after or []), "status": "queued",
                 "created": _now(), "started": None, "finished": None, "error": None, "result": None}
            return self._put(t)

    def submit_action_pipeline(self, job, facing: str, action: str, profile: str | None = None,
                               generate: bool = True, **action_args) -> list[dict]:
        """action (gpu) -> select -> pixelize -> qa -> export (cpu), chained with `after`."""
        tasks, prev = [], []
        base = {"facing": facing, "action": action}
        if generate:
            tasks.append(self.submit(job, "action", {**base, **action_args}, profile))
            prev = [tasks[-1]["id"]]
        for st in POST_ACTION:
            tasks.append(self.submit(job, st, dict(base), profile, after=prev))
            prev = [tasks[-1]["id"]]
        return tasks

    def cancel(self, tid: str) -> dict:
        with self._lock:
            t = self.get(tid)
            if t["status"] != "queued":
                raise ValueError(f"task {tid} is {t['status']}; only queued tasks can be cancelled")
            t.update(status="cancelled", finished=_now())
            return self._put(t)

    def update(self, tid: str, **fields) -> dict:
        with self._lock:
            t = self.get(tid)
            t.update(fields)
            return self._put(t)


# --- worker -----------------------------------------------------------------------------------

class Worker:
    """Runs queued tasks with per-resource limits. `run_until_idle()` for tests/CLI one-shots,
    `start()` for a background thread (web UI)."""

    def __init__(self, queue: Queue, limits: dict | None = None, poll: float = 0.5,
                 registry: dict[str, tuple[str, Callable]] | None = None, lock: bool = True):
        self.q = queue
        self.limits = {"gpu": 1, "cpu": 2, **(limits or {})}
        self.poll = poll
        self.registry = registry
        self.running: dict[str, threading.Thread] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lockfile = queue.dir / "worker.lock" if lock else None

    # lock: one worker per queue
    def _acquire(self, force: bool) -> None:
        if not self._lockfile:
            return
        try:
            fd = os.open(self._lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not force:
                raise RuntimeError(f"another worker holds {self._lockfile} ({self._lockfile.read_text()}); "
                                   "stop it, or pass --force if it crashed")
            self._lockfile.unlink()
            fd = os.open(self._lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pid {os.getpid()} since {_now()}".encode())
        os.close(fd)

    def _release(self) -> None:
        if self._lockfile:
            self._lockfile.unlink(missing_ok=True)

    def _recover(self) -> None:
        """Tasks left 'running' by a dead worker go back to 'queued' (we hold the only lock)."""
        for t in self.q.list("running"):
            self.q.update(t["id"], status="queued", started=None, error="re-queued after worker restart")

    def _ready(self, t: dict) -> tuple[bool, str | None]:
        for a in t["after"]:
            st = self.q.get(a)["status"]
            if st in ("failed", "cancelled"):
                return False, f"blocked: dependency {a} {st}"
            if st != "done":
                return False, None
        return True, None

    def _execute(self, t: dict) -> None:
        reg = self.registry or _stages()
        try:
            _, fn = reg[t["stage"]]
            job = Job.open(t["job"])
            result = fn(job, resolve(t.get("profile")), t["args"])
            self.q.update(t["id"], status="done", finished=_now(), result=result)
        except Exception as e:                               # a failed task never kills the worker
            self.q.update(t["id"], status="failed", finished=_now(),
                          error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])

    def tick(self) -> int:
        """Start every runnable task the limits allow. Returns the number started."""
        self.running = {k: th for k, th in self.running.items() if th.is_alive()}
        busy = {"gpu": 0, "cpu": 0}
        for tid in self.running:
            busy[self.q.get(tid)["resource"]] += 1
        started = 0
        for t in self.q.list("queued"):
            ok, why = self._ready(t)
            if why:
                self.q.update(t["id"], status="failed", finished=_now(), error=why)
                continue
            if not ok or busy[t["resource"]] >= self.limits[t["resource"]]:
                continue
            t = self.q.update(t["id"], status="running", started=_now())
            th = threading.Thread(target=self._execute, args=(t,), daemon=True, name=f"task-{t['id']}")
            self.running[t["id"]] = th
            busy[t["resource"]] += 1
            th.start()
            started += 1
        return started

    def _idle(self) -> bool:
        return not any(th.is_alive() for th in self.running.values()) and not self.q.list("queued")

    def run_until_idle(self, force: bool = False, timeout: float | None = None) -> None:
        self._acquire(force)
        try:
            self._recover()
            deadline = None if timeout is None else time.time() + timeout
            while True:
                self.tick()
                if self._idle():
                    return
                if deadline and time.time() > deadline:
                    raise TimeoutError("queue did not drain in time")
                time.sleep(self.poll)
        finally:
            for th in self.running.values():
                th.join()
            self._release()

    def start(self, force: bool = False) -> None:
        """Background loop until stop() (web UI)."""
        self._acquire(force)
        self._recover()

        def loop():
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.poll)

        self._thread = threading.Thread(target=loop, daemon=True, name="queue-worker")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        for th in self.running.values():
            th.join()
        self._release()
