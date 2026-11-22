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


def _snapshot(root: Path, files: list[Path], border: int) -> dict:
    return receipt.snapshot(root, files, {"canvas_border_px": border})


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
    extra = {p.name for p in video.colour_frames(out)} - record["outputs"].keys()
    if extra:
        result.update(status="stale", changed_outputs=sorted(set(result["changed_outputs"]) | extra))
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
        aligned, points, warnings = layout.align_feet(cells, border=border)
        receipt.incomplete(path)
        out.mkdir(exist_ok=True)
        outputs = [out / source.name for source in sources]
        for file, cell in zip(outputs, aligned):
            image = BytesIO()
            Image.fromarray(cell).save(image, format="PNG")
            fsutil.write_bytes(file, image.getvalue())
        for file in set(video.colour_frames(out)) - set(outputs):
            file.unlink()
        points_path = out / "footpoints.json"
        fsutil.write_text(points_path, json.dumps(points))
        current_border = camera.effective(job, profile)[0].canvas_border_px
        if before != _snapshot(job.root, video.colour_frames(directory / "frames"), current_border):
            raise RuntimeError("Alignment inputs changed during the rebuild. Re-align feet again.")
        receipt.save(path, out, before, [*outputs, points_path])
    return {"frames": len(sources), "foot_point": points[0], "warnings": warnings}
