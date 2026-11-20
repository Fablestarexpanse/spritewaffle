"""Workflow templates (API-format JSON exported from Ronan's ComfyUI) + parameter-injection maps.

templates/<slot>.json      API-format workflow ({"<node id>": {"class_type", "inputs"}})
templates/<slot>.map.json  {
  "slot": "<slot>",
  "params": {                      # parameter -> where it goes; list = multiple targets/slots
    "prompt": {"node": "6", "input": "text"},
    "first_frame": {"node": "12", "input": "image", "kind": "image"},
    "ref_images": [{"node": "20", "input": "image", "kind": "image"}, ...]
  },
  "output_node": "30"              # node whose /history outputs are downloaded
}
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .. import paths

SLOTS = ("anchor_still", "facing_multiref", "transition_pose", "bridge_frame", "h3_action_fl2va",
         "h3_action_i2v", "h3_turntable", "h3_tara_transfer", "sam3_mask")
PARAMS = ("prompt", "negative", "first_frame", "last_frame", "ref_images", "ref_video", "width", "height",
          "frames", "seed", "steps")
IMAGE_PARAMS = ("first_frame", "last_frame", "ref_images", "ref_video")   # uploaded files


H3_FPS = 24


def snap_h3_frames(n: int) -> int:
    """H3 frame counts live on a 17k+5 grid at 24 fps; return the nearest valid count (>= 5)."""
    k = max(0, round((n - 5) / 17))
    return 17 * k + 5


def empty_map(slot: str) -> dict:
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot}")
    return {"slot": slot, "params": {}, "output_node": None}


def _targets(spec) -> list[dict]:
    return spec if isinstance(spec, list) else [spec]


def validate(workflow: dict, mapping: dict) -> list[str]:
    """Problems with a map against its workflow (empty list = OK)."""
    errs = []
    if mapping.get("slot") not in SLOTS:
        errs.append(f"unknown slot {mapping.get('slot')}")
    for name, spec in mapping.get("params", {}).items():
        if name not in PARAMS:
            errs.append(f"unknown param {name}")
        for t in _targets(spec):
            node = workflow.get(str(t.get("node")))
            if node is None:
                errs.append(f"{name}: node {t.get('node')} not in workflow")
            elif t.get("input") not in node.get("inputs", {}):
                errs.append(f"{name}: node {t['node']} ({node.get('class_type')}) has no input '{t.get('input')}'")
    out = mapping.get("output_node")
    if out is None or str(out) not in workflow:
        errs.append(f"output_node {out} not in workflow")
    return errs


def load(slot: str, base: Path | None = None) -> tuple[dict, dict]:
    base = Path(base) if base else paths.templates()
    wf = json.loads((base / f"{slot}.json").read_text())
    mp = json.loads((base / f"{slot}.map.json").read_text())
    errs = validate(wf, mp)
    if errs:
        raise ValueError(f"template {slot}: " + "; ".join(errs))
    return wf, mp


def inject(workflow: dict, mapping: dict, values: dict) -> dict:
    """Return a copy of workflow with values placed. Image params must already be uploaded names.
    `frames` is snapped to the H3 grid for h3_* slots."""
    wf = copy.deepcopy(workflow)
    for name, value in values.items():
        if value is None:
            continue
        spec = mapping["params"].get(name)
        if spec is None:
            raise KeyError(f"template {mapping['slot']} has no slot for '{name}'")
        if name == "frames" and mapping["slot"].startswith("h3_"):
            value = snap_h3_frames(int(value))
        targets = _targets(spec)
        if name == "ref_images":
            vals = list(value)
            if len(vals) > len(targets):
                raise ValueError(f"{len(vals)} ref images but template has {len(targets)} slots")
            for t, v in zip(targets, vals):
                wf[str(t["node"])]["inputs"][t["input"]] = v
            for t in targets[len(vals):]:
                if not t.get("optional"):
                    raise ValueError(f"template {mapping['slot']} needs at least {targets.index(t) + 1} ref images")
                _prune(wf, str(t["node"]))
        else:
            for t in targets:
                # "as": "seconds" -> the graph takes a duration and snaps it to frames itself
                v = value / H3_FPS if t.get("as") == "seconds" else value
                wf[str(t["node"])]["inputs"][t["input"]] = v
    return wf


def _prune(wf: dict, node: str) -> None:
    """Remove an unused optional node and every input that links to it."""
    wf.pop(node, None)
    for n in wf.values():
        for k in [k for k, v in n["inputs"].items() if isinstance(v, list) and len(v) == 2 and str(v[0]) == node]:
            del n["inputs"][k]


def class_types(workflow: dict) -> set[str]:
    return {n["class_type"] for n in workflow.values()}
