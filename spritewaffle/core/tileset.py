"""Local, source-preserving tilesets with a rectangular atlas and per-tile collision."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image

from ..export import receipt
from . import fsutil
from .job import Job

TYPE = "tileset"
DIRECTORY = "01_tileset"
RECORD = f"{DIRECTORY}/tileset.json"
MAX_BYTES = 16 * 1024**2
MAX_DIMENSION = 4096
MAX_TILES = 4096
FILES = ("tiles.png", "tileset.json", "tileset.tsj")


def create(base: Path, name: str, job_id: str | None = None) -> Job:
    for value in (name, job_id) if job_id is not None else (name,):
        if (not isinstance(value, str) or not value or value.startswith("_") or value.endswith((".", " "))
                or any(c in value for c in '/\\:*?"<>|\0')):
            raise ValueError("Use a plain name for the tileset and job ID.")
    base = base.resolve()
    target = base / name / (job_id or '.')
    if not target.resolve().is_relative_to(base):
        raise ValueError("The tileset must stay inside the jobs folder.")
    job = Job.create(name, job_id, base, asset_type=TYPE)
    _workspace(job)
    return job


def _workspace(job: Job) -> Path:
    if job.read_meta()["inputs"].get("asset_type") != TYPE:
        raise ValueError("Choose a tileset job.")
    directory = job.root / DIRECTORY
    if not directory.resolve().is_relative_to(job.root.resolve()):
        raise ValueError("Tileset files must stay inside the job.")
    return directory


def _read(directory: Path) -> dict | None:
    try:
        record = json.loads(fsutil.read_text(directory / "tileset.json"))
    except FileNotFoundError:
        return None
    if (not isinstance(record, dict) or record.get("version") != 1
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("digest")))):
        raise ValueError("The tileset record has an unsupported format.")
    grid = record.get("grid")
    if (not isinstance(grid, dict) or any(type(grid.get(key)) is not int or not 1 <= grid[key] <= MAX_DIMENSION
                                          for key in ("width", "height"))
            or _grid((grid["width"], grid["height"]), grid) != grid):
        raise ValueError("The stored tileset grid is invalid.")
    for key in ("empty_tiles", "solid_tiles"):
        ids = record.get(key)
        if not isinstance(ids, list) or any(type(i) is not int or not 0 <= i < grid["columns"] * grid["rows"] for i in ids):
            raise ValueError("The stored tile IDs are invalid.")
    return record


def _revision(record: dict) -> str:
    return sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()


def _source(directory: Path, record: dict) -> Path:
    path = directory / "sources" / (record["digest"] + ".png")
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("The tileset source must stay inside the job.")
    return path


def _grid(size: tuple[int, int], values: dict) -> dict:
    if not isinstance(values, dict):
        raise ValueError("Enter a tile width, tile height, margin, and spacing.")
    width, height = size
    tw, th = values.get("tile_width"), values.get("tile_height")
    margin, spacing = values.get("margin", 0), values.get("spacing", 0)
    if any(type(v) is not int for v in (tw, th, margin, spacing)) or min(tw, th) < 1 or min(margin, spacing) < 0:
        raise ValueError("Tile dimensions must be positive integers. Margin and spacing must be zero or greater.")
    cols, right = divmod(width - 2 * margin + spacing, tw + spacing)
    rows, bottom = divmod(height - 2 * margin + spacing, th + spacing)
    if min(cols, rows) < 1 or right or bottom:
        raise ValueError(f"The grid must fit the {width} × {height} PNG exactly. Check tile size, margin, and spacing.")
    if rows * cols > MAX_TILES:
        raise ValueError(f"A tileset can have at most {MAX_TILES} tiles.")
    return dict(width=width, height=height, columns=cols, rows=rows, tile_width=tw, tile_height=th,
                margin=margin, spacing=spacing)


def _rectangles(grid: dict):
    w, h, m, s = (grid[key] for key in ("tile_width", "tile_height", "margin", "spacing"))
    for row in range(grid["rows"]):
        for col in range(grid["columns"]):
            yield m + col * (w + s), m + row * (h + s), w, h


def import_bytes(job: Job, data: bytes, filename: str, values: dict) -> dict:
    from . import manifest

    directory = _workspace(job)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Choose a PNG no larger than 16 MiB.")
    try:
        with Image.open(BytesIO(data), formats=["PNG"]) as image:
            if max(image.size) > MAX_DIMENSION or getattr(image, "is_animated", False):
                raise ValueError("Choose a still PNG no larger than 4096 × 4096 pixels.")
            grid = _grid(image.size, values)
            alpha = image.convert("RGBA").getchannel("A")
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("Choose a valid PNG tile sheet.") from error
    empty = [i for i, (x, y, w, h) in enumerate(_rectangles(grid)) if not alpha.crop((x, y, x + w, y + h)).getbbox()]
    digest = sha256(data).hexdigest()
    name = str(filename or "tiles.png").replace("\\", "/").rsplit("/", 1)[-1]
    record = {"version": 1, "digest": digest, "filename": name[:255], "grid": grid,
              "empty_tiles": empty, "solid_tiles": []}
    directory.mkdir(exist_ok=True)
    with fsutil.locked(directory / ".workspace.lock", "This tileset is being written. Try again."):
        previous = _read(directory)
        if previous and (previous["digest"], previous["grid"]) == (digest, grid):
            record["solid_tiles"] = previous["solid_tiles"]
        elif previous:
            history = directory / "history"
            history.mkdir(exist_ok=True)
            fsutil.write_text(history / (_revision(previous) + ".json"), json.dumps(previous, indent=2))
        path = _source(directory, record)
        path.parent.mkdir(exist_ok=True)
        if receipt.digest(path) != digest:
            fsutil.write_bytes(path, data)
        fsutil.write_text(directory / "tileset.json", json.dumps(record, indent=2))
    job.set_stage("tileset", "done")
    manifest.refresh(job)
    return inspect(job)


def import_file(job: Job, path: Path, values: dict) -> dict:
    with path.open("rb") as source:
        return import_bytes(job, source.read(MAX_BYTES + 1), path.name, values)


def collision(job: Job, tile: int, solid: bool, revision: str | None = None) -> dict:
    directory = _workspace(job)
    if not directory.is_dir():
        raise ValueError("Import a tile sheet first.")
    with fsutil.locked(directory / ".workspace.lock", "This tileset is being written. Try again."):
        record = _read(directory)
        if not record:
            raise ValueError("Import a tile sheet first.")
        if revision is not None and revision != _revision(record):
            raise ValueError("The tileset changed. Reload it before editing collision.")
        grid = record["grid"]
        if type(solid) is not bool or type(tile) is not int or not 0 <= tile < grid["columns"] * grid["rows"]:
            raise ValueError("Choose a tile in the grid and set collision to true or false.")
        ids = set(record["solid_tiles"])
        (ids.add if solid else ids.discard)(tile)
        record["solid_tiles"] = sorted(ids)
        fsutil.write_text(directory / "tileset.json", json.dumps(record, indent=2))
    return inspect(job)


def _snapshot(job: Job, directory: Path, record: dict) -> dict:
    return receipt.snapshot(job.root, [_source(directory, record)],
                            {key: record[key] for key in ("grid", "solid_tiles")})


def inspect(job: Job) -> dict:
    directory = _workspace(job)
    record = _read(directory)
    if record is None:
        return {"tileset": None, "revision": None, "preview": None, "export": {"status": "missing"}, "files": {}}
    out = job.root / "06_export" / TYPE
    path = out.with_name(".tileset.receipt")
    saved = receipt.load(path)
    files = {name: (out / name).relative_to(job.root).as_posix() for name in FILES if (out / name).is_file()}
    state = {"status": "untracked" if files or path.exists() else "missing"}
    if saved:
        state = {"status": "incomplete"} if saved.get("incomplete") else receipt.compare(
            saved, out, _snapshot(job, directory, record))
    source = _source(directory, record)
    return {"tileset": record, "revision": _revision(record),
            "preview": source.relative_to(job.root).as_posix() if source.is_file() else None,
            "export": state, "files": files}


def export(job: Job) -> dict:
    directory = _workspace(job)
    if not directory.is_dir():
        raise ValueError("Import a tile sheet first.")
    with fsutil.locked(directory / ".workspace.lock", "This tileset is being written. Try again."):
        record = _read(directory)
        if record is None:
            raise ValueError("Import a tile sheet first.")
        path = _source(directory, record)
        data = path.read_bytes()
        if sha256(data).hexdigest() != record["digest"]:
            raise ValueError("The retained PNG changed. Import a valid tile sheet again.")
        grid = record["grid"]
        ids, blank = set(record["solid_tiles"]), set(record["empty_tiles"])
        rects = list(_rectangles(grid))
        native = {"schema_version": 1, "image": "tiles.png", "grid": grid,
                  "tiles": [{"id": i, "rect": list(rect), "empty": i in blank, "solid": i in ids}
                            for i, rect in enumerate(rects)]}
        w, h = grid["tile_width"], grid["tile_height"]
        collision_layer = {"type": "objectgroup", "draworder": "index", "name": "Collision", "visible": True,
                           "opacity": 1, "x": 0, "y": 0, "objects": [{"id": 1, "name": "", "x": 0, "y": 0,
                               "width": w, "height": h, "rotation": 0, "visible": True}]}
        tiled = {"type": "tileset", "version": "1.10", "name": job.root.parent.name, "image": "tiles.png",
                 "imagewidth": grid["width"], "imageheight": grid["height"], "columns": grid["columns"],
                 "tilecount": len(rects), "tilewidth": w, "tileheight": h, "margin": grid["margin"],
                 "spacing": grid["spacing"], "tiles": [{"id": i, "objectgroup": collision_layer} for i in sorted(ids)]}
        before = _snapshot(job, directory, record)
        if before["files"].get(path.relative_to(job.root).as_posix()) != record["digest"]:
            raise ValueError("The retained PNG changed during export. Import it again.")
        out = job.root / "06_export" / TYPE
        if not out.resolve().is_relative_to(job.root.resolve()):
            raise ValueError("Export files must stay inside the job.")
        out.mkdir(parents=True, exist_ok=True)
        receipt_path = out.with_name(".tileset.receipt")
        receipt.incomplete(receipt_path)
        fsutil.write_bytes(out / FILES[0], data)
        fsutil.write_text(out / FILES[1], json.dumps(native, indent=2))
        fsutil.write_text(out / FILES[2], json.dumps(tiled, indent=2))
        if _read(directory) != record or _snapshot(job, directory, record) != before:
            raise RuntimeError("Tileset inputs changed during export. Export again.")
        receipt.save(receipt_path, out, before, [out / name for name in FILES])
    return inspect(job)
