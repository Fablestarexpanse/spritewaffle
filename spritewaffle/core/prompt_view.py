"""What will be sent to ComfyUI for each stage of a job, what was sent last time, and the parts the
human may edit (Ronan: "access to the prompts").

Editable: the anchor description, a note per facing (or for all facings), and each action's
motion / transition / sound text. The fixed rules (green background, framing, in-place motion,
style wording) are added by the builder around them and are never editable. Building a preview
never runs the AI writer: an action whose AI text isn't written yet shows its preset and says so.
"""
from __future__ import annotations

from ..prompts import builder, styles
from .job import Job
from .profile import resolve
from .takes import latest_provenance

EDITABLE_ACTION = ("motion", "transition", "sound")


def _spec(job: Job, action: str) -> tuple[dict | None, str]:
    inputs = job.read_meta()["inputs"]
    preset = builder.ACTIONS.get(action)
    over = {k: v for k, v in ((inputs.get("action_overrides") or {}).get(action) or {}).items() if v}
    ai = (inputs.get("action_specs") or {}).get(action)
    base = ai if inputs.get("prompt_writer") == "ai" and ai else preset
    if over:
        return (base or {}) | over | {"cyclic": (base or preset or {}).get("cyclic", False)}, "edited"
    if base is ai and ai:
        return ai, "ai"
    if preset:
        return preset, "preset (AI text is written at render time)" if inputs.get("prompt_writer") == "ai" else "preset"
    return None, "missing: write motion and transition text, or turn on the AI writer"


def _used(job: Job, rel: str) -> str | None:
    p = latest_provenance(job, rel)
    v = p.get("values") or {}
    return v.get("prompt") if isinstance(v, dict) else None


def view(job: Job) -> dict:
    meta = job.read_meta()
    inputs = meta["inputs"]
    styles.use(styles.of_job(job))
    prof = resolve(inputs.get("profile"))
    asset_type = inputs.get("asset_type", "character")
    desc = inputs.get("description") or ""
    text = inputs.get("visual_description") if inputs.get("prompt_writer") == "ai" and inputs.get("visual_description") else desc
    anchor = {"description": desc, "visual_description": inputs.get("visual_description"),
              "preview": builder.anchor(text, prof, asset_type=asset_type) if text else None,
              "used": _used(job, "01_anchor/anchor.png")}
    src = latest_provenance(job, "01_anchor/anchor.png").get("source")
    if not anchor["used"] and src:
        anchor["used"] = f"(no prompt: imported from {src})"

    notes = inputs.get("facing_notes") or {}
    from .generate import facing_note
    fac = {}
    for f in builder.CARDINALS + builder.DIAGONALS:
        if f == "S":
            continue
        first, refs = (builder.DIAGONAL_NEAREST[f], []) if f in builder.DIAGONALS else ("S", [])
        fac[f] = {"note": notes.get(f, ""), "preview": builder.facing(f, refs, first, facing_note(job, f)),
                  "used": _used(job, f"02_facings/{f}.png")}

    names = set(builder.ACTIONS) | set(inputs.get("action_overrides") or {}) | set(inputs.get("action_specs") or {})
    names |= {d.name for d in (job.root / "03_actions").glob("*/*") if d.is_dir()}
    acts = {}
    for a in sorted(names):
        spec, source = _spec(job, a)
        used = {}
        for d in sorted((job.root / "03_actions").glob(f"*/{a}")):
            f = d.parent.name
            u = {"transition": _used(job, f"03_actions/{f}/{a}/transition.png"),
                 "video": _used(job, f"03_actions/{f}/{a}/raw.mp4")}
            if any(u.values()):
                used[f] = u
        acts[a] = {"source": source, "spec": {k: (spec or {}).get(k, "") for k in EDITABLE_ACTION + ("cyclic",)},
                   "edited": {k: v for k, v in ((inputs.get("action_overrides") or {}).get(a) or {}).items() if v},
                   "preview": None if not spec else {
                       "transition": builder.transition(a, "S", spec),
                       "video": builder.action_video(a, "S", 2.0, True, spec)},
                   "used": used}
    return {"anchor": anchor, "facing_note_all": notes.get("*", ""), "facings": fac, "actions": acts,
            "writer": inputs.get("prompt_writer") or "template"}


def set_action(job: Job, action: str, fields: dict) -> None:
    """Save the human's text for an action; empty fields fall back to preset/AI. All empty = reset."""
    action = action.strip().lower()
    if not action:
        raise ValueError("action name is empty")
    clean = {k: str(fields.get(k) or "").strip() for k in EDITABLE_ACTION}
    with job.mutate() as meta:
        ov = meta["inputs"].setdefault("action_overrides", {})
        kept = {k: v for k, v in clean.items() if v}
        if kept:
            ov[action] = kept
        else:
            ov.pop(action, None)
    job.log_provenance(f"action_spec/{action}", edited_by="human", **clean)


def set_facing_note(job: Job, facing: str, note: str) -> None:
    if facing != "*" and facing not in builder.VIEW:
        raise ValueError(f"unknown facing '{facing}'")
    with job.mutate() as meta:
        notes = meta["inputs"].setdefault("facing_notes", {})
        if note.strip():
            notes[facing] = note.strip()
        else:
            notes.pop(facing, None)
