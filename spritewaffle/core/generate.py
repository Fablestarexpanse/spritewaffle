"""Generation stages (Phase 2): anchor -> 4 cardinals -> diagonals -> mirror drifting facings.

Every output is written under the job folder with provenance (template, prompt, seed, refs).
"""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from ..frames import layout
from ..pixel import chroma
from ..pixel.color import srgb_to_oklab
from ..prompts import builder, styles
from . import takes
from .job import Job
from .profile import GameProfile

MIRROR_OF = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW"}


def _seed(seed: int | None) -> int:
    return seed if seed is not None else random.randrange(2**31)


def _run(client: ComfyClient, job: Job, slot: str, values: dict, dest: Path, *,
         project_reference_id: str | None = None) -> dict:
    """One image generation. A project/asset camera profile adds its sentence to the prompt here, so
    every still (anchor, facings, items, variants) gets it; none set -> the prompt is unchanged."""
    from . import camera
    extra = camera.prompt_sentence(job)
    if extra and isinstance(values.get("prompt"), str):
        values = {**values, "prompt": f"{values['prompt'].rstrip()} {extra}"}
    tmp = dest.parent / f".{dest.stem}_tmp"
    prov = client.run_template(slot, values, tmp)
    src = Path(prov["files"][0])
    dest.parent.mkdir(parents=True, exist_ok=True)
    takes.stash(job, dest)                         # a re-roll keeps the take it replaces
    flatten_background(Image.open(src).convert("RGB"), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    prov["files"] = [str(dest.relative_to(job.root))]
    prov["values"] = {k: (str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v)
                      for k, v in prov["values"].items()}
    if project_reference_id is not None:
        prov["project_reference_id"] = project_reference_id
    job.log_provenance(str(dest.relative_to(job.root)), **prov, camera=camera.snapshot(job))
    return prov


def flatten_background(img: Image.Image, dest: Path) -> Path:
    """Rule 3: background becomes exact #00FF00. Edit models amplify an off-green background when a
    generated still is fed back as a reference (measured: speckled green noise), so every still is
    keyed and re-composited on pure green before it is saved or reused."""
    a = chroma.key(np.array(img), despill="all")
    out = np.where(a[..., 3:] > 0, a[..., :3], np.array([0, 255, 0], np.uint8)).astype(np.uint8)
    Image.fromarray(out).save(dest)
    return dest


# --- anchor ---------------------------------------------------------------------------------

def anchor_reference(base: Path, reference_id: str, *, description: str | None, asset_type: str = "character",
                     image: str | Path | None = None, style_ref: str | Path | None = None) -> Path:
    """Resolve a selected library image for a new generation."""
    from . import project_references
    if image or style_ref:
        raise ValueError("Choose one project reference, hero reference, or import image for the anchor.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Describe the anchor to generate with this project reference.")
    if asset_type in ("animal", "base_body"):
        raise ValueError("Animals and base bodies use a turnaround sheet. Choose an asset with single-anchor generation.")
    return project_references.image(base, reference_id, active_only=True)


def anchor(job: Job, profile: GameProfile, client: ComfyClient | None = None, description: str | None = None,
           image: str | Path | None = None, seed: int | None = None, asset_type: str = "character",
           style_ref: str | Path | None = None, project_reference_id: str | None = None) -> Path:
    """Generate the anchor from a description, or import an existing image. Not approved yet.

    style_ref: an approved hero anchor (path or job folder). The new anchor is drawn in the hero's
    style through the image-edit template ("hero asset first, then reference it").
    project_reference_id: one active image in the project's library, used through that template."""
    styles.use(styles.of_job(job))
    builder.asset(asset_type)
    ref = (anchor_reference(job.root.parent.parent, project_reference_id, description=description,
                            asset_type=asset_type, image=image, style_ref=style_ref) if project_reference_id is not None else None)
    dest = job.stage_dir("01_anchor") / "anchor.png"
    if image:
        takes.stash(job, dest)
        flatten_background(Image.open(image).convert("RGB"), dest)
        job.log_provenance(str(dest.relative_to(job.root)), source=str(image))
    else:
        if not description:
            raise ValueError("anchor needs --describe or --image")
        client = client or ComfyClient()
        if style_ref or ref is not None:
            if ref is None:
                ref = Path(style_ref)
                if ref.is_dir():
                    hero = Job.open(ref)
                    hero.require_approved("anchor")
                    ref = hero.root / "01_anchor" / "anchor.png"
                if not ref.exists():
                    raise FileNotFoundError(f"style reference {ref} not found")
            _run(client, job, "facing_multiref",
                 {"prompt": builder.anchor_from_hero(description, profile, asset_type, project_reference=project_reference_id is not None),
                  "ref_images": [ref], "seed": _seed(seed)}, dest, project_reference_id=project_reference_id)
        elif asset_type in ("animal", "base_body"):
            return _turnaround(job, profile, description, client, seed, asset_type)
        else:
            text = description
            if job.read_meta()["inputs"].get("prompt_writer") == "ai":
                text = _ai_description(job, description, asset_type, client)
            _run(client, job, "anchor_still",
                 {"prompt": builder.anchor(text, profile, asset_type=asset_type), "seed": _seed(seed)}, dest)
    job.update_inputs(description=description, asset_type=asset_type, style_ref=str(style_ref) if style_ref else None)
    with job.mutate() as meta:                         # a new anchor invalidates AI text written for the old one
        if project_reference_id is None:
            meta["inputs"].pop("project_reference_id", None)
        else:
            meta["inputs"]["project_reference_id"] = project_reference_id
            meta["inputs"].pop("style_ref", None)
        meta["inputs"].pop("visual_description", None)
        meta["inputs"].pop("action_specs", None)
    if job.read_meta()["inputs"].get("prompt_writer") == "ai":
        _ai_visual_description(job, dest, asset_type, client)
    job.set_stage("anchor", "review")
    return dest


# --- AI prompt writer (optional, per job: inputs.prompt_writer == "ai") -------------------------

def _ai_description(job: Job, idea: str, asset_type: str, client) -> str:
    """Strict expansion of a short idea; on any failed check the user's own text is used."""
    from ..prompts import writer
    try:
        text = writer.describe(idea, asset_type, client=client)
        job.log_provenance("01_anchor/description", writer="qwen3vl_4b", idea=idea, description=text)
        return text
    except writer.WriterError as e:
        job.log_provenance("01_anchor/description", writer="qwen3vl_4b", fallback=str(e), description=idea)
        return idea


def _ai_visual_description(job: Job, image: Path, asset_type: str, client) -> str | None:
    """Canonical description read off the anchor image; later prompts name the same details."""
    from ..prompts import writer
    try:
        text = writer.describe("", asset_type, image=image, client=client)
    except writer.WriterError as e:
        job.log_provenance("visual_description", writer="qwen3vl_4b", fallback=str(e))
        return None
    job.update_inputs(visual_description=text)
    job.log_provenance("visual_description", writer="qwen3vl_4b", description=text)
    return text


def resolve_action_spec(job: Job, action_name: str, client=None) -> dict:
    """The motion/transition/sound text for this job's action. Template preset, or (AI writer on)
    one spec written once per character + action from the S facing and cached on the job, so all
    facings share it. Known actions keep their preset loop flag; a failed check falls back to the
    preset. New action names need the AI writer."""
    from ..prompts import writer
    inputs = job.read_meta()["inputs"]
    preset = builder.actions_for(inputs.get("asset_type")).get(action_name)
    override = {k: v for k, v in ((inputs.get("action_overrides") or {}).get(action_name) or {}).items() if v not in (None, "")}
    if override:                                  # the human's own text wins over preset and AI
        base = dict(preset or (inputs.get("action_specs") or {}).get(action_name) or {})
        spec = base | override | {"source": "edited"}
        spec.setdefault("cyclic", bool(preset and preset["cyclic"]))
        missing = [k for k in ("motion", "transition") if not spec.get(k)]
        if missing:
            raise ValueError(f"action '{action_name}' needs {' and '.join(missing)} text (Animations -> Prompts)")
        return spec
    if inputs.get("prompt_writer") != "ai":
        if preset is None:
            raise ValueError(f"no preset for action '{action_name}'; known: {sorted(builder.actions_for(inputs.get('asset_type')))} "
                             "(turn on the AI prompt writer for new actions)")
        return preset
    cached = (inputs.get("action_specs") or {}).get(action_name)
    if cached:
        return cached
    face = job.root / "02_facings" / "S.png"
    try:
        spec = writer.action_spec(action_name, image=face if face.exists() else None,
                                  description=inputs.get("visual_description", ""), client=client,
                                  cyclic=preset["cyclic"] if preset else None)
    except writer.WriterError as e:
        if preset is None:
            raise RuntimeError(f"AI writer could not write '{action_name}' ({e}); try again or pick a preset action")
        job.log_provenance(f"action_spec/{action_name}", writer="qwen3vl_4b", fallback=str(e))
        return preset
    spec["writer"] = "qwen3vl_4b"
    with job.mutate() as meta:
        meta["inputs"].setdefault("action_specs", {})[action_name] = spec
    job.log_provenance(f"action_spec/{action_name}", **spec)
    return spec


def approve(job: Job, stage: str) -> None:
    meta = job.read_meta()
    if stage not in meta["stages"]:
        raise ValueError(f"stage {stage} has not run")
    job.set_stage(stage, "approved", **{k: v for k, v in meta["stages"][stage].items() if k not in ("status", "time")})


# --- facings --------------------------------------------------------------------------------

def _rgba(path: Path) -> np.ndarray:
    return chroma.key(np.array(Image.open(path).convert("RGB")))


COPY_DIFF = 15.0    # below this a facing is a copy of its reference, not a turn (see turned_from)


def turned_from(rgba: np.ndarray, ref_rgba: np.ndarray) -> float:
    """How different a facing is from the picture it was drawn from: mean RGB difference of the two
    sprites, each cropped and scaled to 64x96. Measured 2026-11-20: facings that did not turn
    (top-down diagonals, the side-view knight's NW) score 7-13; real turns 22-86."""
    def norm(a):
        ys, xs = np.where(a[..., 3] > 0)
        if not len(ys):
            return np.zeros((96, 64, 4), float)
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return np.array(Image.fromarray(a).resize((64, 96), Image.BOX)).astype(float)
    a, b = norm(rgba), norm(ref_rgba)
    m = (a[..., 3] > 0) | (b[..., 3] > 0)
    if not m.any():
        return 0.0
    return float(np.abs(a[..., :3] * (a[..., 3:] > 0) - b[..., :3] * (b[..., 3:] > 0))[m].mean())


def drift(anchor_rgba: np.ndarray, rgba: np.ndarray, bins: int = 6) -> dict:
    """How far a facing strays from the anchor: colour-distribution distance (0..1, Oklab histogram
    of opaque pixels) and silhouette height ratio."""
    def hist(img):
        m = img[..., 3] > 0
        if not m.any():
            return np.zeros(bins ** 3), 0
        lab = srgb_to_oklab(img[m][:, :3].astype(float))
        lo, hi = np.array([0, -0.4, -0.4]), np.array([1, 0.4, 0.4])
        q = np.clip(((lab - lo) / (hi - lo) * bins).astype(int), 0, bins - 1)
        h = np.bincount(q[:, 0] * bins * bins + q[:, 1] * bins + q[:, 2], minlength=bins ** 3).astype(float)
        ys = np.where(m.any(1))[0]
        return h / h.sum(), ys[-1] - ys[0] + 1
    ha, la = hist(anchor_rgba)
    hb, lb = hist(rgba)
    return {"color": round(float(np.abs(ha - hb).sum() / 2), 3), "height_ratio": round(lb / la, 3) if la else 0.0}


def _drifted(d: dict, max_color: float, height_tol: float) -> bool:
    return d["color"] > max_color or abs(d["height_ratio"] - 1) > height_tol


def _turnaround(job: Job, profile: GameProfile, description: str, client: ComfyClient,
                seed: int | None, asset_type: str = "animal") -> Path:
    """Animals and base bodies: one turnaround sheet (5 views) cut apart with SAM 3 -> anchor (front)
    + facings, W/SW/NW mirrored. Both stages are left in review. Measured 2026-11-21: a plain base
    body drawn one facing at a time only turned its head (7 of 7 flagged as copies); on a sheet every
    view turned."""
    from . import sheet_import
    sheet_dir = job.stage_dir("01_anchor") / "sheet"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    seed = _seed(seed)
    body = asset_type == "base_body"
    text = builder.turnaround(f"{description.strip().rstrip('.')}, {builder.BASE_BODY_WEAR}" if body else description,
                              profile, asset_type)
    prov = client.run_template("anchor_still", {"prompt": text, "seed": seed}, sheet_dir / ".tmp")
    sheet = sheet_dir / "turnaround.png"
    Image.open(prov["files"][0]).convert("RGB").save(sheet)
    job.log_provenance("01_anchor/sheet/turnaround.png", template="anchor_still", values={"prompt": text, "seed": seed})
    job.update_inputs(description=description, asset_type=asset_type)
    res = sheet_import.import_sheet(job, sheet, list(builder.TURNAROUND_VIEWS), subject="character" if body else "animal",
                                    client=client)
    job.set_stage("anchor", "review", source="turnaround sheet", seed=seed)
    job.set_stage("facings", "review", source="turnaround sheet", mirrored=res["mirrored"], missing=res["missing"])
    return job.root / "01_anchor" / "anchor.png"


def facing_note(job: Job, f: str) -> str:
    """The human's extra detail for facing f: the note for all facings, then the one for f."""
    notes = job.read_meta()["inputs"].get("facing_notes") or {}
    return " ".join(n.strip().rstrip(".") + "." for n in (notes.get("*"), notes.get(f)) if n and n.strip()).rstrip(".")


def facings(job: Job, profile: GameProfile, client: ComfyClient | None = None, only: list[str] | None = None,
            seed: int | None = None, mirror: str = "auto", diagonals: str = "nearest",
            max_color: float = 0.35, height_tol: float = 0.12) -> dict:
    """Staged facings (rule 4): cardinals from the anchor, then diagonals from anchor + cardinals,
    then mirror any facing that drifted when its partner did not (code, not prompts)."""
    if job.read_meta()["inputs"].get("asset_type") in ("animal", "base_body") and not only:
        raise ValueError("animals and base bodies get their facings from the turnaround sheet: re-roll the anchor to draw a new "
                         "sheet (all views at once), or re-roll single facings with only=...")
    if job.read_meta()["inputs"].get("asset_type") == "item":   # equipment: front + back only
        from . import item
        return item.facings(job, profile, client, seed=seed)
    if job.read_meta()["inputs"].get("base_job"):          # a variant: every facing from the base's
        from . import variant
        return variant.facings(job, profile, client, only=only, seed=seed)
    styles.use(styles.of_job(job))
    job.require_approved("anchor")
    client = client or ComfyClient()
    a_path = job.root / "01_anchor" / "anchor.png"
    out = job.stage_dir("02_facings")
    flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")   # the approved anchor IS the S facing
    want = [f for f in (builder.CARDINALS + builder.DIAGONALS)[: 4 if profile.directions == 4 else 8]]
    todo = [f for f in want if f != "S" and (not only or f in only)]
    report = {"diagonals": diagonals, "facings": {}, "mirrored": {}, "warnings": []}
    # per-asset mirror policy (docs/MANIFEST.md); legacy = the behaviour below, unchanged
    inputs = job.read_meta()["inputs"]
    policy = inputs.get("mirror_policy") or "legacy"
    flip_from = {}
    if policy in ("mirror_left_from_right", "custom"):
        from . import angles
        for f in want:
            src = angles.mirror_source(angles.yaw_of(f), policy, inputs.get("mirror_map"), n=profile.directions)
            if src is not None and angles.label(src) in want:
                flip_from[f] = angles.label(src)
    elif policy == "none":
        mirror = "off"
    todo = [f for f in todo if f not in flip_from]

    for f in [x for x in todo if x in builder.CARDINALS] + [x for x in todo if x in builder.DIAGONALS]:
        if f in builder.DIAGONALS and diagonals == "nearest":
            first, refs = builder.DIAGONAL_NEAREST[f], []
        else:
            first, refs = "S", list(builder.DIAGONAL_REFS.get(f, ()))
        missing = [r for r in [first] + refs if not (out / f"{r}.png").exists()]
        if missing:
            raise RuntimeError(f"{f} needs cardinals {missing} first")
        imgs = [out / f"{first}.png"] + [out / f"{r}.png" for r in refs]
        _run(client, job, "facing_multiref",
             {"prompt": builder.facing(f, refs, first, facing_note(job, f), raised=profile.projection != "side",
                                       animal=job.read_meta()["inputs"].get("asset_type") == "animal"), "ref_images": imgs, "seed": _seed(seed)},
             out / f"{f}.png")

    for f, src in flip_from.items():                  # policy: flipped, never rendered
        if f == "S" or (only and f not in only and src not in only):
            continue
        if not (out / f"{src}.png").exists():
            raise RuntimeError(f"{f} is flipped from {src} (mirror policy {policy}); generate {src} first")
        takes.stash(job, out / f"{f}.png")
        Image.open(out / f"{src}.png").transpose(Image.FLIP_LEFT_RIGHT).save(out / f"{f}.png")
        report["mirrored"][f] = {"from": src, "policy": policy}
        job.log_provenance(f"02_facings/{f}.png", mirrored_from=src, reason=f"mirror_policy {policy}")
    a = _rgba(a_path)
    asym = layout.asymmetry(a)
    if asym["asymmetric"]:
        report["warnings"].append((f"anchor is asymmetric (silhouette {asym['silhouette']:.2f}, colour {asym['color']:.2f}): "
                                  "mirrored facings will flip that detail (a bag or weapon swaps sides); "
                                  "untick mirroring on the Animations tab to render W/NW/SW instead"))
    for f in want:
        p = out / f"{f}.png"
        if p.exists():
            report["facings"][f] = drift(a, _rgba(p))

    if mirror == "auto" and profile.mirror_allowed:
        for f, d in list(report["facings"].items()):
            partner = MIRROR_OF.get(f)
            pd = report["facings"].get(partner)
            if partner and pd and _drifted(d, max_color, height_tol) and not _drifted(pd, max_color, height_tol):
                img = Image.open(out / f"{partner}.png")
                takes.stash(job, out / f"{f}.png")         # the drifted render stays available
                img.transpose(Image.FLIP_LEFT_RIGHT).save(out / f"{f}.png")
                report["mirrored"][f] = {"from": partner, "drift_before": d}
                report["facings"][f] = drift(a, _rgba(out / f"{f}.png"))
                job.log_provenance(f"02_facings/{f}.png", mirrored_from=partner, reason="drift", drift=d)
    for f, d in report["facings"].items():
        if _drifted(d, max_color, height_tol):
            report["warnings"].append(f"{f} still drifts from the anchor {d}: re-roll it")
    # a facing that didn't turn: a near-copy of the picture it was drawn from
    report["turned"] = {}
    for f in want:
        ref = "S" if f in builder.CARDINALS else builder.DIAGONAL_NEAREST[f]
        p, rp = out / f"{f}.png", out / f"{ref}.png"
        if f == "S" or f in report["mirrored"] or not (p.exists() and rp.exists()):
            continue
        t = round(turned_from(_rgba(p), _rgba(rp)), 1)
        report["turned"][f] = t
        if t < COPY_DIFF:
            report["warnings"].append(f"{f} looks like a copy of {ref} (difference {t}): it didn't turn; re-roll it")
    if profile.projection != "side" and profile.directions == 8:
        report["warnings"].append("8 directions under a top-down / isometric camera: diagonals often come out as "
                                  "copies of their neighbour. 4 directions with W mirrored from E works (Sizes…)")

    (out / "facings_report.json").write_text(json.dumps(report, indent=2))
    sheet = [np.array(Image.open(out / f"{f}.png").convert("RGB")) for f in want if (out / f"{f}.png").exists()]
    from ..frames import contact
    contact.write(sheet, out / "facings_sheet.png", labels=[f for f in want if (out / f"{f}.png").exists()],
                  cols=4, cell=256)
    job.set_stage("facings", "review", mirrored=list(report["mirrored"]), warnings=report["warnings"])
    return report



# --- actions (Phase 2 step 2) ----------------------------------------------------------------

def _run_video(client: ComfyClient, job: Job, slot: str, values: dict, dest: Path) -> dict:
    tmp = dest.parent / f".{dest.stem}_tmp"
    prov = client.run_template(slot, values, tmp)
    vids = [Path(f) for f in prov["files"] if Path(f).suffix.lower() in (".mp4", ".webm", ".mov")]
    if not vids:
        raise RuntimeError(f"{slot} produced no video: {prov['files']}")
    takes.stash(job, dest)
    dest.unlink(missing_ok=True)
    shutil.move(str(vids[0]), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    prov["files"] = [str(dest.relative_to(job.root))]
    prov["values"] = {k: str(v) if isinstance(v, Path) else v for k, v in prov["values"].items()}
    job.log_provenance(str(dest.relative_to(job.root)), **prov)
    return prov


def _video_frames(path: Path) -> list[np.ndarray]:
    from ..frames import video
    return video.read_frames(path)


def action(job: Job, profile: GameProfile, facing: str, action_name: str, client: ComfyClient | None = None,
           seconds: float = 2.0, mode: str = "fl2va", seed: int | None = None) -> dict:
    """Transition pose (rule 5) -> H3 clip -> frozen check with I2V fallback (rule 7) -> extract.

    Cyclic actions use the transition pose as first AND last frame; one-shot actions end on the
    idle facing. Every still is flattened to exact #00FF00 first."""
    styles.use(styles.of_job(job))
    from ..frames import analysis
    from . import stages
    job.require_approved("facings")
    client = client or ComfyClient()
    spec = resolve_action_spec(job, action_name, client)
    face = job.root / "02_facings" / f"{facing}.png"
    if not face.exists():
        raise FileNotFoundError(f"facing {facing} not generated")
    d = job.action_dir(facing, action_name)
    report = {"facing": facing, "action": action_name, "mode": mode, "seconds": seconds,
              "spec": {k: spec[k] for k in ("motion", "transition", "sound", "cyclic") if k in spec} | {"writer": spec.get("writer", "template")}}

    first = face
    if spec["transition"]:
        first = d / "transition.png"
        _run(client, job, "transition_pose", {"prompt": builder.transition(action_name, facing, spec),
                                              "ref_images": [face], "seed": _seed(seed)}, first)
    last = first if spec["cyclic"] else face
    frames = round(seconds * 24)
    raw = d / "raw.mp4"
    if spec.get("end") == "free" and not spec["cyclic"]:
        # the action changes the character (a thrown shield is gone): ending on the facing picture
        # would put it back. Measured 2026-11-21: "throw shield" with FL2VA had the shield back on the
        # arm from frame 6.
        mode = "i2v"
        report["end"] = "free (no last frame)"
    if mode == "fl2va":
        _run_video(client, job, "h3_action_fl2va",
                   {"prompt": builder.action_video(action_name, facing, seconds, True, spec), "first_frame": first,
                    "last_frame": last, "frames": frames, "seed": _seed(seed)}, raw)
        frozen, diff = analysis.is_frozen(_video_frames(raw))
        report["fl2va_frozen"] = {"frozen": frozen, "mean_diff": round(diff, 3)}
        if frozen:                                   # rule 7: same first/last frame can freeze the clip
            kept = d / "raw_frozen_fl2va.mp4"
            kept.unlink(missing_ok=True)
            raw.rename(kept)
            mode = "i2v"
            report["fallback"] = "frozen FL2VA -> regenerated as I2V; ending picked from footage (loop search)"
    if mode == "i2v":
        _run_video(client, job, "h3_action_i2v",
                   {"prompt": builder.action_video(action_name, facing, seconds, False, spec), "first_frame": first,
                    "frames": frames, "seed": _seed(seed)}, raw)
    report["extract"] = stages.extract(job, raw, facing, action_name)
    report["mode_used"] = mode
    (d / "action_report.json").write_text(json.dumps(report, indent=2, default=str))
    job.set_stage(f"action:{facing}/{action_name}", "review", mode=mode, frozen=report["extract"]["frozen"])
    return report


def bridge(job: Job, a: Path, b: Path, dest: Path, client: ComfyClient | None = None, seed: int | None = None,
           method: str = "video", seconds: float = 1.0) -> Path:
    """In-between pose of two stills (e.g. last selected frame -> first, or action end -> idle).

    method='video' (default): a short FL2VA clip from A to B, middle frame kept. Measured: the image
    edit ('image', bridge_frame slot) copies Picture 2's pose instead of interpolating."""
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if method == "image":
        _run(client, job, "bridge_frame",
             {"prompt": builder.bridge(), "ref_images": [Path(a), Path(b)], "seed": _seed(seed)}, dest)
        return dest
    clip = dest.with_suffix(".mp4")
    _run_video(client, job, "h3_action_fl2va", {"prompt": builder.bridge_video(seconds), "first_frame": Path(a),
                                                "last_frame": Path(b), "frames": round(seconds * 24),
                                                "seed": _seed(seed)}, clip)
    frames = _video_frames(clip)
    flatten_background(Image.fromarray(frames[len(frames) // 2]), dest)
    job.log_provenance(str(dest.relative_to(job.root)), bridge_clip=str(clip.relative_to(job.root)),
                       frame=len(frames) // 2, of=len(frames))
    return dest


# --- motion transfer (experimental, TARA) -------------------------------------------------------

TRANSFER_MAX_DRIFT = 0.35      # same line as facing re-rolls


def transfer(job: Job, profile: GameProfile, facing: str, action_name: str, motion_name: str,
             client: ComfyClient | None = None, size: int = 768, steps: int = 8, seed: int | None = None) -> dict:
    """EXPERIMENTAL: render an action by transferring an approved library motion (TARA) onto this
    job's approved facing, then extract like any action. Identity is checked against the facing:
    colour drift above TRANSFER_MAX_DRIFT is reported as a warning (measured best case ~0.35)."""
    styles.use(styles.of_job(job))
    from ..frames import analysis
    from . import motion, stages
    job.require_approved("facings")
    base = job.root.parent.parent
    m = motion.get(motion_name, base)
    if m["status"] != "approved":
        raise RuntimeError(f"motion '{motion_name}' is {m['status']}; approve it first")
    face = job.root / "02_facings" / f"{facing}.png"
    if not face.exists():
        raise FileNotFoundError(f"facing {facing} not generated")
    d = job.action_dir(facing, action_name)
    raw = d / "raw.mp4"
    frames = m["frames"] - ((m["frames"] - 5) % 17)          # 17n+5, never longer than the clip
    _run_video(client or ComfyClient(), job, "h3_tara_transfer",
               {"prompt": builder.motion_transfer(), "ref_images": [face], "ref_video": Path(m["clip"]),
                "frames": frames, "width": size, "height": size, "steps": steps, "seed": _seed(seed)}, raw)
    vid = _video_frames(raw)
    face_rgba = _rgba(face)
    drifts = [drift(face_rgba, chroma.key(vid[i]))["color"] for i in range(0, len(vid), max(1, len(vid) // 7))]
    report = {"experimental": True, "mode_used": "tara", "facing": facing, "action": action_name,
              "motion": motion_name, "size": size, "steps": steps, "frames": frames,
              "identity_drift": {"mean": round(float(np.mean(drifts)), 3), "max": round(float(max(drifts)), 3)},
              "warnings": []}
    if report["identity_drift"]["mean"] > TRANSFER_MAX_DRIFT:
        report["warnings"].append(f"identity drift {report['identity_drift']['mean']} > {TRANSFER_MAX_DRIFT}: "
                                  "the transfer is losing the character; re-roll (seed) or render with H3")
    report["extract"] = stages.extract(job, raw, facing, action_name)
    (d / "action_report.json").write_text(json.dumps(report, indent=2, default=str))
    job.set_stage(f"action:{facing}/{action_name}", "review", mode="tara", motion=motion_name,
                  identity_drift=report["identity_drift"], warnings=report["warnings"])
    return report
