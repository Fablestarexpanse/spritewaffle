"""spritewaffle CLI (Phase 1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import stages
from .core.job import Job
from .core.profile import PROFILES_DIR, GameProfile, resolve


def _job(path: str) -> Job:
    p = Path(path)
    if (p / "job.json").exists():
        return Job.open(p)
    if len(p.parts) >= 2:                      # jobs/<character>/<job_id> -> create it
        return Job.create(p.parent.name, p.name, base=p.parent.parent)
    raise SystemExit(f"--job must be a job folder (jobs/<character>/<job_id>): {path}")


def _profile(args) -> GameProfile:
    return resolve(getattr(args, "profile", None))


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_profile_new(a):
    p = GameProfile(name=a.name, projection=a.projection, cell_size=a.cell, sprite_height_px=a.height,
                    palette=a.palette, outline=a.outline, directions=a.directions)
    print(p.save(PROFILES_DIR / f"{a.name}.json"))


def cmd_extract(a):
    _print(stages.extract(_job(a.job), a.video, a.facing, a.action))


def cmd_sheet(a):
    print(stages.contact_sheet(_job(a.job), a.dir, a.facing, a.action))


def cmd_select(a):
    counts = (a.frames,) if a.frames else (12, 24)
    loop = True if a.loop else (False if a.no_loop else None)
    r = stages.select(_job(a.job), a.facing, a.action, counts=counts, indices=a.indices, loop=loop)
    _print({k: r[k] for k in ("start", "end", "loop", "keys", "warnings")} | {"sets": {k: len(v) for k, v in r["sets"].items()}})


def cmd_pixelize(a):
    r = stages.pixel(_job(a.job), _profile(a), a.facing, a.action, palette=a.palette)
    _print({"grid": r["grid"], "palette": r["palette"]})


def cmd_qa(a):
    r = stages.qa(_job(a.job), _profile(a), a.facing, a.action)
    _print(r)
    return 1 if "fail" in r.values() else 0


def cmd_export(a):
    _print(stages.export(_job(a.job), _profile(a), a.facing, a.action, a.format))


def cmd_run(a):
    job = Job.create(a.character, a.job_id, profile=a.profile)
    prof = _profile(a)
    loop = True if a.loop else (False if a.no_loop else None)
    print(f"job: {job.root}")
    rep = stages.extract(job, a.video, a.facing, a.action)
    if rep["frozen"]:
        print(f"WARNING: clip looks frozen (mean frame diff {rep['mean_frame_diff']}); regenerate without last frame (rule 7)")
    sel = stages.select(job, loop=loop)
    for w in sel["warnings"]:
        print("WARNING:", w)
    px = stages.pixel(job, prof)
    print(f"grid {px['grid']}  palette {len(px['palette'])} colours")
    q = stages.qa(job, prof)
    print(f"qa {q}")
    out = stages.export(job, prof, fmt="both")
    _print(out)
    return 1 if "fail" in q.values() else 0


def cmd_anchor(a):
    from .core import generate
    print(generate.anchor(_job(a.job), _profile(a), description=a.describe, image=a.image, seed=a.seed))


def cmd_approve(a):
    from .core import generate
    generate.approve(_job(a.job), a.stage)
    print(f"{a.stage}: approved")


def cmd_facings(a):
    from .core import generate
    only = a.only.split(",") if a.only else None
    _print(generate.facings(_job(a.job), _profile(a), only=only, seed=a.seed, mirror=a.mirror,
                            diagonals=a.diagonals))


def cmd_action(a):
    from .core import generate
    _print(generate.action(_job(a.job), _profile(a), a.facing, a.action, seconds=a.seconds, mode=a.mode, seed=a.seed))


def cmd_bridge(a):
    from .core import generate
    job = _job(a.job)
    dest = job.action_dir(a.facing, a.action) / "bridges" / f"{a.name}.png"
    print(generate.bridge(job, a.a, a.b, dest, seed=a.seed, method=a.method))


def cmd_comfy_check(a):
    from .comfy import templates
    from .comfy.client import ComfyClient, ComfyError
    c = ComfyClient(a.url)
    try:
        info = c.check()
    except ComfyError as e:
        print(e)
        return 2
    _print(info)
    for slot in ([a.template] if a.template else templates.SLOTS):
        wf_path = templates.TEMPLATES_DIR / f"{slot}.json"
        if not wf_path.exists():
            print(f"{slot}: no template exported yet")
            continue
        try:
            wf, _ = templates.load(slot)
            miss = c.missing_nodes(wf)
            print(f"{slot}: {'OK' if not miss else 'missing nodes ' + str(miss)}")
        except ValueError as e:
            print(f"{slot}: {e}")
    return 0


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="spritewaffle")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def ctx(p, job=True):
        if job:
            p.add_argument("--job", required=True, help="job folder jobs/<character>/<job_id>")
        p.add_argument("--facing")
        p.add_argument("--action")

    pr = sub.add_parser("profile").add_subparsers(dest="sub", required=True).add_parser("new")
    pr.add_argument("name")
    pr.add_argument("--projection", default="side")
    pr.add_argument("--cell", type=int, default=64)
    pr.add_argument("--height", type=int, default=48)
    pr.add_argument("--palette", type=int, default=16)
    pr.add_argument("--outline", default="none")
    pr.add_argument("--directions", type=int, default=8)
    pr.set_defaults(fn=cmd_profile_new)

    p = sub.add_parser("extract"); p.add_argument("video"); ctx(p); p.set_defaults(fn=cmd_extract)
    p.set_defaults(facing="S", action="walk")
    p = sub.add_parser("sheet"); p.add_argument("dir"); ctx(p); p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("select"); ctx(p)
    p.add_argument("--indices", help="'1,6,11,17' or ranges '24-48'")
    p.add_argument("--frames", type=int, choices=(12, 24))
    p.add_argument("--loop", action="store_true"); p.add_argument("--no-loop", action="store_true")
    p.set_defaults(fn=cmd_select)
    p = sub.add_parser("pixelize"); ctx(p); p.add_argument("--palette", type=int); p.add_argument("--profile")
    p.set_defaults(fn=cmd_pixelize)
    p = sub.add_parser("qa"); ctx(p); p.add_argument("--profile"); p.set_defaults(fn=cmd_qa)
    p = sub.add_parser("export"); ctx(p); p.add_argument("--profile")
    p.add_argument("--format", choices=("png", "aseprite", "both"), default="both"); p.set_defaults(fn=cmd_export)
    p = sub.add_parser("run"); p.add_argument("video"); p.add_argument("--profile")
    p.add_argument("--character", required=True); p.add_argument("--action", required=True)
    p.add_argument("--facing", required=True); p.add_argument("--job-id")
    p.add_argument("--loop", action="store_true"); p.add_argument("--no-loop", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("anchor"); p.add_argument("--job", required=True); p.add_argument("--profile")
    p.add_argument("--describe"); p.add_argument("--image"); p.add_argument("--seed", type=int)
    p.set_defaults(fn=cmd_anchor)
    p = sub.add_parser("approve"); p.add_argument("stage"); p.add_argument("--job", required=True)
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("facings"); p.add_argument("--job", required=True); p.add_argument("--profile")
    p.add_argument("--only", help="e.g. E,N"); p.add_argument("--seed", type=int)
    p.add_argument("--mirror", choices=("auto", "none"), default="auto")
    p.add_argument("--diagonals", choices=("nearest", "multi"), default="nearest"); p.set_defaults(fn=cmd_facings)
    p = sub.add_parser("action"); p.add_argument("--job", required=True); p.add_argument("--profile")
    p.add_argument("--facing", required=True); p.add_argument("--action", required=True)
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--mode", choices=("fl2va", "i2v"), default="fl2va")
    p.add_argument("--seed", type=int); p.set_defaults(fn=cmd_action)
    p = sub.add_parser("bridge"); p.add_argument("--job", required=True); p.add_argument("--facing", required=True)
    p.add_argument("--action", required=True); p.add_argument("--a", required=True); p.add_argument("--b", required=True)
    p.add_argument("--name", default="bridge"); p.add_argument("--seed", type=int)
    p.add_argument("--method", choices=("video", "image"), default="video"); p.set_defaults(fn=cmd_bridge)
    c = sub.add_parser("comfy").add_subparsers(dest="sub", required=True).add_parser("check")
    c.add_argument("--url", default="http://127.0.0.1:8188"); c.add_argument("--template")
    c.set_defaults(fn=cmd_comfy_check)
    return ap


def main(argv=None) -> int:
    args = build().parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
