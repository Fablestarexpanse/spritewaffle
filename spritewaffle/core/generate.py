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
from ..prompts import builder
from .job import Job
from .profile import GameProfile

MIRROR_OF = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW"}


def _seed(seed: int | None) -> int:
    return seed if seed is not None else random.randrange(2**31)


def _run(client: ComfyClient, job: Job, slot: str, values: dict, dest: Path) -> dict:
    tmp = dest.parent / f".{dest.stem}_tmp"
    prov = client.run_template(slot, values, tmp)
    src = Path(prov["files"][0])
    dest.parent.mkdir(parents=True, exist_ok=True)
    flatten_background(Image.open(src).convert("RGB"), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    prov["files"] = [str(dest.relative_to(job.root))]
    prov["values"] = {k: (str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v)
                      for k, v in prov["values"].items()}
    job.log_provenance(str(dest.relative_to(job.root)), **prov)
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

def anchor(job: Job, profile: GameProfile, client: ComfyClient | None = None, description: str | None = None,
           image: str | Path | None = None, seed: int | None = None, asset_type: str = "character",
           style_ref: str | Path | None = None) -> Path:
    """Generate the anchor from a description, or import an existing image. Not approved yet.

    style_ref: an approved hero anchor (path or job folder). The new anchor is drawn in the hero's
    style through the image-edit template ("hero asset first, then reference it")."""
    builder.asset(asset_type)
    dest = job.stage_dir("01_anchor") / "anchor.png"
    if image:
        flatten_background(Image.open(image).convert("RGB"), dest)
        job.log_provenance(str(dest.relative_to(job.root)), source=str(image))
    else:
        if not description:
            raise ValueError("anchor needs --describe or --image")
        client = client or ComfyClient()
        if style_ref:
            ref = Path(style_ref)
            if ref.is_dir():
                hero = Job.open(ref)
                _require_approved(hero, "anchor")
                ref = hero.root / "01_anchor" / "anchor.png"
            if not ref.exists():
                raise FileNotFoundError(f"style reference {ref} not found")
            _run(client, job, "facing_multiref",
                 {"prompt": builder.anchor_from_hero(description, profile, asset_type), "ref_images": [ref],
                  "seed": _seed(seed)}, dest)
        else:
            _run(client, job, "anchor_still",
                 {"prompt": builder.anchor(description, profile, asset_type=asset_type), "seed": _seed(seed)}, dest)
    job.update_inputs(description=description, asset_type=asset_type, style_ref=str(style_ref) if style_ref else None)
    job.set_stage("anchor", "review")
    return dest


def approve(job: Job, stage: str) -> None:
    meta = job.read_meta()
    if stage not in meta["stages"]:
        raise ValueError(f"stage {stage} has not run")
    job.set_stage(stage, "approved", **{k: v for k, v in meta["stages"][stage].items() if k not in ("status", "time")})


def _require_approved(job: Job, stage: str) -> None:
    st = job.read_meta()["stages"].get(stage, {}).get("status")
    if st != "approved":
        raise RuntimeError(f"stage '{stage}' is {st or 'missing'}; approve it first (rule 2: one approved anchor)")


# --- facings --------------------------------------------------------------------------------

def _rgba(path: Path) -> np.ndarray:
    return chroma.key(np.array(Image.open(path).convert("RGB")))


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


def facings(job: Job, profile: GameProfile, client: ComfyClient | None = None, only: list[str] | None = None,
            seed: int | None = None, mirror: str = "auto", diagonals: str = "nearest",
            max_color: float = 0.35, height_tol: float = 0.12) -> dict:
    """Staged facings (rule 4): cardinals from the anchor, then diagonals from anchor + cardinals,
    then mirror any facing that drifted when its partner did not (code, not prompts)."""
    _require_approved(job, "anchor")
    client = client or ComfyClient()
    a_path = job.root / "01_anchor" / "anchor.png"
    out = job.stage_dir("02_facings")
    flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")   # the approved anchor IS the S facing
    want = [f for f in (builder.CARDINALS + builder.DIAGONALS)[: 4 if profile.directions == 4 else 8]]
    todo = [f for f in want if f != "S" and (not only or f in only)]
    report = {"diagonals": diagonals, "facings": {}, "mirrored": {}, "warnings": []}

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
             {"prompt": builder.facing(f, refs, first), "ref_images": imgs, "seed": _seed(seed)}, out / f"{f}.png")

    a = _rgba(a_path)
    asym = layout.asymmetry(a)
    if asym["asymmetric"]:
        report["warnings"].append(f"anchor is asymmetric ({asym}); mirrored facings will flip that detail")
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
                img.transpose(Image.FLIP_LEFT_RIGHT).save(out / f"{f}.png")
                report["mirrored"][f] = {"from": partner, "drift_before": d}
                report["facings"][f] = drift(a, _rgba(out / f"{f}.png"))
                job.log_provenance(f"02_facings/{f}.png", mirrored_from=partner, reason="drift", drift=d)
    for f, d in report["facings"].items():
        if _drifted(d, max_color, height_tol):
            report["warnings"].append(f"{f} still drifts from the anchor {d}: re-roll it")

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
    dest.unlink(missing_ok=True)
    shutil.move(str(vids[0]), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    prov["files"] = [str(dest.relative_to(job.root))]
    prov["values"] = {k: str(v) if isinstance(v, Path) else v for k, v in prov["values"].items()}
    job.log_provenance(str(dest.relative_to(job.root)), **prov)
    return prov


def _video_frames(path: Path) -> list[np.ndarray]:
    import cv2
    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return out


def action(job: Job, profile: GameProfile, facing: str, action_name: str, client: ComfyClient | None = None,
           seconds: float = 2.0, mode: str = "fl2va", seed: int | None = None) -> dict:
    """Transition pose (rule 5) -> H3 clip -> frozen check with I2V fallback (rule 7) -> extract.

    Cyclic actions use the transition pose as first AND last frame; one-shot actions end on the
    idle facing. Every still is flattened to exact #00FF00 first."""
    from ..frames import analysis
    from . import stages
    _require_approved(job, "facings")
    client = client or ComfyClient()
    spec = builder.action_spec(action_name)
    face = job.root / "02_facings" / f"{facing}.png"
    if not face.exists():
        raise FileNotFoundError(f"facing {facing} not generated")
    d = job.action_dir(facing, action_name)
    report = {"facing": facing, "action": action_name, "mode": mode, "seconds": seconds}

    first = face
    if spec["transition"]:
        first = d / "transition.png"
        _run(client, job, "transition_pose", {"prompt": builder.transition(action_name, facing),
                                              "ref_images": [face], "seed": _seed(seed)}, first)
    last = first if spec["cyclic"] else face
    frames = round(seconds * 24)
    raw = d / "raw.mp4"
    if mode == "fl2va":
        _run_video(client, job, "h3_action_fl2va",
                   {"prompt": builder.action_video(action_name, facing, seconds, True), "first_frame": first,
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
                   {"prompt": builder.action_video(action_name, facing, seconds, False), "first_frame": first,
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
    from ..frames import analysis
    from . import motion, stages
    _require_approved(job, "facings")
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
