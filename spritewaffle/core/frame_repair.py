"""Compare a reprocessed or repositioned frame before saving a timeline replacement."""
from __future__ import annotations

import hashlib
import io
import json
import math
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..frames import layout
from ..pixel import smooth
from ..pixel.grid import Grid
from ..pixel.pipeline import PixelParams, pixelize
from . import manifest, timeline
from .job import Job
from .profile import resolve

DESPILL_MODES = ("profile", "all", "edge")
STALE = "The comparison inputs changed. Please compare again before applying the frame."
RECIPE_ERROR = "The processed frame has no usable grid, scale, or placement record."


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass(frozen=True)
class Draft:
    current: Image.Image
    candidate: bytes
    fingerprint: str
    source_digest: str
    changed: np.ndarray
    inputs: dict[Path, str]
    details: dict

    @property
    def changed_pixels(self) -> int:
        return int(np.count_nonzero(self.changed))

    def require_current_inputs(self) -> None:
        try:
            if all(_hash(path.read_bytes()) == digest for path, digest in self.inputs.items()):
                return
        except OSError:
            pass
        raise RuntimeError(STALE)

    def view(self, include_png: bool) -> dict:
        view = {"fingerprint": self.fingerprint, "width": self.current.width, "height": self.current.height,
                "changed_pixels": self.changed_pixels, **self.details}
        if include_png:
            view["before_png"] = b64encode(_png(self.current)).decode("ascii")
            view["after_png"] = b64encode(self.candidate).decode("ascii")
            mask = Image.new("RGBA", self.current.size, "white")
            mask.putalpha(Image.fromarray(self.changed.astype(np.uint8) * 255))
            view["change_mask_png"] = b64encode(_png(mask)).decode("ascii")
        return view


def _draft(root: Path, current: Image.Image, result: np.ndarray, *, source_digest: str,
           inputs: dict[Path, str], details: dict, provenance: dict) -> Draft:
    changes = np.any(np.asarray(current) != result, axis=2)
    candidate = _png(Image.fromarray(result))
    receipt = {"inputs": {path.relative_to(root).as_posix(): digest for path, digest in inputs.items()},
               "details": details, "provenance": provenance, "candidate": _hash(candidate)}
    fingerprint = _hash(json.dumps(receipt, sort_keys=True).encode("utf-8"))
    return Draft(current, candidate, fingerprint, source_digest, changes, inputs, details)


def _artwork_inputs(frame: timeline.Frame, source_digest: str) -> dict[Path, str]:
    inputs = {frame.source: source_digest}
    if frame.replaced:
        inputs[frame.image] = frame.image.stem
    return inputs


def _repair_art(master: np.ndarray, recipe: dict, size: tuple[int, int], despill: str) -> np.ndarray:
    try:
        if size != (recipe["cell"], recipe["cell"]):
            raise ValueError("The recorded cell differs from this processed frame.")
        placement = recipe["placement"]
        place = layout.Placement(float(placement["scale"]), tuple(placement["crop"]), tuple(placement["paste"]))
        if (len(place.crop) != 4 or len(place.paste) != 2 or not math.isfinite(place.scale)
                or place.scale <= 0 or min(place.crop[2:]) <= 0):
            raise ValueError(RECIPE_ERROR)
        if recipe["method"] == "smooth":
            scale = float(recipe["scale"])
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError(RECIPE_ERROR)
            art = smooth.reprocess_frame(master, scale, despill)
        else:
            grid = recipe["grid"]
            lattice = Grid(int(grid["size"]), int(grid.get("ox", 0)), int(grid.get("oy", 0)))
            scale = float(grid.get("resample", 1.0))
            if lattice.size < 1 or not math.isfinite(scale) or scale <= 0 or not recipe["palette"]:
                raise ValueError(RECIPE_ERROR)
            params = PixelParams(palette=recipe["palette"], outline=recipe["outline"], despill=despill,
                                 alpha_threshold=recipe["alpha_threshold"])
            art = pixelize([master], params, locked_grid=(lattice, scale)).rgba(0)
        return layout._place(art, place, size)
    except (KeyError, TypeError, IndexError, OverflowError, cv2.error) as error:
        raise ValueError(RECIPE_ERROR) from error


