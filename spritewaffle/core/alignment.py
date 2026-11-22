"""Build and verify optional foot-aligned copies of processed frames."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from ..export import receipt
from ..frames import layout, video
from . import camera, fsutil

MAP_KINDS = ("depth", "normal")
METADATA_NAME = "alignment.json"


def map_path(frame: Path, kind: str) -> Path:
    return frame.with_name(f"{frame.stem}_{kind}.png")


def _snapshot(root: Path, files: list[Path], border: int) -> dict:
    maps = [map_path(frame, kind) for frame in files for kind in MAP_KINDS]
    return receipt.snapshot(root, [*files, *maps], {"canvas_border_px": border})


def _derived_images(directory: Path) -> set[Path]:
    return set(video.colour_frames(directory)).union(
        *(directory.glob(f"[0-9][0-9][0-9]_{kind}.png") for kind in MAP_KINDS))


def metadata(directory: Path) -> dict:
    try:
        record = json.loads(fsutil.read_text(directory / "frames_aligned" / METADATA_NAME))
    except (FileNotFoundError, ValueError):
        return {}
    return record if isinstance(record, dict) and record.get("version") == 1 else {}


def _write_png(path: Path, cell: np.ndarray) -> None:
    image = BytesIO()
    Image.fromarray(cell).save(image, format="PNG")
    fsutil.write_bytes(path, image.getvalue())


def frames(directory: Path, originals: list[Path]) -> list[Path]:
    aligned = video.colour_frames(directory / "frames_aligned")
    return aligned if [p.name for p in aligned] == [p.name for p in originals] else []


def status(root: Path, directory: Path, border: int) -> dict:
    path = directory / ".alignment.receipt"
    record = receipt.load(path)
    if record is None:
        return {"status": "incomplete" if path.exists() else "untracked"}
    if record.get("incomplete"):
        return {"status": "incomplete"}
    out = directory / "frames_aligned"
    inputs = _snapshot(root, video.colour_frames(directory / "frames"), border)
    result = receipt.compare(record, out, inputs)
    unrecorded = ({p.name for p in _derived_images(out)} | {METADATA_NAME}) - record["outputs"].keys()
    if unrecorded:
        result.update(status="stale", changed_outputs=sorted(set(result["changed_outputs"]) | unrecorded))
    return result


def rebuild(job, profile, directory: Path, border: int) -> dict:
    out = directory / "frames_aligned"
    if not directory.resolve().is_relative_to(job.root.resolve()) or not out.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Aligned frames must stay inside the job's frame set.")
    path = directory / ".alignment.receipt"
    with receipt.locked(out):
        sources = video.colour_frames(directory / "frames")
        if not sources:
            raise FileNotFoundError(f"No processed frames in {directory.name}.")
        before = _snapshot(job.root, sources, border)
        cells = []
        for source in sources:
            with Image.open(source) as image:
                cells.append(np.array(image.convert("RGBA")))
        aligned, points, warnings, offsets = layout.align_feet_with_offsets(cells, border=border)
        maps = []
        for source, cell, offset in zip(sources, cells, offsets):
            for kind in MAP_KINDS:
                auxiliary = map_path(source, kind)
                if auxiliary.is_file():
                    with Image.open(auxiliary) as image:
                        if image.size != (cell.shape[1], cell.shape[0]):
                            raise ValueError(f"{auxiliary.name} must match the dimensions of {source.name}.")
                    maps.append((auxiliary, offset))
        receipt.incomplete(path)
        out.mkdir(exist_ok=True)
        outputs = [out / source.name for source in sources]
        for file, cell in zip(outputs, aligned):
            _write_png(file, cell)
        for source, (dx, dy) in maps:
            with Image.open(source) as image:
                shifted = layout.translate_rgba(np.array(image.convert("RGBA")), dx, dy)
            file = out / source.name
            _write_png(file, shifted)
            outputs.append(file)
        for file in _derived_images(out) - set(outputs):
            file.unlink()
        points_path = out / "footpoints.json"
        fsutil.write_text(points_path, json.dumps(points))
        transform_path = out / METADATA_NAME
        feet = [point for point in points if point is not None]
        pivot = [round(float(value)) for value in np.median(feet, axis=0)] if feet else None
        fsutil.write_text(transform_path, json.dumps({"version": 1, "pivot": pivot,
                                                     "offsets": dict(zip((p.name for p in sources), offsets))}))
        current_border = camera.effective(job, profile)[0].canvas_border_px
        if before != _snapshot(job.root, video.colour_frames(directory / "frames"), current_border):
            raise RuntimeError("Alignment inputs changed during the rebuild. Re-align feet again.")
        receipt.save(path, out, before, [*outputs, points_path, transform_path])
    return {"frames": len(sources), "foot_point": points[0], "warnings": warnings}
