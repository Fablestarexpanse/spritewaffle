"""Local web UI: one static page + a small JSON API over job folders and the queue.

Binds 127.0.0.1 only. POSTs take JSON bodies (a cross-site form can't send those without a CORS
preflight, which this server never answers), files are served only from inside the jobs folder.
The queue worker runs in-process while the server is up.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from ..core import generate
from ..core import motion as motion_lib
from ..core.job import Job
from ..core.queue import Queue, Worker
from ..prompts import builder

STATIC = Path(__file__).parent / "static"
ORDER = ("S", "E", "N", "W", "SE", "NE", "NW", "SW")


def create_app(base: str | Path = "jobs", worker: bool = True, limits: dict | None = None) -> FastAPI:
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    queue = Queue(base)
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        if worker:
            state["worker"] = Worker(queue, limits)
            state["worker"].start(force=True)            # the UI owns the queue while it runs
        yield
        if worker:
            state["worker"].stop()

    app = FastAPI(title="SpriteWaffle", lifespan=lifespan)

    def job_or_404(char: str, jid: str) -> Job:
        root = (base / char / jid).resolve()
        if base not in root.parents or not (root / "job.json").exists():
            raise HTTPException(404, "no such job")
        return Job(root)

    def url(p: Path) -> str | None:
        if not p.exists():
            return None
        return f"/files/{p.resolve().relative_to(base).as_posix()}?t={p.stat().st_mtime_ns}"

    def read_json(p: Path):
        return json.loads(p.read_text()) if p.exists() else None

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/files/{path:path}")
    def files(path: str):
        p = (base / path).resolve()
        if base not in p.parents or not p.is_file():
            raise HTTPException(404)
        return FileResponse(p)

    @app.get("/api/jobs")
    def jobs():
        out = []
        for meta in sorted(base.glob("*/*/job.json")):
            m = read_json(meta)
            out.append({"character": m["character"], "job_id": m["job_id"],
                        "stages": {k: v["status"] for k, v in m["stages"].items()}})
        return out

    @app.post("/api/jobs")
    def create(body: dict = Body(...)):
        char, jid = body.get("character", "").strip(), (body.get("job_id") or "").strip() or None
        if not char or "/" in char or "\\" in char or (jid and ("/" in jid or "\\" in jid)):
            raise HTTPException(400, "character (and job_id) must be plain names")
        j = Job.create(char, jid, base=base)
        return {"character": char, "job_id": j.root.name}

    @app.get("/api/jobs/{char}/{jid}")
    def job(char: str, jid: str):
        j = job_or_404(char, jid)
        meta = j.read_meta()
        fr = read_json(j.root / "02_facings" / "facings_report.json") or {}
        facings = [{"facing": f, "image": url(j.root / "02_facings" / f"{f}.png"),
                    "drift": fr.get("facings", {}).get(f), "mirrored": f in fr.get("mirrored", {})} for f in ORDER]
        actions = []
        for d in sorted((j.root / "03_actions").glob("*/*")):
            if not d.is_dir():
                continue
            facing, action = d.parent.name, d.name
            sets = {}
            for n in ("12f", "24f"):
                qa = read_json(j.root / "05_qa" / facing / action / n / "report.json")
                sets[n] = {"preview": url(j.root / "06_export" / facing / action / n / f"{action}_{facing}_{n}_preview.gif"),
                           "qa": qa and {"status": qa["status"], "errors": qa["errors"], "warnings": qa["warnings"],
                                         "reroll": qa["reroll"]}}
            actions.append({"facing": facing, "action": action,
                            "status": meta["stages"].get(f"action:{facing}/{action}", {}).get("status"),
                            "transition": url(d / "transition.png"), "contact": url(d / "contact_sheet.png"),
                            "report": read_json(d / "action_report.json"), "sets": sets})
        return {"character": meta["character"], "job_id": meta["job_id"], "inputs": meta["inputs"],
                "stages": meta["stages"], "anchor": url(j.root / "01_anchor" / "anchor.png"),
                "facings": facings, "facings_report": {k: fr.get(k) for k in ("warnings", "mirrored", "diagonals")},
                "actions": actions, "known_actions": sorted(builder.ACTIONS),
                "motions": [m["name"] for m in motion_lib.list_all(base) if m["status"] == "approved"]}

    @app.post("/api/jobs/{char}/{jid}/approve")
    def approve(char: str, jid: str, body: dict = Body(...)):
        j = job_or_404(char, jid)
        try:
            generate.approve(j, body["stage"])
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/jobs/{char}/{jid}/run")
    def run(char: str, jid: str, body: dict = Body(...)):
        """Queue a stage (re-roll = run again with a new seed). stage 'pipeline' queues
        action -> select -> pixelize -> qa -> export; with generate=false only the post-processing."""
        j = job_or_404(char, jid)
        stage, args = body.get("stage"), dict(body.get("args") or {})
        try:
            if stage == "pipeline":
                gen = args.pop("generate", True)
                tasks = queue.submit_action_pipeline(j.root, args.pop("facing"), args.pop("action"),
                                                     body.get("profile"), generate=gen, **args)
            else:
                tasks = [queue.submit(j.root, stage, args, body.get("profile"))]
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))
        return [t["id"] for t in tasks]

    @app.get("/api/queue")
    def queue_list(limit: int = 40):
        ts = queue.list()
        return [{k: t.get(k) for k in ("id", "status", "resource", "stage", "job", "args", "started",
                                       "finished", "error", "after")} for t in ts[-limit:]][::-1]

    @app.post("/api/queue/{tid}/cancel")
    def cancel(tid: str):
        try:
            return queue.cancel(tid)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    return app


def serve(base: str = "jobs", port: int = 8765) -> None:
    import uvicorn
    uvicorn.run(create_app(base), host="127.0.0.1", port=port, log_level="warning")
