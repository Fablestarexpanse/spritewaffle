"""Compose standalone art and image-space geometry from a saved tile module."""
from __future__ import annotations

from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from . import fsutil, tileset
from .job import Job


def _pivot(value: list | None, width: int, height: int) -> list[int]:
    if value is None:
        return [width // 2, height]
    if (not isinstance(value, list) or len(value) != 2
            or any(type(axis) is not int or not 0 <= axis <= limit
                   for axis, limit in zip(value, (width, height)))):
        raise ValueError(f"Enter whole pixel pivot coordinates inside 0–{width} × 0–{height}.")
    return value


def export(job: Job, name: str, pivot: list | None = None, revision: str | None = None) -> dict:
    with tileset._locked_record(job) as (directory, record):
        if revision is not None and revision != tileset._revision(record):
            raise ValueError("The tileset changed. Reload it before exporting the module.")
        module = tileset._get_module(record, name)
        grid = record["grid"]
        tw, th = grid["tile_width"], grid["tile_height"]
        size = (module["width"] * tw, module["height"] * th)
        point = _pivot(pivot, *size)
        _, original = tileset._export_image(directory, record)
        rects = list(tileset._rectangles(grid))
        solid = set(record["solid_tiles"])
        shapes = record.get("tile_shapes") or {}
        from . import tile_collision as tc
        collision = []
        rendered = Image.new("RGBA", size)
        with Image.open(BytesIO(original)) as image:
            atlas = image.convert("RGBA")
            for row, values in enumerate(module["tiles"]):
                for col, tile in enumerate(values):
                    if tile is None:
                        continue
                    sx, sy, w, h = rects[tile]
                    x, y = col * tw, row * th
                    rendered.paste(atlas.crop((sx, sy, sx + w, sy + h)), (x, y))
                    if tile in solid:
                        box = {"x": x, "y": y, "width": w, "height": h}
                        if shape := shapes.get(str(tile)):          # bounding box + the real polygon
                            pts = [[x + px, y + py] for px, py in tc.polygon(shape, w, h)]
                            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                            box = {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys),
                                   "polygon": pts, **({"one_way": True} if shape.get("one_way") else {})}
                        collision.append(box)
        name = module["name"]
        metadata = {"schema_version": 1, "type": "tile_module", "name": name, "image": "module.png",
                    "size": list(size), "pivot": point, "collision": collision,
                    "coordinate_space": "image_pixels_top_left"}
        key = tileset._revision({"atlas": tileset._atlas_revision(record), "module": module, "export": metadata})
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "module"
        target = job.root / "06_export" / "modules" / f"{slug}-{key[:12]}.zip"
        if not target.resolve().is_relative_to(job.root.resolve()):
            raise ValueError("Module exports must stay inside the tileset job.")
        png, packed = BytesIO(), BytesIO()
        rendered.save(png, format="PNG")
        with ZipFile(packed, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("module.png", png.getvalue())
            archive.writestr("module.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        target.parent.mkdir(parents=True, exist_ok=True)
        fsutil.write_bytes(target, packed.getvalue())
    return {"name": name, "file": target.relative_to(job.root).as_posix(), "pivot": point}
