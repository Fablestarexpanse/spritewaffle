"""spritewaffle command line.

Run `spritewaffle -h` for the grouped command list, `spritewaffle <command> -h` for details.
Known errors print one line and exit 1; add --debug for the full traceback.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, paths
from .comfy.client import DEFAULT_URL
from .core import stages
from .core.job import Job
from .core.profile import GameProfile, resolve

FACINGS = ("S", "E", "N", "W", "SE", "NE", "NW", "SW")

OVERVIEW = """\
setup         doctor, profile, comfy
character     anchor -> approve -> facings -> approve -> animate (or action) -> export-character
              also: mirror, bridge, archive
props         anchor --asset-type prop -> approve -> ortho -> stack   (sprite stacking)
video->art    run (all of): extract, sheet, select, pixelize, qa, export
motion lib    motion, transfer (TARA), flow (pixel-exact)          [experimental]
services      ui (web app), worker, queue, mcp

Typical start:  spritewaffle doctor   then   spritewaffle ui
"""


# --- helpers ----------------------------------------------------------------------------------

def _job(path: str, create: bool = False) -> Job:
    """A job folder; `<character>/<job_id>` is resolved under the jobs folder. Only commands that
    start a job pass create=True; everywhere else a typo is an error, not a new empty job."""
    p = Path(path)
    if not p.is_absolute() and not (p / "job.json").exists() and not p.parts[0] == paths.jobs().name:
        p = paths.jobs() / p
    if (p / "job.json").exists():
        return Job.open(p)
    if len(p.parts) >= 2 and create:
        return Job.create(p.parent.name, p.name, base=p.parent.parent)
    if len(p.parts) >= 2:
        import difflib
        known = [f"{d.parent.name}/{d.name}" for d in paths.jobs().glob("*/*") if (d / "job.json").exists()]
        near = difflib.get_close_matches(f"{p.parent.name}/{p.name}", known, n=3, cutoff=0.6)
        hint = f"; did you mean {', '.join(near)}?" if near else " (start one with `spritewaffle anchor --job ...`)"
        raise FileNotFoundError(f"no such job: {path}{hint}")
    raise SystemExit(f"error: --job must be <character>/<job_id> (got {path})")


def _profile(a, job: Job | None = None) -> GameProfile:
    """--profile if given, else the profile recorded on the job, else the built-in default."""
    name = getattr(a, "profile", None)
    if not name and job is not None:
        name = job.read_meta()["inputs"].get("profile")
    return resolve(name)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _kv(items) -> dict:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def _csv(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _task_line(t) -> str:
    dep = f" after {','.join(t['after'])}" if t["after"] else ""
    err = f"  !! {t['error']}" if t.get("error") and t["status"] == "failed" else ""
    return f"{t['id']}  {t['status']:<9} {t['resource']}  {t['stage']:<8} {t['job']} {json.dumps(t['args'])}{dep}{err}"


# --- setup ------------------------------------------------------------------------------------

def cmd_doctor(a):
    from . import doctor
    rows = doctor.check(a.url)
    print(doctor.render(rows))
    return 1 if any(s == doctor.FAIL for s, _, _ in rows) else 0


def cmd_profile(a):
    from .core.profile import list_all
    if a.sub == "list":
        for n in list_all():
            print(n)
        print("(default)  built-in, used when a job has no profile")
    elif a.sub == "show":
        from dataclasses import asdict
        _print(asdict(resolve(a.name)))
    else:
        p = GameProfile(name=a.name, projection=a.projection, cell_size=a.cell, sprite_height_px=a.height,
                        palette=a.palette, outline=a.outline, directions=a.directions)
        print(p.save(paths.profiles() / f"{a.name}.json"))


def cmd_comfy_check(a):
    from .comfy import templates
    from .comfy.client import ComfyClient
    c = ComfyClient(a.url)
    _print(c.check())
    for slot in ([a.template] if a.template else templates.SLOTS):
        if not (paths.templates() / f"{slot}.json").exists():
            print(f"{slot}: no template exported yet")
            continue
        try:
            miss = c.missing_nodes(templates.load(slot)[0])
            print(f"{slot}: {'OK' if not miss else 'missing nodes ' + str(miss)}")
        except ValueError as e:
            print(f"{slot}: {e}")


# --- character --------------------------------------------------------------------------------

def cmd_anchor(a):
    from .core import generate
    job = _job(a.job, create=True)
    if a.profile:
        job.update_inputs(profile=a.profile)
    print(generate.anchor(job, _profile(a, job), description=a.describe, image=a.image, seed=a.seed,
                          asset_type=a.asset_type, style_ref=a.style_ref))


def cmd_sheet_import(a):
    from .core import sheet_import
    job = _job(a.job, create=True)
    if a.style:
        from .prompts import styles
        job.update_inputs(style=styles.get(a.style)["name"])
    _print(sheet_import.import_sheet(job, a.image, _csv(a.views), subject=a.subject, mirror=not a.no_mirror))
    print("next: look at 02_facings, then `spritewaffle approve anchor` and generate any missing facings with "
          "`spritewaffle facings --only ...`")


def cmd_approve(a):
    from .core import generate
    generate.approve(_job(a.job), a.stage)
    print(f"{a.stage}: approved")


def cmd_facings(a):
    from .core import generate
    job = _job(a.job)
    _print(generate.facings(job, _profile(a, job), only=_csv(a.only), seed=a.seed, mirror=a.mirror,
                            diagonals=a.diagonals))


def cmd_action(a):
    from .core import generate
    job = _job(a.job)
    _print(generate.action(job, _profile(a, job), a.facing, a.action, seconds=a.seconds, mode=a.mode, seed=a.seed))


def cmd_animate(a):
    from .core.queue import Queue
    facings = _csv(a.facings) or list(FACINGS)
    bad = [f for f in facings if f not in FACINGS]
    if bad:
        raise ValueError(f"unknown facings {bad}; use {','.join(FACINGS)}")
    job = _job(a.job)
    args = {"seconds": a.seconds} if not a.motion else {}
    ts = Queue().submit_animate(job.root, facings, _csv(a.actions), a.profile, mirror=not a.no_mirror,
                                motion=a.motion, method=a.method, **args)
    for t in ts:
        print(_task_line(t))
    print(f"\nqueued {len(ts)} tasks; run `spritewaffle worker` or keep `spritewaffle ui` open")


def cmd_style(a):
    from .prompts import styles
    job = _job(a.job)
    job.update_inputs(style=styles.get(a.style)["name"])
    print(f"style: {a.style} ({styles.STYLES[a.style]['label']}); generate a new anchor to see it")


def cmd_palette(a):
    from .core import job_palette
    job = _job(a.job)
    prof = _profile(a, job)
    if a.file:
        job_palette.save(job, job_palette.load_file(a.file), f"file {Path(a.file).name}")
    elif a.rebuild:
        job_palette.clear(job)
        cols = job_palette.from_stills(job, prof)
        if not cols:
            raise FileNotFoundError("no anchor or facing stills to build from")
        job_palette.save(job, cols, f"anchor + facings ({len(job_palette.stills(job))} stills)")
    elif a.unlock:
        job_palette.clear(job)
        print("unlocked: the next pixelize builds it again from the anchor + facings")
    from .prompts import styles
    if styles.get(styles.of_job(job))["post"] != "pixel":
        print(f"style '{styles.of_job(job)}' is full colour: no palette is used (--apply still re-lays out every clip)")
    cur = job_palette.get(job)
    if isinstance(prof.palette, list):
        print(f"profile '{prof.name}' locks its own {len(prof.palette)}-colour palette (it wins over the job's)")
    if cur:
        print(f"job palette: {len(cur['colours'])} colours from {cur['source']}")
        print(" ".join(cur["colours"]))
    elif not a.unlock:
        print("no job palette yet: the next pixelize builds it from the anchor + facings")
    stale = [c for c in job_palette.clips(job) if cur and c["colours"] and c["colours"] != len(cur["colours"])]
    if a.apply:
        from .core.queue import Queue
        ts = Queue(paths.jobs()).submit_reprocess(job.root, a.profile)
        print(f"queued {len(ts)} tasks: every clip re-pixelized with this palette, then QA + export")
    elif stale or (cur and (a.file or a.rebuild)):
        print("clips made before this palette keep their old colours: add --apply to re-process them (no rendering)")


def cmd_writer(a):
    job = _job(a.job)
    job.update_inputs(prompt_writer=a.mode)
    print(f"prompt writer: {a.mode}")


def cmd_prompts(a):
    """Template text vs AI text for one action, side by side (nothing is rendered)."""
    from .core import generate
    from .prompts import builder
    job = _job(a.job)
    rows = []
    if a.action in builder.ACTIONS:
        rows.append(("template", builder.ACTIONS[a.action]))
    mode = job.read_meta()["inputs"].get("prompt_writer")
    job.update_inputs(prompt_writer="ai")
    try:
        rows.append(("ai", generate.resolve_action_spec(job, a.action)))
    finally:
        job.update_inputs(prompt_writer=mode or "template")
    for who, spec in rows:
        print(f"[{who}]")
        for k in ("motion", "transition", "sound", "cyclic"):
            print(f"  {k:<10} {spec.get(k)}")
        print()
    vd = job.read_meta()["inputs"].get("visual_description")
    if vd:
        print(f"[ai] visual description: {vd}")


def cmd_mirror(a):
    job = _job(a.job)
    _print(stages.mirror_action(job, _profile(a, job), a.facing, a.action, a.source))


def cmd_bridge(a):
    from .core import generate
    job = _job(a.job)
    dest = job.action_dir(a.facing, a.action) / "bridges" / f"{a.name}.png"
    print(generate.bridge(job, a.a, a.b, dest, seed=a.seed, method=a.method))


def cmd_export_character(a):
    from .export import character
    job = _job(a.job)
    prof = _profile(a, job)
    out = character.export(job.root, job.stage_dir("06_export") / "character", job.read_meta()["character"],
                           prof.fps, a.set, require_pass=not a.include_failed, max_size=a.max_size, mirror=a.mirror)
    job.set_stage("export:character", "done", pages=len(out["pages"]), mirror=a.mirror,
                  **{k: out[k] for k in ("animations", "skipped", "mode", "colours")})
    _print(out)


def cmd_showcase(a):
    from .export import showcase
    job = _job(a.job)
    _print(showcase.for_job(job, _profile(a, job), size=a.size, frame_set=a.set))


def cmd_archive(a):
    print(f"archived to {_job(a.job).archive()}")


def cmd_manifest(a):
    """Write asset manifests (docs/MANIFEST.md): one job, or every job (the migration)."""
    from .core import manifest
    if a.job:
        job = _job(a.job)
        print(manifest.write(job) if a.rebuild or not manifest.path(job).exists() else f"kept {manifest.path(job)}")
        return
    counts = {}
    for job, st in manifest.migrate(paths.jobs(), rebuild=a.rebuild):
        counts[st.split(":")[0]] = counts.get(st.split(":")[0], 0) + 1
        print(f"{job.root.parent.name}/{job.root.name}: {st}")
    print(", ".join(f"{v} {k}" for k, v in counts.items()) or "no jobs")


# --- props ------------------------------------------------------------------------------------

def cmd_ortho(a):
    from .stack import stage
    _print(stage.ortho(_job(a.job), seed=a.seed, only=_csv(a.only)))


def cmd_stack(a):
    from .stack import stage
    job = _job(a.job)
    _print(stage.build(job, _profile(a, job), stack_height=a.height, layer_px=a.layer_px))


# --- video -> pixel art -----------------------------------------------------------------------

def cmd_run(a):
    job = Job.create(a.character, a.job_id, profile=a.profile)
    prof = _profile(a, job)
    loop = True if a.loop else (False if a.no_loop else None)
    print(f"job: {job.root}")
    rep = stages.extract(job, a.video, a.facing, a.action)
    if rep["frozen"]:
        print(f"warning: clip looks frozen (mean frame diff {rep['mean_frame_diff']}); regenerate without last frame (rule 7)")
    for w in stages.select(job, loop=loop)["warnings"]:
        print("warning:", w)
    px = stages.pixel(job, prof)
    print(f"grid {px['grid']}  palette {len(px['palette'])} colours")
    q = stages.qa(job, prof)
    print(f"qa {q}")
    _print(stages.export(job, prof, fmt="both"))
    return 1 if "fail" in q.values() else 0


def cmd_extract(a):
    _print(stages.extract(_job(a.job, create=True), a.video, a.facing, a.action))


def cmd_sheet(a):
    print(stages.contact_sheet(_job(a.job), a.dir, a.facing, a.action))


def cmd_select(a):
    counts = (a.frames,) if a.frames else (12, 24)
    loop = True if a.loop else (False if a.no_loop else None)
    r = stages.select(_job(a.job), a.facing, a.action, counts=counts, indices=a.indices, loop=loop)
    _print({k: r[k] for k in ("start", "end", "loop", "keys", "warnings")} | {"sets": {k: len(v) for k, v in r["sets"].items()}})


def cmd_pixelize(a):
    job = _job(a.job)
    r = stages.pixel(job, _profile(a, job), a.facing, a.action, palette=a.palette)
    _print({"grid": r["grid"], "palette": r["palette"]})


def cmd_qa(a):
    job = _job(a.job)
    r = stages.qa(job, _profile(a, job), a.facing, a.action)
    _print(r)
    return 1 if "fail" in r.values() else 0


def cmd_export(a):
    job = _job(a.job)
    _print(stages.export(job, _profile(a, job), a.facing, a.action, a.format))


# --- motion library (experimental) ------------------------------------------------------------

def cmd_motion(a):
    from .core import motion
    if a.sub == "add":
        _print(motion.add(a.name, _job(a.job), a.facing, a.action, notes=a.notes or ""))
    elif a.sub == "approve":
        _print(motion.approve(a.name))
    else:
        for m in motion.list_all():
            print(f"{m['name']:<22} {m['status']:<9} {m['action']}/{m['facing']} {m['frames']}f  {m['notes']}")


def cmd_transfer(a):
    from .core import generate
    job = _job(a.job)
    _print(generate.transfer(job, _profile(a, job), a.facing, a.action, a.motion, size=a.size, steps=a.steps, seed=a.seed))


def cmd_flow(a):
    job = _job(a.job)
    _print(stages.flow_transfer(job, _profile(a, job), a.facing, a.action, a.motion))


# --- services ---------------------------------------------------------------------------------

def cmd_queue(a):
    from .core.queue import Queue
    q = Queue()
    if a.sub == "add":
        print(_task_line(q.submit(_job(a.job).root, a.stage, _kv(a.arg), a.profile, _csv(a.after))))
    elif a.sub == "pipeline":
        for t in q.submit_action_pipeline(_job(a.job).root, a.facing, a.action, a.profile, generate=not a.no_generate,
                                          motion=a.motion, method=a.method, **_kv(a.arg)):
            print(_task_line(t))
    elif a.sub == "list":
        for t in q.list(a.status):
            print(_task_line(t))
    elif a.sub == "cancel":
        print(_task_line(q.cancel(a.id)))
    elif a.sub == "retry":
        print(_task_line(q.retry(a.id)))
    elif a.sub == "clear":
        print(f"removed {q.clear(('done', 'cancelled', 'failed') if a.failed else ('done', 'cancelled'))} finished tasks")


def cmd_worker(a):
    import time
    from .core.queue import Queue, Worker
    w = Worker(Queue(), {"gpu": a.gpu, "cpu": a.cpu})
    if a.once:
        w.run_until_idle(force=a.force)
        return 0
    w.start(force=a.force)
    print(f"worker running (gpu {a.gpu}, cpu {a.cpu}) on {paths.jobs()}; Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        w.stop()


def cmd_ui(a):
    from .ui.server import serve
    print(f"SpriteWaffle UI on http://127.0.0.1:{a.port}  (jobs: {paths.jobs()}; Ctrl-C to stop)")
    serve(port=a.port)


def cmd_mcp(a):
    import os
    if a.root:
        os.environ["SPRITEWAFFLE_HOME"] = str(Path(a.root).resolve())
    from .mcp_server import main as mcp_main
    mcp_main()


# --- parser -----------------------------------------------------------------------------------

def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="spritewaffle", description="AI image/video -> game-ready pixel-art sprites.",
                                 epilog=OVERVIEW, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"spritewaffle {__version__}")
    ap.add_argument("--debug", action="store_true", help="show full tracebacks")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def cmd(name, fn, help_, *specs, **kw):
        p = sub.add_parser(name, help=help_, description=help_, **kw)
        for flags, opts in specs:
            p.add_argument(*flags, **opts)
        p.set_defaults(fn=fn)
        return p

    JOB = (("--job",), {"required": True, "help": "job as <character>/<job_id> (or a folder path)"})
    PROFILE = (("--profile",), {"help": "profile name (default: the job's profile, else built-in)"})
    SEED = (("--seed",), {"type": int, "help": "fixed seed (default: random)"})
    FACING = (("--facing",), {"required": True, "choices": FACINGS})
    ACTION = (("--action",), {"required": True, "help": "idle, walk, run, attack, jump"})
    OPT_FACING = (("--facing",), {"choices": FACINGS, "help": "default: the job's last facing"})
    OPT_ACTION = (("--action",), {"help": "default: the job's last action"})

    # setup
    cmd("doctor", cmd_doctor, "check ComfyUI, templates, models, folders and the queue worker",
        (("--url",), {"default": DEFAULT_URL, "help": "ComfyUI address ($SPRITEWAFFLE_COMFY)"}))
    pp = sub.add_parser("profile", help="game profiles: list, show, new").add_subparsers(dest="sub", required=True)
    pp.add_parser("list", help="list saved profiles")
    pp.add_parser("show", help="print one profile").add_argument("name")
    pn = pp.add_parser("new", help="save a new profile")
    pn.add_argument("name")
    pn.add_argument("--projection", default="side", choices=("side", "topdown_34", "iso_2to1"))
    pn.add_argument("--cell", type=int, default=64, help="cell size in px")
    pn.add_argument("--height", type=int, default=48, help="sprite height in art px")
    pn.add_argument("--palette", type=int, default=16, help="max colours")
    pn.add_argument("--outline", default="none", choices=("none", "dark_1px", "selout"))
    pn.add_argument("--directions", type=int, default=8, choices=(4, 8))
    for spp in pp.choices.values():
        spp.set_defaults(fn=cmd_profile)
    cp = sub.add_parser("comfy", help="ComfyUI connection and templates").add_subparsers(dest="sub", required=True)
    cc = cp.add_parser("check", help="connect and validate exported templates")
    cc.add_argument("--url", default=DEFAULT_URL)
    cc.add_argument("--template", help="only this slot")
    cc.set_defaults(fn=cmd_comfy_check)

    # character
    cmd("anchor", cmd_anchor, "generate (or import) the anchor still a character is built from",
        JOB, PROFILE, SEED,
        (("--describe",), {"help": "what the asset looks like"}),
        (("--image",), {"help": "import this image instead of generating"}),
        (("--asset-type",), {"default": "character", "choices": ("character", "creature", "prop")}),
        (("--style-ref",), {"help": "approved hero job (<character>/<job_id>) to copy the art style from"}))
    cmd("sheet-import", cmd_sheet_import, "use YOUR character sheet (views side by side, any background) as anchor + facings",
        (("image",), {}), JOB,
        (("--views",), {"required": True, "help": "facing of each figure left to right, e.g. S,SE,E,N (S becomes the anchor)"}),
        (("--subject",), {"default": "character", "help": "what SAM 3 should cut out, e.g. 'hare character'"}),
        (("--style",), {"help": "set the job's art style too (pixel, painted, anime, comic)"}),
        (("--no-mirror",), {"action": "store_true", "help": "don't flip missing W/SW/NW from E/SE/NE"}))
    cmd("approve", cmd_approve, "mark a stage approved after you've looked at it (anchor, facings, ortho)",
        (("stage",), {}), JOB)
    cmd("facings", cmd_facings, "generate the other 7 facings from the approved anchor",
        JOB, PROFILE, SEED,
        (("--only",), {"help": "re-roll just these, e.g. NW,SW"}),
        (("--mirror",), {"choices": ("auto", "none"), "default": "auto", "help": "mirror a drifting facing from its partner"}),
        (("--diagonals",), {"choices": ("nearest", "multi"), "default": "nearest"}))
    cmd("action", cmd_action, "render one action clip for one facing now (no queue)",
        JOB, PROFILE, FACING, ACTION, SEED,
        (("--seconds",), {"type": float, "default": 2.0}),
        (("--mode",), {"choices": ("fl2va", "i2v"), "default": "fl2va"}))
    cmd("animate", cmd_animate, "queue many facings x actions at once (W/NW/SW mirrored from E/NE/SE)",
        JOB, PROFILE,
        (("--actions",), {"required": True, "help": "comma list, e.g. idle,walk"}),
        (("--facings",), {"help": "comma list (default: all 8)"}),
        (("--seconds",), {"type": float, "default": 2.0}),
        (("--no-mirror",), {"action": "store_true", "help": "render W/NW/SW instead of mirroring"}),
        (("--motion",), {"help": "use this library motion instead of H3 [experimental]"}),
        (("--method",), {"choices": ("tara", "flow"), "default": "flow", "help": "with --motion"}))
    from .prompts.styles import STYLES
    cmd("style", cmd_style, "art style of this job: " + ", ".join(f"{k} ({v['label']})" for k, v in STYLES.items()),
        JOB, (("style",), {"choices": tuple(STYLES)}))
    cmd("palette", cmd_palette, "the job's one palette (all facings and actions share it): show, rebuild, load a file",
        JOB, PROFILE,
        (("--file",), {"help": "load colours from .gpl (Aseprite/GIMP/Lospec), .hex/.txt or an image"}),
        (("--rebuild",), {"action": "store_true", "help": "build it again from the anchor + facing stills"}),
        (("--unlock",), {"action": "store_true", "help": "forget it; the next pixelize builds a new one"}),
        (("--apply",), {"action": "store_true", "help": "queue every existing clip to be re-pixelized with it (no rendering)"}))
    cmd("writer", cmd_writer, "who writes the creative prompt text for this job: template (default) or ai (Qwen3-VL 4B)",
        JOB, (("mode",), {"choices": ("template", "ai")}))
    cmd("prompts", cmd_prompts, "show template vs AI motion text for one action (renders nothing)",
        JOB, ACTION)
    cmd("mirror", cmd_mirror, "make a facing by flipping its partner's finished pixel art (e.g. W from E)",
        JOB, PROFILE, FACING, ACTION, (("--source",), {"choices": FACINGS, "help": "default: the mirror partner"}))
    cmd("bridge", cmd_bridge, "in-between pose of two images (a 1 s clip's middle frame)",
        JOB, FACING, ACTION, SEED,
        (("--a",), {"required": True}), (("--b",), {"required": True}),
        (("--name",), {"default": "bridge"}), (("--method",), {"choices": ("video", "image"), "default": "video"}))
    cmd("export-character", cmd_export_character, "one .aseprite (a tag per animation) + atlas for the whole job",
        JOB, PROFILE, (("--set",), {"default": "12f", "choices": ("12f", "24f")}),
        (("--include-failed",), {"action": "store_true", "help": "also ship animations that failed QA"}),
        (("--max-size",), {"type": int, "default": 4096, "help": "atlas page limit in px (default 4096)"}),
        (("--mirror",), {"choices": ("pack", "flip"), "default": "pack",
                         "help": "flip: leave exact W/NW/SW mirrors out of the atlas; the engine flips E/NE/SE"}))
    cmd("showcase", cmd_showcase, "GIF to show people: turnaround through the facings, then every action in all its facings",
        JOB, PROFILE, (("--size",), {"type": int, "default": 512, "help": "square size in px"}),
        (("--set",), {"default": "12f", "choices": ("12f", "24f")}))
    cmd("archive", cmd_archive, "move a job to jobs/_archive (reversible: move it back)", JOB)
    cmd("manifest", cmd_manifest, "write asset manifests (angles, foot points, maps, masters): one job, or all (migration)",
        (("--job",), {"help": "jobs/<character>/<job_id>; default: every job"}),
        (("--rebuild",), {"action": "store_true", "help": "rewrite manifests that already exist"}))

    # props
    cmd("ortho", cmd_ortho, "sprite stacking: back/right/top views of an approved prop anchor",
        JOB, SEED, (("--only",), {"help": "e.g. top,right"}))
    cmd("stack", cmd_stack, "sprite stacking: carve the 4 views into slices + turntable + rotations",
        JOB, PROFILE, (("--height",), {"type": int, "default": 24, "help": "number of slices"}),
        (("--layer-px",), {"type": int, "default": 1}))

    # video -> pixel art
    cmd("run", cmd_run, "whole video pipeline on an existing clip: extract, select, pixelize, qa, export",
        (("video",), {}), PROFILE, (("--character",), {"required": True}), ACTION, FACING,
        (("--job-id",), {}), (("--loop",), {"action": "store_true"}), (("--no-loop",), {"action": "store_true"}))
    cmd("extract", cmd_extract, "extract every frame of a clip into the job", (("video",), {}), JOB,
        (("--facing",), {"choices": FACINGS, "default": "S"}), (("--action",), {"default": "walk"}))
    cmd("sheet", cmd_sheet, "numbered contact sheet of a frame folder", (("dir",), {}), JOB, OPT_FACING, OPT_ACTION)
    cmd("select", cmd_select, "pick 12f/24f frame sets (start, end, key beats, in-betweens)", JOB, OPT_FACING, OPT_ACTION,
        (("--indices",), {"help": "manual: '1,6,11,17' or '24-48'"}), (("--frames",), {"type": int, "choices": (12, 24)}),
        (("--loop",), {"action": "store_true"}), (("--no-loop",), {"action": "store_true"}))
    cmd("pixelize", cmd_pixelize, "turn the selected frames into pixel art (one palette)", JOB, PROFILE,
        OPT_FACING, OPT_ACTION, (("--palette",), {"type": int, "help": "override max colours"}))
    cmd("qa", cmd_qa, "check the pixel art and write report.json", JOB, PROFILE, OPT_FACING, OPT_ACTION)
    cmd("export", cmd_export, "PNG strip, sheet.json, GIF and .aseprite for one action", JOB, PROFILE, OPT_FACING,
        OPT_ACTION, (("--format",), {"choices": ("png", "aseprite", "both"), "default": "both"}))

    # motion library
    mp = sub.add_parser("motion", help="[experimental] library of approved driving clips").add_subparsers(dest="sub", required=True)
    ma = mp.add_parser("add", help="add a job's rendered clip")
    ma.add_argument("name")
    ma.add_argument("--job", required=True)
    ma.add_argument("--facing", required=True, choices=FACINGS)
    ma.add_argument("--action", required=True)
    ma.add_argument("--notes")
    mp.add_parser("approve", help="approve a motion for use").add_argument("name")
    mp.add_parser("list", help="list motions")
    for spp in mp.choices.values():
        spp.set_defaults(fn=cmd_motion)
    cmd("transfer", cmd_transfer, "[experimental] TARA: render an action from a library motion", JOB, PROFILE,
        FACING, ACTION, SEED, (("--motion",), {"required": True}),
        (("--size",), {"type": int, "default": 768}), (("--steps",), {"type": int, "default": 8}))
    cmd("flow", cmd_flow, "[experimental] pixel-exact: move the facing's pixels with a library motion",
        JOB, PROFILE, FACING, ACTION, (("--motion",), {"required": True}))

    # services
    qp = sub.add_parser("queue", help="background task queue").add_subparsers(dest="sub", required=True)
    qa = qp.add_parser("add", help="queue one stage")
    qa.add_argument("stage")
    qa.add_argument("--job", required=True)
    qa.add_argument("--profile")
    qa.add_argument("--after", help="task ids, comma separated")
    qa.add_argument("--arg", action="append", help="key=value (JSON values allowed), repeatable")
    qpl = qp.add_parser("pipeline", help="queue one action: render -> select -> pixelize -> qa -> export")
    qpl.add_argument("--job", required=True)
    qpl.add_argument("--facing", required=True, choices=FACINGS)
    qpl.add_argument("--action", required=True)
    qpl.add_argument("--profile")
    qpl.add_argument("--no-generate", action="store_true", help="re-process the existing clip only")
    qpl.add_argument("--arg", action="append", help="action args key=value, e.g. seconds=2")
    qpl.add_argument("--motion", help="[experimental] library motion instead of an H3 render")
    qpl.add_argument("--method", choices=("tara", "flow"), default="tara")
    qp.add_parser("list", help="list tasks").add_argument("--status", choices=("queued", "running", "done", "failed", "cancelled"))
    qp.add_parser("cancel", help="cancel a queued task").add_argument("id")
    qp.add_parser("retry", help="queue a failed task again").add_argument("id")
    qp.add_parser("clear", help="remove finished tasks").add_argument("--failed", action="store_true", help="failed ones too")
    for spp in qp.choices.values():
        spp.set_defaults(fn=cmd_queue)
    cmd("worker", cmd_worker, "run queued tasks (the web UI runs one itself)",
        (("--gpu",), {"type": int, "default": 1}), (("--cpu",), {"type": int, "default": 2}),
        (("--once",), {"action": "store_true", "help": "drain the queue and exit"}),
        (("--force",), {"action": "store_true", "help": "take over a live worker's lock"}))
    cmd("ui", cmd_ui, "start the web app on http://127.0.0.1:<port>", (("--port",), {"type": int, "default": 8765}))
    cmd("mcp", cmd_mcp, "MCP server on stdio (for agents)", (("--root",), {"help": "project folder (default: auto)"}))
    return ap


KNOWN_ERRORS = (FileNotFoundError, FileExistsError, ValueError, RuntimeError, KeyError)


def main(argv=None) -> int:
    args = build().parse_args(argv)
    try:
        return args.fn(args) or 0
    except Exception as e:
        from .comfy.client import ComfyError
        if args.debug or not isinstance(e, KNOWN_ERRORS + (ComfyError,)):
            raise
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"error: {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
