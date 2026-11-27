"""More than 8 views from a 3D model (docs/PLAN_DIRECTIONAL.md, Myth-style test).

Measured 2026-11-27 (DECISIONS.md): in-between views by image edit fail (small pixel sprites copy their
reference, degree wording turns them around). This route:
1. model: the anchor redrawn as a lit 3D-look render (wording per body plan), TRELLIS.2 builds a mesh
   -> 02_views/model.glb. A ground sheet TRELLIS sometimes adds is removed (mesh3d.drop_floor).
2. views: for every in-between yaw of a 16/24/32-view set, the model is rendered on the CPU at that yaw
   (camera elevation from the job's camera), H3 Image edit redraws that render alone as a sprite in the
   job's style (view words per body plan), and the result is scaled to the anchor's height and put on its
   foot point. Left-facing views are mirrored from their right-facing partners. Written to
   02_facings/views/<yaw>.png and left in review (stage "views"); the eight approved facings are untouched.
Props are not covered: sprite stacks already give them every angle.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from ..prompts import builder, styles
from . import angles, camera, generate
from .job import Job

PLANS = tuple(builder.VIEW_PLANS)
COUNTS = (16, 24, 32)
NOT_FOR = ("prop", "item", "effect", "texture", "tileset")


def plan_of(job: Job) -> str:
    """The job's body plan: its saved choice, else from the asset type (animal -> animal, creature ->
    monster, everything else -> biped)."""
    inputs = job.read_meta()["inputs"]
    if inputs.get("view_plan") in PLANS:
        return inputs["view_plan"]
    return {"animal": "animal", "creature": "monster"}.get(inputs.get("asset_type"), "biped")


def _check(job: Job) -> None:
    t = job.read_meta()["inputs"].get("asset_type", "character")
    if t in NOT_FOR:
        raise ValueError(f"extra 3D views are for characters, creatures and animals; a {t} uses its own tools "
                         "(props: sprite stack)")


def views_dir(job: Job) -> Path:
    return job.root / "02_facings" / "views"


def view_path(job: Job, yaw: float) -> Path:
    return views_dir(job) / f"{angles.norm(yaw):g}.png"


def model(job: Job, client: ComfyClient | None = None, seed: int | None = None, plan: str | None = None) -> dict:
    """Anchor -> 3D-look render -> TRELLIS.2 mesh (02_views/model.glb). Needs the approved anchor."""
    _check(job)
    job.require_approved("anchor")
    if plan is not None:
        if plan not in PLANS:
            raise ValueError(f"body plan must be one of {PLANS}")
        job.update_inputs(view_plan=plan)
    plan = plan_of(job)
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    out = job.stage_dir("02_views")
    seed = generate._seed(seed)
    note = job.read_meta()["inputs"].get("views_note") or ""
    prompt = builder.model_render(plan, note)
    r = client.run_template("facing_multiref", {"prompt": prompt, "ref_images": [job.root / "01_anchor" / "anchor.png"],
                                                "seed": seed}, out / ".r3d")
    shutil.copyfile(r["files"][0], out / "render3d.png")
    job.log_provenance("02_views/render3d.png", template="facing_multiref", values={"prompt": prompt, "seed": seed})
    client.free()                                    # H3 Image holds most of the VRAM; TRELLIS needs it
    m = client.run_template("trellis_mesh", {"ref_images": [out / "render3d.png"], "seed": seed}, out / ".glb")
    glb = next((f for f in m["files"] if str(f).endswith(".glb")), None)
    if not glb:
        raise RuntimeError(f"TRELLIS produced no GLB: {m['files']}")
    shutil.copyfile(glb, out / "model.glb")
    shutil.rmtree(out / ".r3d", ignore_errors=True)
    shutil.rmtree(out / ".glb", ignore_errors=True)
    client.free()
    job.log_provenance("02_views/model.glb", template="trellis_mesh", seed=seed)
    job.set_stage("views_model", "done", seed=seed, plan=plan)
    return {"render": str(out / "render3d.png"), "model": str(out / "model.glb"), "plan": plan}


def _place(sprite: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """The drawn sprite scaled to the anchor's height, its bottom on the anchor's foot line and centred
    where the anchor is. Measured 2026-11-27: drawn at the anchor's own small size H3 lost the view (back
    views drawn as fronts); drawn large and placed, it kept it."""
    ys, xs = (sprite[..., 3] > 0).nonzero()
    ay, ax = (anchor[..., 3] > 0).nonzero()
    if not len(ys) or not len(ay):
        raise ValueError("empty sprite or anchor")
    cut = sprite[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h = int(ay.max() - ay.min() + 1)
    im = Image.fromarray(cut).resize((max(1, round(cut.shape[1] * h / cut.shape[0])), h), Image.LANCZOS)
    out = Image.new("RGBA", (anchor.shape[1], anchor.shape[0]), (0, 255, 0, 255))
    cx = (int(ax.min()) + int(ax.max())) // 2
    out.alpha_composite(im, (int(cx - im.width / 2), int(ay.max() + 1 - h)))
    return np.array(out)


def yaws_for(count: int) -> list[float]:
    """The views a count adds to the eight (the eight keep their approved facings)."""
    if count not in COUNTS:
        raise ValueError(f"view count must be one of {COUNTS}")
    return [y for y in angles.views(count) if angles.label(y) not in angles.LEGACY]


def views(job: Job, count: int = 16, client: ComfyClient | None = None, seed: int | None = None,
          only: list[float] | None = None, mirror: bool = True) -> dict:
    """Draw the in-between views of a `count`-view set from the 3D model. Left in review."""
    from ..stack import mesh3d
    _check(job)
    job.require_approved("facings")
    glb = job.root / "02_views" / "model.glb"
    if not glb.exists():
        raise FileNotFoundError("no 3D model yet: run the 3D model step first")
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    inputs = job.read_meta()["inputs"]
    plan, note, desc = plan_of(job), inputs.get("views_note") or "", inputs.get("description") or ""
    elev = camera.snapshot(job)["camera_elevation_degrees"]
    anchor = generate._rgba(job.root / "01_anchor" / "anchor.png")
    pos, col, faces, floor = mesh3d.drop_floor(*mesh3d.read_glb(glb))
    want = [angles.norm(y) for y in (only or yaws_for(count))]
    out = views_dir(job)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".work"
    report_p = out / "views_report.json"
    report = json.loads(report_p.read_text(encoding="utf-8")) if report_p.exists() else {"views": {}}
    report.update({"view_count": count, "plan": plan, "floor_faces_removed": floor, "warnings": []})
    drawn = [y for y in want if not (mirror and 0 < y < 180 and angles.mirror_of(y) in want or
                                     mirror and 0 < y < 180 and view_path(job, angles.mirror_of(y)).exists())]
    for y in drawn:
        render = mesh3d.view(pos, col, faces, y, elev, size=anchor.shape[0])
        tmp.mkdir(exist_ok=True)
        Image.fromarray(render).save(tmp / f"{y:g}_render.png")
        # facing away: no description. Measured 2026-11-27 on human/body1_vest_cloak: its description
        # (laced front, brass buckle, clasp, 'open at the front') put the front on every back view
        # although the model's render showed the cloak from behind
        prompt = builder.view_from_model(y, plan, desc if (y < 90 or y > 270) else "", note)
        r = client.run_template("facing_multiref", {"prompt": prompt, "ref_images": [tmp / f"{y:g}_render.png"],
                                                    "seed": generate._seed(seed)}, tmp / f"{y:g}")
        raw = tmp / f"{y:g}_raw.png"
        generate.flatten_background(Image.open(r["files"][0]).convert("RGB"), raw)
        Image.fromarray(_place(generate._rgba(raw), anchor)).convert("RGB").save(view_path(job, y))
        report["views"][f"{y:g}"] = {"drawn": True}
        job.log_provenance(str(view_path(job, y).relative_to(job.root)), template="facing_multiref",
                           values={"prompt": prompt}, yaw=y)
    for y in want:
        if y in drawn:
            continue
        src = angles.mirror_of(y)
        if view_path(job, src).exists():
            Image.open(view_path(job, src)).transpose(Image.FLIP_LEFT_RIGHT).save(view_path(job, y))
            report["views"][f"{y:g}"] = {"mirrored_from": src}
    # checks against the neighbouring approved facings: a copy of one means the view did not turn
    for y in want:
        if not view_path(job, y).exists():
            continue
        v = generate._rgba(view_path(job, y))
        n8 = sorted(angles.LEGACY, key=lambda f: min(abs(angles.LEGACY[f] - y), 360 - abs(angles.LEGACY[f] - y)))[:2]
        turned = {}
        for f in n8:
            fp = job.root / "02_facings" / f"{f}.png"
            if fp.exists():
                turned[f] = round(generate.turned_from(v, generate._rgba(fp)), 1)
        report["views"].setdefault(f"{y:g}", {})["turned_from"] = turned
        if turned and min(turned.values()) < generate.COPY_DIFF:
            report["warnings"].append(f"{y:g}° looks like a copy of {min(turned, key=turned.get)}: re-roll it")
    shutil.rmtree(tmp, ignore_errors=True)
    report_p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    job.update_inputs(view_count=count)
    job.set_stage("views", "review", view_count=count, drawn=[f"{y:g}" for y in drawn], plan=plan)
    return report
