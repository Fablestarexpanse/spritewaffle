"""Local web UI: one static page + a JSON API over job folders and the queue.

Binds 127.0.0.1 only. POSTs take JSON bodies (a cross-site form can't send those without a CORS
preflight, which this server never answers); files are served only from inside the jobs folder.
The queue worker runs in-process while the server is up.
"""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .. import __version__, paths
from ..core import generate
from ..core import motion as motion_lib
from ..core.job import Job
from ..core.profile import list_all as list_profiles, resolve
from ..core.queue import Queue, Worker
from ..prompts import builder, styles

STATIC = Path(__file__).parent / "static"
ORDER = ("S", "E", "N", "W", "SE", "NE", "NW", "SW")
EXPORT_SUFFIXES = (".aseprite", ".png", ".gif", ".json")
from ..comfy.client import DEFAULT_URL as COMFY_URL


def create_app(base: str | Path | None = None, worker: bool = True, limits: dict | None = None,
               comfy_url: str = COMFY_URL) -> FastAPI:
    base = (Path(base) if base else paths.jobs()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    queue = Queue(base)
    state: dict = {"comfy": {"t": 0.0, "ok": False, "detail": "not checked"}}

    @asynccontextmanager
    async def lifespan(app):
        if worker:
            state["worker"] = Worker(queue, limits)
            state["worker"].start(force=True)            # the UI owns the queue while it runs
        yield
        if worker:
            state["worker"].stop()

    app = FastAPI(title="SpriteWaffle", lifespan=lifespan)

    # --- helpers --------------------------------------------------------------------------
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
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def crop(src: Path, size: int | None = None) -> str | None:
        """The sprite cut out of its green canvas on transparency (cached next to the source as
        .<name>.crop.png), so cards show the sprite instead of a mostly-green square."""
        if not src.exists():
            return None
        out = src.parent / f".{src.stem}.crop{size or ''}.png"
        if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
            import numpy as np
            from PIL import Image
            from ..pixel import chroma
            im = Image.fromarray(chroma.crop_sprite(np.array(Image.open(src).convert("RGB"))), "RGBA")
            if size:
                im.thumbnail((size, size), Image.NEAREST)
            im.save(out)
        return url(out)

    def thumb(root: Path) -> str | None:
        src = next((p for p in (root / "02_facings" / "S.png", root / "01_anchor" / "anchor.png") if p.exists()), None)
        return crop(src, 128) if src else None

    def bad(e: Exception):
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        raise HTTPException(400, msg)

    def job_profile(j: Job, body: dict | None = None) -> str | None:
        return (body or {}).get("profile") or j.read_meta()["inputs"].get("profile")

    def profile_directions(j: Job) -> int:
        try:
            return resolve(job_profile(j)).directions
        except (FileNotFoundError, ValueError):      # a missing profile must not break the job page
            return 8

    # --- static + files -------------------------------------------------------------------
    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/files/{path:path}")
    def files(path: str, download: bool = False):
        p = (base / path).resolve()
        if base not in p.parents or not p.is_file():
            raise HTTPException(404)
        return FileResponse(p, filename=p.name if download else None)

    # --- status ---------------------------------------------------------------------------
    @app.get("/api/status")
    def status():
        c = state["comfy"]
        if time.time() - c["t"] > 10:                    # cache: don't hammer ComfyUI every poll
            from ..comfy.client import ComfyClient, ComfyError
            try:
                info = ComfyClient(comfy_url, timeout=3).system_stats()
                c.update(ok=True, detail=f"ComfyUI {info.get('system', {}).get('comfyui_version', '?')}")
            except ComfyError as e:
                c.update(ok=False, detail=str(e))
            c["t"] = time.time()
        tasks = queue.list()
        counts = {s: sum(t["status"] == s for t in tasks) for s in ("queued", "running", "failed")}
        w = state.get("worker")
        def short(t: dict) -> dict:
            parts = Path(str(t["job"])).parts[-2:]
            a = t.get("args") or {}
            return {"id": t["id"], "job": "/".join(parts), "stage": t["stage"], "facing": a.get("facing"),
                    "action": a.get("action"), "started": t.get("started"), "attempt": t.get("attempt", 1)}
        running = [short(t) for t in tasks if t["status"] == "running"]
        return {"version": __version__, "comfy": {"ok": c["ok"], "detail": c["detail"]},
                "worker": bool(w and w._thread and w._thread.is_alive()), "queue": counts, "running": running,
                "now": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "jobs": str(base), "profiles": list_profiles(), "actions": sorted(builder.ACTIONS),
                "asset_types": sorted(builder.ASSET_TYPES),
                "styles": [{"name": k, "label": v["label"]} for k, v in styles.STYLES.items()]}

    # --- jobs -----------------------------------------------------------------------------
    @app.get("/api/jobs")
    def jobs():
        out = []
        for meta in base.glob("*/*/job.json"):
            if meta.parts[-3].startswith("_"):
                continue
            m = read_json(meta)
            root = meta.parent
            out.append({"character": m["character"], "job_id": m["job_id"],
                        "asset_type": m["inputs"].get("asset_type", "character"),
                        "profile": m["inputs"].get("profile"), "style": m["inputs"].get("style") or "pixel",
                        "stages": {k: v["status"] for k, v in m["stages"].items()},
                        "thumb": thumb(root),
                        "updated": meta.stat().st_mtime})
        return sorted(out, key=lambda j: -j["updated"])

    @app.post("/api/jobs")
    def create(body: dict = Body(...)):
        char, jid = body.get("character", "").strip(), (body.get("job_id") or "").strip() or None
        if not char or any(c in char + (jid or "") for c in "/\\:") or char.startswith("_"):
            raise HTTPException(400, "character (and job_id) must be plain names")
        asset_type = body.get("asset_type") or "character"
        if asset_type not in builder.ASSET_TYPES:
            raise HTTPException(400, f"unknown asset type {asset_type}")
        try:
            if body.get("profile"):
                resolve(body["profile"])                  # refuse unknown profiles early
        except FileNotFoundError as e:
            bad(e)
        try:
            style = styles.get(body.get("style") or "pixel")["name"]
        except ValueError as e:
            bad(e)
        j = Job.create(char, jid, base=base, asset_type=asset_type, profile=body.get("profile") or None, style=style)
        return {"character": char, "job_id": j.root.name}

    @app.post("/api/jobs/{char}/{jid}/settings")
    def settings(char: str, jid: str, body: dict = Body(...)):
        j = job_or_404(char, jid)
        try:
            if body.get("profile"):
                resolve(body["profile"])
            if body.get("asset_type") and body["asset_type"] not in builder.ASSET_TYPES:
                raise ValueError(f"unknown asset type {body['asset_type']}")
            if body.get("style"):
                styles.get(body["style"])
            if body.get("prompt_writer") and body["prompt_writer"] not in ("template", "ai"):
                raise ValueError("prompt_writer must be 'template' or 'ai'")
            j.update_inputs(profile=body.get("profile"), asset_type=body.get("asset_type"),
                            prompt_writer=body.get("prompt_writer"), style=body.get("style"))
            if "profile" in body and not body["profile"]:        # back to the built-in default
                with j.mutate() as meta:
                    meta["inputs"].pop("profile", None)
        except (FileNotFoundError, ValueError) as e:
            bad(e)
        return {"ok": True}

    @app.post("/api/jobs/{char}/{jid}/archive")
    def archive(char: str, jid: str):
        try:
            return {"archived": str(job_or_404(char, jid).archive())}
        except FileExistsError as e:
            bad(e)

    @app.get("/api/jobs/{char}/{jid}")
    def job(char: str, jid: str):
        j = job_or_404(char, jid)
        meta = j.read_meta()
        fr = read_json(j.root / "02_facings" / "facings_report.json") or {}
        def takes_of(rel: str, still: bool = True) -> list[dict]:
            from ..core import takes
            out = []
            for t in takes.list_takes(j, rel):
                p = (j.root / rel).parent / "takes" / t["take"]
                out.append({"take": t["take"], "kept": t.get("kept"), "seed": (t.get("values") or {}).get("seed"),
                            "url": url(p), "thumb": crop(p) if still else None})
            return out

        facings = [{"facing": f, "image": crop(j.root / "02_facings" / f"{f}.png"),
                    "takes": takes_of(f"02_facings/{f}.png"),
                    "full": url(j.root / "02_facings" / f"{f}.png"),
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
                           "qa": qa and {k: qa[k] for k in ("status", "errors", "warnings", "reroll")}}
            actions.append({"facing": facing, "action": action,
                            "status": meta["stages"].get(f"action:{facing}/{action}", {}).get("status"),
                            "transition": url(d / "transition.png"), "contact": url(d / "contact_sheet.png"),
                            "has_clip": (d / "raw.mp4").exists(), "clip": url(d / "raw.mp4"),
                            "takes": takes_of(f"03_actions/{facing}/{action}/raw.mp4", still=False),
                            "report": read_json(d / "action_report.json"), "sets": sets})
        exp = j.root / "06_export"
        st = exp / "stack"
        exports = sorted(
            [{"name": p.name, "group": p.parent.relative_to(exp).as_posix(), "size": p.stat().st_size,
              "url": url(p) + "&download=1"}
             for p in exp.rglob("*") if p.is_file() and p.suffix in EXPORT_SUFFIXES and p.parent.name != "frames"],
            key=lambda e: (e["group"], e["name"])) if exp.is_dir() else []
        return {"character": meta["character"], "job_id": meta["job_id"], "inputs": meta["inputs"],
                "asset_type": meta["inputs"].get("asset_type", "character"), "thumb": thumb(j.root),
                "style": meta["inputs"].get("style") or "pixel",
                "stages": meta["stages"], "anchor": crop(j.root / "01_anchor" / "anchor.png"),
                "anchor_full": url(j.root / "01_anchor" / "anchor.png"),
                "anchor_takes": takes_of("01_anchor/anchor.png"),
                "facings": facings, "facings_report": {k: fr.get(k) for k in ("warnings", "mirrored", "diagonals", "turned")},
                "directions": profile_directions(j),
                "variant": ({"base": Path(meta["inputs"]["base_job"]).name, "edit": meta["inputs"].get("edit")}
                            if meta["inputs"].get("base_job") else None),
                "actions": actions,
                "motions": [m["name"] for m in motion_lib.list_all(base) if m["status"] == "approved"],
                "stack": {"views": {v: crop(j.root / "02_ortho" / f"{v}.png") for v in ("front", "back", "right", "top")},
                          "turntable": next((url(p) for p in st.glob("*_turntable.gif")), None) if st.is_dir() else None,
                          "rotations": next((url(p) for p in st.glob("*_rotations.png")), None) if st.is_dir() else None,
                          "info": read_json(next(st.glob("*_slices.json"), Path("_none"))) if st.is_dir() else None,
                          "slices": next((url(p) for p in st.glob("*_slices.png")), None) if st.is_dir() else None,
                          "spin_gif": next((url(p) for p in st.glob("*_spin.gif")), None) if st.is_dir() else None,
                          "build_gif": next((url(p) for p in st.glob("*_build.gif")), None) if st.is_dir() else None},
                "exports": exports,
                "palette": palette_info(j),
                "showcase": next((url(p) for p in (exp / "showcase").glob("*_showcase.gif")), None)
                            if (exp / "showcase").is_dir() else None}

    @app.post("/api/jobs/{char}/{jid}/approve")
    def approve(char: str, jid: str, body: dict = Body(...)):
        j = job_or_404(char, jid)
        try:
            generate.approve(j, body["stage"])
        except (KeyError, ValueError) as e:
            bad(e)
        return {"ok": True}

    def palette_info(j: Job) -> dict | None:
        from ..core import job_palette
        cur = job_palette.get(j)
        if not cur:
            return None
        have = set(cur["colours"])
        stale = []
        for c in job_palette.clips(j):
            rep = j.root / "04_pixel" / c["facing"] / c["action"] / "pixel_report.json"
            used = set((read_json(rep) or {}).get("palette") or [])
            if not used <= have:
                stale.append(f"{c['action']} {c['facing']}")
        return cur | {"stale": stale}

    @app.post("/api/jobs/{char}/{jid}/palette")
    def palette(char: str, jid: str, body: dict = Body(...)):
        """op: rebuild (from anchor + facings), file (load .gpl/.hex/.png from body.file), unlock."""
        from ..core import job_palette
        j = job_or_404(char, jid)
        try:
            op = body.get("op")
            if op == "file":
                f = str(body.get("file", "")).strip().strip('"')
                job_palette.save(j, job_palette.load_file(f), f"file {Path(f).name}")
            elif op == "rebuild":
                cols = job_palette.from_stills(j, resolve(job_profile(j)))
                if not cols:
                    raise FileNotFoundError("no anchor or facing stills to build from")
                job_palette.save(j, cols, f"anchor + facings ({len(job_palette.stills(j))} stills)")
            elif op == "unlock":
                job_palette.clear(j)
            else:
                raise ValueError("op must be rebuild, file or unlock")
        except (ValueError, FileNotFoundError, OSError) as e:
            bad(e)
        return palette_info(j) or {}

    @app.post("/api/jobs/{char}/{jid}/restore")
    def restore_take(char: str, jid: str, body: dict = Body(...)):
        """Put an earlier take back (the current one is kept as a take). A restored clip is
        re-extracted and re-processed through the queue; stills go back to review."""
        from ..core import takes
        j = job_or_404(char, jid)
        rel, take = str(body.get("file", "")), str(body.get("take", ""))
        if ".." in rel or ".." in take:
            raise HTTPException(404)
        try:
            what = takes.restore(j, rel, take)
        except (FileNotFoundError, ValueError) as e:
            bad(e)
        tasks = []
        if what["stage"] == "action":
            base = {"facing": what["facing"], "action": what["action"]}
            prev = []
            for st, args in (("extract", {**base, "video": str(j.root / rel)}), ("select", base), ("pixelize", base),
                             ("qa", base), ("export", base)):
                t = queue.submit(j.root, st, dict(args), job_profile(j), after=prev)
                prev = [t["id"]]
                tasks.append(t["id"])
        return what | {"tasks": tasks}

    @app.get("/api/jobs/{char}/{jid}/prompts")
    def prompts_view(char: str, jid: str):
        from ..core import prompt_view
        return prompt_view.view(job_or_404(char, jid))

    @app.post("/api/jobs/{char}/{jid}/prompts")
    def prompts_edit(char: str, jid: str, body: dict = Body(...)):
        """kind 'action': {action, motion, transition, sound} (empty = back to preset/AI);
        kind 'facing': {facing: 'NE' or '*' for all, note}."""
        from ..core import prompt_view
        j = job_or_404(char, jid)
        try:
            if body.get("kind") == "action":
                prompt_view.set_action(j, str(body.get("action", "")), body)
            elif body.get("kind") == "facing":
                prompt_view.set_facing_note(j, str(body.get("facing", "")), str(body.get("note", "")))
            else:
                raise ValueError("kind must be 'action' or 'facing'")
        except ValueError as e:
            bad(e)
        return prompt_view.view(j)

    @app.get("/api/profiles")
    def profiles_full():
        """Every profile with its settings and which jobs use it ('default' = built-in, read-only)."""
        from dataclasses import asdict
        used: dict[str, list[str]] = {}
        for jj in base.glob("*/*/job.json"):
            if jj.parent.parent.name.startswith("_"):
                continue
            prof = (read_json(jj) or {}).get("inputs", {}).get("profile") or "default"
            used.setdefault(prof, []).append(f"{jj.parent.parent.name}/{jj.parent.name}")
        out = []
        for name in ["default"] + list_profiles():
            try:
                p = asdict(resolve(None if name == "default" else name))
            except (FileNotFoundError, ValueError, TypeError) as e:
                out.append({"name": name, "error": str(e), "used_by": used.get(name, [])})
                continue
            out.append(p | {"name": name, "builtin": name == "default", "used_by": sorted(used.get(name, []))})
        return out

    @app.post("/api/profiles")
    def profile_save(body: dict = Body(...)):
        from dataclasses import asdict
        from ..core.profile import save_named
        try:
            prof = save_named(str(body.get("name", "")).strip(), body)
        except (ValueError, TypeError) as e:
            bad(e)
        if body.get("use_for"):                      # "char/jid": switch that job to this profile
            c, jid = str(body["use_for"]).split("/", 1)
            job_or_404(c, jid).update_inputs(profile=prof.name)
        return asdict(prof)

    @app.post("/api/jobs/{char}/{jid}/variant")
    def make_variant(char: str, jid: str, body: dict = Body(...)):
        """New job: this character with one change. Queues its edited anchor."""
        from ..core import variant
        base_job = job_or_404(char, jid)
        try:
            v = variant.create(base_job, str(body.get("instruction", "")), (body.get("job_id") or "").strip() or None)
        except (ValueError, FileExistsError, RuntimeError) as e:
            bad(e)
        t = queue.submit(v.root, "anchor", {}, job_profile(v))
        return {"character": char, "job_id": v.root.name, "tasks": [t["id"]]}

    @app.post("/api/jobs/{char}/{jid}/stack_gif")
    def stack_gif(char: str, jid: str, body: dict = Body(default={})):
        """kind 'spin' (one turn) or 'build' (slices stack up, then a turn), drawn like the viewer."""
        from ..stack import gifs
        j = job_or_404(char, jid)
        d = j.root / "06_export" / "stack"
        name = j.read_meta()["character"]
        if not (d / f"{name}_slices.json").exists():
            bad(FileNotFoundError("build the sprite stack first"))
        kind = body.get("kind", "spin")
        try:
            opts = {"layer_px": max(1, min(4, int(body.get("layer_px", 1)))),
                    "tilt": max(0.2, min(1.0, float(body.get("tilt", 0.6)))),
                    "scale": max(1, min(8, int(body.get("scale", 4)))),
                    "steps": max(8, min(96, int(body.get("steps", 32))))}
            sl = gifs.load(d, name)
            if kind == "spin":
                out = gifs.spin(sl, d / f"{name}_spin.gif", **opts)
            elif kind == "build":
                out = gifs.build_up(sl, d / f"{name}_build.gif", angle=float(body.get("angle", 30)), **opts)
            else:
                raise ValueError("kind must be 'spin' or 'build'")
        except (ValueError, OSError) as e:
            bad(e)
        return out | {"url": url(Path(out["file"]))}

    @app.post("/api/jobs/{char}/{jid}/run")
    def run(char: str, jid: str, body: dict = Body(...)):
        """Queue work. stage: any queue stage, or 'pipeline' (one action), 'animate' (facings x
        actions, W/NW/SW mirrored), 'stack_pipeline' (ortho -> stack)."""
        j = job_or_404(char, jid)
        stage, args = body.get("stage"), dict(body.get("args") or {})
        profile = job_profile(j, body)
        try:
            if stage == "stack_pipeline":
                tasks = queue.submit_stack_pipeline(j.root, profile, views=args.get("views", True),
                                                    height=int(args.get("height", 24)), seed=args.get("seed"))
            elif stage == "pipeline":
                gen = args.pop("generate", True)
                tasks = queue.submit_action_pipeline(j.root, args.pop("facing"), args.pop("action"),
                                                     profile, generate=gen, **args)
            elif stage == "reprocess":
                tasks = queue.submit_reprocess(j.root, profile)
            elif stage == "animate":
                facings, actions = args.pop("facings", []), args.pop("actions", [])
                if not facings or not actions:
                    raise ValueError("pick at least one facing and one action")
                tasks = queue.submit_animate(j.root, facings, actions, profile, mirror=args.pop("mirror", True), **args)
            else:
                tasks = [queue.submit(j.root, stage, args, profile)]
        except (KeyError, ValueError) as e:
            bad(e)
        return [t["id"] for t in tasks]

    @app.post("/api/jobs/{char}/{jid}/export_character")
    def export_character(char: str, jid: str, body: dict = Body(default={})):
        from ..export import character
        j = job_or_404(char, jid)
        try:
            prof = resolve(job_profile(j))
            mirror = body.get("mirror", "pack")
            out = character.export(j.root, j.stage_dir("06_export") / "character", char, prof.fps,
                                   body.get("set", "12f"), require_pass=not body.get("include_failed"),
                                   max_size=int(body.get("max_size", 4096)), mirror=mirror)
        except (RuntimeError, ValueError, FileNotFoundError) as e:
            bad(e)
        j.set_stage("export:character", "done", pages=len(out["pages"]), mirror=mirror,
                    **{k: out[k] for k in ("animations", "skipped", "mode", "colours")})
        return out

    @app.post("/api/jobs/{char}/{jid}/showcase")
    def showcase(char: str, jid: str, body: dict = Body(default={})):
        from ..export import showcase as sc
        j = job_or_404(char, jid)
        try:
            size = max(256, min(1024, int(body.get("size", 512))))
            out = sc.for_job(j, resolve(job_profile(j)), size=size, frame_set=body.get("set", "12f"))
        except (RuntimeError, ValueError, FileNotFoundError) as e:
            bad(e)
        return out | {"url": url(Path(out["file"]))}

    # --- motion library -------------------------------------------------------------------
    @app.get("/api/motions")
    def motions():
        return [{k: m[k] for k in ("name", "status", "action", "facing", "frames", "notes")} | {"clip": url(Path(m["clip"]))}
                for m in motion_lib.list_all(base)]

    @app.post("/api/motions")
    def add_motion(body: dict = Body(...)):
        try:
            j = job_or_404(body["character"], body["job_id"])
            return motion_lib.add(body["name"], j, body["facing"], body["action"], base, body.get("notes", ""))
        except (KeyError, ValueError, FileNotFoundError) as e:
            bad(e)

    @app.post("/api/motions/{name}/approve")
    def approve_motion(name: str):
        try:
            return motion_lib.approve(name, base)
        except KeyError as e:
            bad(e)

    # --- queue ----------------------------------------------------------------------------
    @app.get("/api/queue")
    def queue_list(limit: int = 60, status: str = "all"):
        """Running tasks first, then the rest newest first. Filtered here, BEFORE the limit, so a
        running task or an old failure is never cut off by newer queued ones."""
        want = {"active": ("queued", "running"), "failed": ("failed",)}.get(status)
        ts = [t for t in queue.list() if want is None or t["status"] in want]
        ts = [t for t in ts if t["status"] == "running"] + [t for t in ts[::-1] if t["status"] != "running"]
        return [{k: t.get(k) for k in ("id", "status", "resource", "stage", "job", "args", "started",
                                       "finished", "error", "after")} for t in ts[:limit]]

    @app.post("/api/queue/{tid}/cancel")
    def cancel(tid: str):
        try:
            return queue.cancel(tid)
        except (FileNotFoundError, ValueError) as e:
            bad(e)

    @app.post("/api/queue/{tid}/retry")
    def retry(tid: str):
        try:
            return queue.retry(tid)
        except (FileNotFoundError, ValueError) as e:
            bad(e)

    @app.post("/api/queue/clear")
    def clear(body: dict = Body(default={})):
        return {"removed": queue.clear(("done", "cancelled", "failed") if body.get("failed") else ("done", "cancelled"))}

    return app


def serve(base: str | None = None, port: int = 8765) -> None:
    import uvicorn
    uvicorn.run(create_app(base), host="127.0.0.1", port=port, log_level="warning")
