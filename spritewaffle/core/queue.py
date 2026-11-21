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

from . import fsutil
from .. import paths
from .job import Job
from .profile import resolve

STATUSES = ("queued", "running", "done", "failed", "cancelled")


def pid_alive(pid: int) -> bool:
    """True if a process with this pid is running. (On Windows os.kill(pid, 0) would kill it.)"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259               # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


GPU_RETRIES = 1          # a failed render is tried once more, with a new seed
# Errors that a second try can't fix (bad input, missing file, wrong setting): fail at once.
NO_RETRY = (ValueError, KeyError, FileNotFoundError, PermissionError, NotImplementedError)


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
        if job.read_meta()["inputs"].get("base_job") and not (a.get("describe") or a.get("image")):
            from . import variant                          # a variant re-rolls its edited anchor
            return str(variant.anchor(job, prof, seed=a.get("seed")))
        return str(generate.anchor(job, prof, description=a.get("describe"), image=a.get("image"), seed=a.get("seed"),
                                   asset_type=a.get("asset_type", "character"), style_ref=a.get("style_ref")))

    def facings(job, prof, a):
        return generate.facings(job, prof, only=a.get("only"), seed=a.get("seed"),
                                diagonals=a.get("diagonals", "nearest"))

    def action(job, prof, a):
        need(a, "facing", "action")
        return generate.action(job, prof, a["facing"], a["action"], seconds=a.get("seconds", 2.0),
                               mode=a.get("mode", "fl2va"), seed=a.get("seed"))

    def sheet(job, prof, a):
        need(a, "image", "views")
        from . import sheet_import
        return sheet_import.import_sheet(job, a["image"], a["views"], subject=a.get("subject", "character"),
                                         mirror=a.get("mirror", True))

    def transfer(job, prof, a):
        need(a, "facing", "action", "motion")
        return generate.transfer(job, prof, a["facing"], a["action"], a["motion"], size=a.get("size", 768),
                                 steps=a.get("steps", 8), seed=a.get("seed"))

    def bridge(job, prof, a):
        need(a, "facing", "action", "a", "b")
        dest = job.action_dir(a["facing"], a["action"]) / "bridges" / f"{a.get('name', 'bridge')}.png"
        return str(generate.bridge(job, a["a"], a["b"], dest, seed=a.get("seed"), method=a.get("method", "video")))

    def flow(job, prof, a):
        need(a, "facing", "action", "motion")
        return stages.flow_transfer(job, prof, a["facing"], a["action"], a["motion"], loop=a.get("loop"))

    def align(job, prof, a):
        return stages.align(job, prof, a.get("facing"), a.get("action"))

    def mirror(job, prof, a):
        need(a, "facing", "action")
        return stages.mirror_action(job, prof, a["facing"], a["action"], a.get("source"))

    def ortho(job, prof, a):
        from ..stack import stage as stack_stage
        return stack_stage.ortho(job, seed=a.get("seed"), only=a.get("only"))

    def stack(job, prof, a):
        from ..stack import stage as stack_stage
        return stack_stage.build(job, prof, stack_height=a.get("height", 24), layer_px=a.get("layer_px", 1),
                                 method=a.get("method", "3d"))

    def model3d(job, prof, a):
        from ..stack import stage as stack_stage
        return stack_stage.model3d(job, seed=a.get("seed"))

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

    def effect_render(job, prof, a):
        from . import effect
        return effect.render(job, seed=a.get("seed"))

    def effect_process(job, prof, a):
        from . import effect
        m = effect.process(job, prof)
        return {k: m[k] for k in ("name", "frames", "cell", "loop", "dir")}

    gpu = {"model3d": model3d, "effect_render": effect_render, "sheet": sheet, "anchor": anchor, "facings": facings, "action": action, "transfer": transfer, "bridge": bridge,
           "ortho": ortho}
    cpu = {"effect_process": effect_process, "mirror": mirror, "stack": stack, "flow": flow, "extract": extract, "select": select, "pixelize": pixelize, "qa": qa, "export": export, "align": align}
    return {**{k: ("gpu", f) for k, f in gpu.items()}, **{k: ("cpu", f) for k, f in cpu.items()}}


STAGE_NAMES = ("model3d", "effect_render", "effect_process", "sheet", "anchor", "facings", "action", "transfer", "bridge", "ortho", "stack", "mirror", "flow", "extract", "select", "pixelize", "qa", "export", "align")
POST_ACTION = ("select", "pixelize", "qa", "export")
# stages after which the asset manifest (core/manifest.py) is rebuilt
MANIFEST_STAGES = ("anchor", "facings", "sheet", "pixelize", "mirror", "flow", "transfer", "export", "align")


# --- store ------------------------------------------------------------------------------------

class Queue:
    def __init__(self, base: str | Path | None = None):
        self.dir = (Path(base) if base else paths.jobs()) / "_queue"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_seq = 0

    def _next_seq(self) -> int:
        """Strictly increasing order key (Windows time_ns ticks coarsely, so equal stamps happen)."""
        self._last_seq = max(time.time_ns(), self._last_seq + 1)
        return self._last_seq

    def _path(self, tid: str) -> Path:
        return self.dir / f"{tid}.json"

    def get(self, tid: str) -> dict:
        return json.loads(fsutil.read_text(self._path(tid)))

    def _put(self, t: dict) -> dict:
        fsutil.write_text(self._path(t["id"]), json.dumps(t, indent=2, default=str))
        return t

    def list(self, status: str | None = None) -> list[dict]:
        tasks = []
        for p in self.dir.glob("*.json"):
            try:
                tasks.append(json.loads(fsutil.read_text(p)))
            except (json.JSONDecodeError, OSError):
                continue
        tasks.sort(key=lambda t: t["seq"])
        return [t for t in tasks if status is None or t["status"] == status]

    def submit(self, job: str | Path, stage: str, args: dict | None = None, profile: str | None = None,
               after: list[str] | None = None) -> dict:
        if stage not in STAGE_NAMES:
            raise ValueError(f"unknown stage {stage}; known: {STAGE_NAMES}")
        for a in after or []:
            if not self._path(a).exists():
                raise ValueError(f"unknown task in after: {a}")
        with self._lock:
            t = {"id": uuid.uuid4().hex[:10], "seq": self._next_seq(), "job": str(job), "stage": stage,
                 "resource": "gpu" if stage in ("model3d", "effect_render", "sheet", "anchor", "facings", "action", "transfer", "bridge", "ortho") else "cpu",
                 "args": args or {}, "profile": profile, "after": list(after or []), "status": "queued",
                 "created": _now(), "started": None, "finished": None, "error": None, "result": None}
            return self._put(t)

    def submit_action_pipeline(self, job, facing: str, action: str, profile: str | None = None,
                               generate: bool = True, motion: str | None = None, method: str = "tara",
                               **action_args) -> list[dict]:
        """action or transfer (gpu) -> select -> pixelize -> qa -> export (cpu), chained with `after`.
        motion=<library name> renders through the experimental TARA transfer instead of H3 I2V."""
        tasks, prev = [], []
        base = {"facing": facing, "action": action}
        if motion and method == "flow":            # pixel-exact: selection + pixelize happen inside 'flow'
            tasks.append(self.submit(job, "flow", {**base, "motion": motion}, profile))
            for st in ("qa", "export"):
                tasks.append(self.submit(job, st, dict(base), profile, after=[tasks[-1]["id"]]))
            return tasks
        if generate:
            stage = "transfer" if motion else "action"
            extra = {"motion": motion} if motion else {}
            tasks.append(self.submit(job, stage, {**base, **extra, **action_args}, profile))
            prev = [tasks[-1]["id"]]
        for st in POST_ACTION:
            tasks.append(self.submit(job, st, dict(base), profile, after=prev))
            prev = [tasks[-1]["id"]]
        return tasks

    def submit_animate(self, job, facings: list[str], actions: list[str], profile: str | None = None,
                       mirror: bool = True, **action_args) -> list[dict]:
        """Batch: every facing x action. With mirror=True, W/NW/SW whose partner (E/NE/SE) is also
        requested are made by flipping the partner's pixel art (after its pixelize task) instead of
        rendering — same pixels, no GPU time. Each one still gets its own QA and export."""
        from .stages import MIRROR_OF
        flip = self._mirror_plan(job, facings, mirror, profile)
        tasks = []
        for action in actions:
            pix_task = {}
            mirrored = {f: src for f, src in flip.items() if f in facings}
            render = [f for f in facings if f not in mirrored]
            render += [s for s in dict.fromkeys(mirrored.values()) if s not in render
                       and not (Path(job) / "04_pixel" / s / action / "pixel_report.json").exists()]
            for f in render:
                chain = self.submit_action_pipeline(job, f, action, profile, **action_args)
                pix_task[f] = next(t["id"] for t in chain if t["stage"] in ("pixelize", "flow"))
                tasks += chain
            for f, src in mirrored.items():
                m = self.submit(job, "mirror", {"facing": f, "action": action, "source": src}, profile,
                                after=[pix_task[src]] if src in pix_task else [])
                q = self.submit(job, "qa", {"facing": f, "action": action}, profile, after=[m["id"]])
                e = self.submit(job, "export", {"facing": f, "action": action}, profile, after=[q["id"]])
                tasks += [m, q, e]
        return tasks

    def _mirror_plan(self, job, facings: list[str], mirror: bool, profile: str | None) -> dict[str, str]:
        """facing -> the facing it is flipped from. legacy (no policy): the run's mirror flag, W/NW/SW
        from a requested partner, as before. none: nothing. mirror_left_from_right / custom: per the
        policy, and a missing source is rendered too (docs/MANIFEST.md)."""
        from . import angles
        from .job import Job
        from .stages import MIRROR_OF
        jf = Path(job) / "job.json"
        inputs = Job.open(Path(job)).read_meta()["inputs"] if jf.exists() else {}
        policy = inputs.get("mirror_policy") or "legacy"
        if policy == "legacy":
            return {f: MIRROR_OF[f] for f in facings if mirror and f in ("W", "NW", "SW") and MIRROR_OF[f] in facings}
        if policy == "none":
            return {}
        n = resolve(profile).directions if profile else 8
        out = {}
        for f in facings:
            src = angles.mirror_source(angles.yaw_of(f), policy, inputs.get("mirror_map"), n=n)
            if src is not None:
                out[f] = angles.label(src)
        return out

    def submit_reprocess(self, job, profile: str | None = None) -> list[dict]:
        """Re-run every pixelized clip of a job from its frames (no rendering), e.g. after the job
        palette changed: renders -> pixelize, flow -> flow, then qa + export; mirrored facings are
        flipped again after their source's pixelize."""
        from . import job_palette
        from .job import Job
        clips = job_palette.clips(Job.open(Path(job)))
        tasks, pix = [], {}
        for c in [c for c in clips if c["method"] != "mirror"]:
            base = {"facing": c["facing"], "action": c["action"]}
            first = (self.submit(job, "flow", {**base, "motion": c["motion"]}, profile) if c["method"] == "flow"
                     else self.submit(job, "pixelize", dict(base), profile))
            pix[(c["facing"], c["action"])] = first["id"]
            q = self.submit(job, "qa", dict(base), profile, after=[first["id"]])
            tasks += [first, q, self.submit(job, "export", dict(base), profile, after=[q["id"]])]
        for c in [c for c in clips if c["method"] == "mirror"]:
            base = {"facing": c["facing"], "action": c["action"]}
            after = [pix[(c["source"], c["action"])]] if (c["source"], c["action"]) in pix else []
            m = self.submit(job, "mirror", {**base, "source": c["source"]}, profile, after=after)
            q = self.submit(job, "qa", dict(base), profile, after=[m["id"]])
            tasks += [m, q, self.submit(job, "export", dict(base), profile, after=[q["id"]])]
        return tasks

    def submit_stack_pipeline(self, job, profile: str | None = None, views: bool = True, height: int = 24,
                              seed: int | None = None, method: str = "3d") -> list[dict]:
        """Sprite stacking: 3D model or ortho views (gpu) -> stack build (cpu). views=False rebuilds
        from the model / views already there."""
        tasks = []
        if views:
            tasks.append(self.submit(job, "model3d" if method == "3d" else "ortho",
                                     {"seed": seed} if seed is not None else {}, profile))
        tasks.append(self.submit(job, "stack", {"height": height, "method": method}, profile,
                                 after=[t["id"] for t in tasks]))
        return tasks

    def cancel(self, tid: str) -> dict:
        with self._lock:
            t = self.get(tid)
            if t["status"] != "queued":
                raise ValueError(f"task {tid} is {t['status']}; only queued tasks can be cancelled")
            t.update(status="cancelled", finished=_now())
            return self._put(t)

    def retry(self, tid: str) -> dict:
        """Queue a failed/cancelled task again (same job, stage, args; no dependencies)."""
        t = self.get(tid)
        if t["status"] not in ("failed", "cancelled"):
            raise ValueError(f"task {tid} is {t['status']}; only failed or cancelled tasks can be retried")
        return self.submit(t["job"], t["stage"], t["args"], t.get("profile"))

    def clear(self, statuses=("done", "cancelled")) -> int:
        """Delete finished task files (failed ones stay until retried or cleared explicitly)."""
        n = 0
        for t in self.list():
            if t["status"] in statuses:
                self._path(t["id"]).unlink(missing_ok=True)
                n += 1
        return n

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
            holder = self._lockfile.read_text().split()
            pid = int(holder[1]) if len(holder) > 1 and holder[0] == "pid" and holder[1].isdigit() else -1
            if not force and pid_alive(pid) and pid != os.getpid():
                raise RuntimeError(f"another worker holds {self._lockfile} ({' '.join(holder)}); "
                                   "stop it, or pass --force")
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
            if t["stage"] in MANIFEST_STAGES:              # keep the asset manifest current (JSON only)
                from . import manifest
                manifest.refresh(job)
        except Exception as e:                               # a failed task never kills the worker
            err = f"{type(e).__name__}: {e}"
            attempt = t.get("attempt", 1)
            if t["resource"] == "gpu" and attempt <= GPU_RETRIES and not isinstance(e, NO_RETRY):
                args = {k: v for k, v in t["args"].items() if k != "seed"}      # new seed on the retry
                self.q.update(t["id"], status="queued", started=None, attempt=attempt + 1, args=args,
                              error=f"attempt {attempt} failed, retrying with a new seed: {err}",
                              trace=traceback.format_exc()[-2000:])
                return
            self.q.update(t["id"], status="failed", finished=_now(), error=err,
                          trace=traceback.format_exc()[-2000:])

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