def prepare(root: Path, frame_set: Path, frame: str, despill: str = "profile") -> Draft:
    if despill not in DESPILL_MODES:
        raise ValueError("Choose profile, all, or edge for green spill cleanup.")
    selected, current, source_digest, artwork_fingerprint = timeline.frame_artwork(root, frame_set, frame)
    if selected.inserted:
        raise ValueError("An inserted frame has no retained animation master. Edit or replace its pixels instead.")
    facing, action, set_name = frame_set.relative_to(root / "04_pixel").parts
    count = set_name.rstrip("f")
    slot = int(selected.source.stem)
    job_root = root.resolve()
    inputs = _artwork_inputs(selected, source_digest)

    def read(path: Path, missing: str) -> bytes:
        if not path.resolve().is_relative_to(job_root):
            raise ValueError("The reprocessing inputs must be inside this job.")
        try:
            contents = path.read_bytes()
        except FileNotFoundError as error:
            raise FileNotFoundError(missing) from error
        inputs[path] = _hash(contents)
        return contents

    report = json.loads(read(frame_set.parent / "pixel_report.json", "The recorded pixel report is missing."))
    if not isinstance(report, dict):
        raise ValueError("The recorded pixel report must be a JSON object.")
    method = report.get("method")
    if method not in (None, "render", "pixelize", "smooth"):
        raise ValueError(f"Single-frame reprocessing is unavailable for {method} clips. Reprocess the action instead.")
    try:
        source_index = report["sets"][count]["sources"][slot]
    except (TypeError, KeyError, IndexError) as error:
        raise ValueError("The pixel report has no recorded master for this frame.") from error
    if type(source_index) is not int or source_index < 0:
        raise ValueError("The pixel report has no valid master index for this frame.")
    places = json.loads(read(frame_set / "placements.json", "The recorded placement is missing."))
    if not isinstance(places, list) or slot >= len(places):
        raise ValueError("The processed frame has no recorded placement.")

    master = root / "03_actions" / facing / action / f"selected_{count}f" / f"{slot:03d}_src{source_index:05d}.png"
    master_bytes = read(master, f"The retained master PNG is missing for frame {selected.source.name}. Select the source frames again.")
    with Image.open(io.BytesIO(master_bytes), formats=["PNG"]) as image:
        original = np.asarray(image.convert("RGBA" if image.mode == "RGBA" else "RGB"))
    profile = resolve(Job(root).read_meta()["inputs"].get("profile"))
    recipe = manifest.downscale_record(report, places[slot], profile)
    cleanup = recipe["despill"] if despill == "profile" else despill
    result = _repair_art(original, recipe, current.size, cleanup)
    if not result[..., 3].any():
        raise ValueError("Reprocessing produced an empty frame. Check the retained master and crop.")
    details = {"source": master.relative_to(root).as_posix(), "despill": despill, "applied_despill": cleanup}
    provenance = {"operation": "reprocess", "frame": frame, "artwork": artwork_fingerprint, "recipe": recipe}
    return _draft(root, current, result, source_digest=source_digest, inputs=inputs, details=details, provenance=provenance)


def preview(root: Path, frame_set: Path, frame: str, *, despill: str = "profile", include_png: bool = True) -> dict:
    return prepare(root, frame_set, frame, despill).view(include_png)


def prepare_reposition(root: Path, frame_set: Path, frame: str, *, dx: int = 0, dy: int = 0,
                       reference: str | None = None, axes: str = "vertical") -> Draft:
    if type(dx) is not int or type(dy) is not int:
        raise ValueError("Use whole-pixel offsets for frame repositioning.")
    if axes not in ("vertical", "both"):
        raise ValueError("Choose vertical or both axes for foot alignment.")
    if reference is not None:
        if not isinstance(reference, str) or not reference or reference == frame:
            raise ValueError("Choose a different reference frame in this set.")
        if dx or dy:
            raise ValueError("Choose manual offsets or a reference frame.")
    selected, current, source_digest, artwork_fingerprint = timeline.frame_artwork(root, frame_set, frame)
    foot = layout.foot_point(np.asarray(current))
    if foot is None:
        raise ValueError("The selected frame has no visible artwork to reposition.")
    inputs = _artwork_inputs(selected, source_digest)
    provenance = {"operation": "reposition", "frame": frame, "artwork": artwork_fingerprint}
    target = None
    if reference is not None:
        ref, image, ref_source, ref_fingerprint = timeline.frame_artwork(root, frame_set, reference)
        if image.size != current.size:
            raise ValueError("The reference frame has a different cell size.")
        target = layout.foot_point(np.asarray(image))
        if target is None:
            raise ValueError("The reference frame has no visible artwork to align to.")
        inputs.update(_artwork_inputs(ref, ref_source))
        provenance["reference_artwork"] = ref_fingerprint
        dx = round(target[0] - foot[0]) if axes == "both" else 0
        dy = round(target[1] - foot[1])

    left, top, right, bottom = current.getchannel("A").getbbox()
    if left + dx < 0 or top + dy < 0 or right + dx > current.width or bottom + dy > current.height:
        raise ValueError("This offset would clip visible pixels. Choose a smaller offset or another reference frame.")
    result = Image.new("RGBA", current.size)
    result.paste(current, (dx, dy))
    details = {"dx": dx, "dy": dy, "axes": axes, "reference": reference, "foot_before": foot,
               "foot_after": [foot[0] + dx, foot[1] + dy], "foot_reference": target}
    return _draft(root, current, np.asarray(result), source_digest=source_digest, inputs=inputs,
                  details=details, provenance=provenance)


def preview_reposition(root: Path, frame_set: Path, frame: str, *, dx: int = 0, dy: int = 0,
                       reference: str | None = None, axes: str = "vertical", include_png: bool = True) -> dict:
    draft = prepare_reposition(root, frame_set, frame, dx=dx, dy=dy, reference=reference, axes=axes)
    return draft.view(include_png)
