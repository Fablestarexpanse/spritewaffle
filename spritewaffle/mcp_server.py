"""SpriteWaffle MCP server (stdio): generate, animate, status, approve.

Tools only queue work; the queue worker runs inside this process unless another worker (the web
UI or `spritewaffle worker`) already holds the queue. Approval stays a human decision: the
approve tool is for relaying a yes the human gave after looking at the output.
"""

import io
import json
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

from . import paths
from .core import generate as gen
from .core.job import Job
from .core.queue import Queue, Worker
from .prompts import builder

ORDER = ("S", "E", "N", "W", "SE", "NE", "NW", "SW")


def build(base: str | Path | None = None) -> tuple[FastMCP, Queue]:
    base = (Path(base) if base else paths.jobs()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    q = Queue(base)
    mcp = FastMCP("spritewaffle", instructions=(
        "Turns a character description into game-ready pixel-art sprite sets via the local ComfyUI. "
        "Order: generate(stage='anchor') -> show the anchor to the human -> approve('anchor') only after "
        "they say yes -> generate(stage='facings') -> human approves -> approve('facings') -> animate(...) "
        "per facing/action. Use status(wait_seconds=...) to wait for queued work and include_images to see "
        "results. Hero asset first: make and approve one hero, then pass its job as style_ref for others."))

    def job_for(character: str, job_id: str) -> Job:
        root = (base / character / job_id).resolve()
        if base not in root.parents or not (root / "job.json").exists():
            raise ValueError(f"no job {character}/{job_id}")
        return Job(root)

    def thumb(p: Path, size: int = 512) -> Image:
        im = PILImage.open(p).convert("RGBA")
        im.thumbnail((size, size), PILImage.NEAREST)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return Image(data=buf.getvalue(), format="png")

    def open_tasks(job: Job | None = None) -> list[dict]:
        ts = q.list()
        if job:
            ts = [t for t in ts if Path(t["job"]).resolve() == job.root]
        return [t for t in ts if t["status"] in ("queued", "running")]

    @mcp.tool()
    def generate(character: str, stage: str = "anchor", description: str | None = None,
                 job_id: str | None = None, asset_type: str = "character", style_ref: str | None = None,
                 image: str | None = None, seed: int | None = None, only: list[str] | None = None,
                 style: str | None = None) -> dict:
        """Queue a still-image stage.

        stage='anchor': creates the job when job_id is omitted. Needs `description` (or `image`, a path
        to import). asset_type: character | creature | prop. style_ref: an approved hero as
        'character/job_id' (or an image path) to draw this asset in the hero's style.
        stage='facings': needs an approved anchor; `only` re-rolls specific facings, e.g. ['SW'].
        style (anchor): pixel (default), painted (hand-painted), anime (anime cel), comic (comic ink).
        stage='sheet': import the human's own character sheet: image=<path>, only=<facing of each figure
        left to right, e.g. ['S','SE','E','N']>, description=<what to cut out, e.g. 'hare character'>.
        Returns the job and queued task ids; call status(...) to follow progress."""
        if stage not in ("anchor", "facings", "sheet"):
            raise ValueError("stage must be 'anchor', 'facings' or 'sheet'")
        if stage == "sheet":
            if not image or not only:
                raise ValueError("sheet: pass image=<sheet path> and only=<facing of each figure, left to right>")
            job = job_for(character, job_id) if job_id else Job.create(character, base=base, asset_type=asset_type)
            if style:
                from .prompts import styles
                job.update_inputs(style=styles.get(style)["name"])
            t = q.submit(job.root, "sheet", {"image": image, "views": only, "subject": description or "character"})
            return {"character": character, "job_id": job.root.name, "tasks": [t["id"]]}
        if stage == "anchor":
            builder.asset(asset_type)
            job = job_for(character, job_id) if job_id else Job.create(character, base=base)
            if style:
                from .prompts import styles
                job.update_inputs(style=styles.get(style)["name"])
            args = {"describe": description, "image": image, "seed": seed, "asset_type": asset_type}
            if style_ref:
                ref = base / style_ref if "/" in style_ref and not Path(style_ref).exists() else Path(style_ref)
                args["style_ref"] = str(ref)
        else:
            if not job_id:
                raise ValueError("facings needs job_id")
            job = job_for(character, job_id)
            args = {"seed": seed, "only": only}
        t = q.submit(job.root, stage, {k: v for k, v in args.items() if v is not None})
        return {"character": character, "job_id": job.root.name, "tasks": [t["id"]]}

    @mcp.tool()
    def animate(character: str, job_id: str, facing: str, action: str, seconds: float = 2.0,
                seed: int | None = None, reprocess_only: bool = False, motion: str | None = None,
                method: str = "tara") -> dict:
        """Queue an action for one facing: transition pose -> H3 clip -> frame selection -> pixelize ->
        QA -> export (PNG strip, .aseprite with tag, GIF). Needs approved facings.
        facing: S E N W SE NE NW SW. action: idle walk run attack jump.
        reprocess_only=True re-runs selection..export on the existing clip without a new render.
        motion=<approved library motion> (EXPERIMENTAL): transfer that clip's motion with TARA instead of
        rendering with H3; check identity_drift in status and fall back to H3 when it warns.
        method='flow' (with motion): pixel-exact transfer by optical flow, no render, identity exact,
        but it can only move the facing's existing pixels (no turns, no unseen parts)."""
        job = job_for(character, job_id)
        if facing not in ORDER:
            raise ValueError(f"facing must be one of {ORDER}")
        if action not in builder.ACTIONS and job.read_meta()["inputs"].get("prompt_writer") != "ai":
            builder.action_spec(action)                       # raises with the list of presets
        if not reprocess_only and job.read_meta()["stages"].get("facings", {}).get("status") != "approved":
            raise ValueError("facings are not approved yet; show them to the human first")
        if motion:
            from .core import motion as motion_lib
            m = motion_lib.get(motion, base)
            if m["status"] != "approved":
                raise ValueError(f"motion '{motion}' is not approved")
            args = {**({"seed": seed} if seed is not None else {})}
        else:
            args = {"seconds": seconds, **({"seed": seed} if seed is not None else {})}
        if method not in ("tara", "flow"):
            raise ValueError("method must be 'tara' or 'flow'")
        ts = q.submit_action_pipeline(job.root, facing, action, generate=not reprocess_only, motion=motion,
                                      method=method, **args)
        return {"character": character, "job_id": job_id, "tasks": [t["id"] for t in ts]}

    @mcp.tool()
    def export_character(character: str, job_id: str, frame_set: str = "12f") -> dict:
        """Bundle every QA-passed animation of a job into ONE .aseprite (a tag per facing x action, so
        Unity's Aseprite Importer makes one clip each) plus an atlas PNG + JSON. Returns file paths,
        included animations and anything skipped (QA failures)."""
        from .core.profile import resolve
        from .export import character as char_export
        job = job_for(character, job_id)
        prof = resolve(job.read_meta()["inputs"].get("profile"))
        out = char_export.export(job.root, job.stage_dir("06_export") / "character", character, prof.fps, frame_set)
        job.set_stage("export:character", "done", **{k: out[k] for k in ("animations", "skipped", "mode", "colours")})
        return out

    @mcp.tool()
    def stack(character: str, job_id: str, height: int = 24, regenerate_views: bool = True,
              seed: int | None = None) -> dict:
        """Sprite stacking for a rigid prop/vehicle (approved anchor = front view): queue orthographic
        back/right/top views, then carve them into `height` horizontal slices + turntable GIF + an
        8-angle rotation sheet. regenerate_views=False rebuilds from existing views (CPU only, seconds).
        Hollow shapes come out solid; the left side mirrors the right."""
        job = job_for(character, job_id)
        if regenerate_views and job.read_meta()["stages"].get("anchor", {}).get("status") != "approved":
            raise ValueError("the anchor is not approved yet; show it to the human first")
        ts = q.submit_stack_pipeline(job.root, views=regenerate_views, height=height, seed=seed)
        return {"character": character, "job_id": job_id, "tasks": [t["id"] for t in ts]}

    @mcp.tool()
    def animate_all(character: str, job_id: str, actions: list[str], facings: list[str] | None = None,
                    mirror: bool = True, seconds: float = 2.0) -> dict:
        """Queue many facings x actions at once (default: all 8 facings). With mirror=True, W/NW/SW
        are flipped from E/NE/SE (exact pixels, no render). Needs approved facings."""
        job = job_for(character, job_id)
        facings = facings or list(ORDER)
        bad = [f for f in facings if f not in ORDER]
        if bad:
            raise ValueError(f"unknown facings {bad}")
        if job.read_meta()["inputs"].get("prompt_writer") != "ai":
            for a in actions:
                builder.action_spec(a)
        if job.read_meta()["stages"].get("facings", {}).get("status") != "approved":
            raise ValueError("facings are not approved yet; show them to the human first")
        ts = q.submit_animate(job.root, facings, actions, mirror=mirror, seconds=seconds)
        return {"character": character, "job_id": job_id, "tasks": len(ts),
                "mirrored": sorted({t["args"]["facing"] for t in ts if t["stage"] == "mirror"})}

    @mcp.tool()
    def approve(character: str, job_id: str, stage: str) -> dict:
        """Mark a stage approved ('anchor' or 'facings'). ONLY call this after the human has looked at
        the output (status with include_images) and said yes; never approve on your own judgement."""
        gen.approve(job_for(character, job_id), stage)
        return {"approved": stage}

    @mcp.tool()
    def status(character: str | None = None, job_id: str | None = None, wait_seconds: float = 0,
               include_images: bool = False) -> list:
        """Without a job: list jobs and open queue tasks. With character+job_id: stage statuses,
        output file paths, facing drift, per-action QA verdicts, open/failed tasks.
        wait_seconds (max 900): block until this job has no queued or running tasks.
        include_images: also return the anchor / facings sheet / action previews as images."""
        if not (character and job_id):
            jobs = [{"character": p.parent.parent.name, "job_id": p.parent.name,
                     "stages": {k: v["status"] for k, v in json.loads(p.read_text())["stages"].items()}}
                    for p in sorted(base.glob("*/*/job.json"))]
            from .core import motion as motion_lib
            motions = [{k: m[k] for k in ("name", "status", "action", "facing", "frames")} for m in motion_lib.list_all(base)]
            return [json.dumps({"jobs": jobs, "motions": motions, "open_tasks": open_tasks()}, indent=1)]
        job = job_for(character, job_id)
        deadline = time.time() + min(max(wait_seconds, 0), 900)
        while open_tasks(job) and time.time() < deadline:
            time.sleep(2)
        meta = job.read_meta()
        r = job.root
        fr = r / "02_facings" / "facings_report.json"
        actions = {}
        for d in sorted((r / "03_actions").glob("*/*")):
            if d.is_dir():
                key = f"{d.parent.name}/{d.name}"
                qa = {}
                for n in ("12f", "24f"):
                    rp = r / "05_qa" / d.parent.name / d.name / n / "report.json"
                    if rp.exists():
                        rep = json.loads(rp.read_text())
                        qa[n] = {k: rep[k] for k in ("status", "errors", "warnings", "reroll")}
                exp = r / "06_export" / d.parent.name / d.name
                actions[key] = {"qa": qa, "exports": sorted(str(p) for p in exp.glob("*/*") if p.suffix in (".png", ".aseprite", ".gif", ".json"))}
        failed = [t for t in q.list("failed") if Path(t["job"]).resolve() == r][-5:]
        st_dir = r / "06_export" / "stack"
        stack_out = sorted(str(p) for p in st_dir.glob("*")) if st_dir.is_dir() else []
        out = {"character": character, "job_id": job_id, "inputs": meta["inputs"],
               "stages": {k: v["status"] for k, v in meta["stages"].items()},
               "anchor": str(r / "01_anchor" / "anchor.png") if (r / "01_anchor" / "anchor.png").exists() else None,
               "facings": json.loads(fr.read_text())["facings"] if fr.exists() else {},
               "actions": actions, "open_tasks": [{k: t[k] for k in ("id", "stage", "status", "args")} for t in open_tasks(job)],
               "recent_failures": [{k: t[k] for k in ("id", "stage", "error")} for t in failed],
               "stack": stack_out}
        result: list = [json.dumps(out, indent=1, default=str)]
        if include_images:
            for p in [r / "01_anchor" / "anchor.png", r / "02_facings" / "facings_sheet.png"]:
                if p.exists():
                    result.append(thumb(p))
            for gif in sorted(r.glob("06_export/*/*/12f/*_preview.gif"))[:6]:
                result.append(thumb(gif, 256))
            for rot in sorted(r.glob("06_export/stack/*_rotations.png"))[:1]:
                result.append(thumb(rot, 1024))
        return result

    return mcp, q


def main(base: str | None = None) -> None:
    mcp, q = build(base)
    worker = Worker(q)
    try:
        worker.start()
    except RuntimeError:
        worker = None                      # the web UI or a CLI worker already runs the queue
    try:
        mcp.run("stdio")
    finally:
        if worker:
            worker.stop()
