"""Local tilesets with a retained atlas, collision, terrain, and animation."""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image

from ..export import receipt
from . import fsutil, terrain
from .job import Job

TYPE = "tileset"
DIRECTORY = "01_tileset"
RECORD = f"{DIRECTORY}/tileset.json"
MAX_BYTES = 16 * 1024**2
MAX_DIMENSION = 4096
MAX_TILES = 4096
MAX_ANIMATION_FRAMES = 64
MAX_FRAME_DURATION_MS = 60_000
MAX_MODULES = 64
MAX_MODULE_SIDE = 16
FILES = ("tiles.png", "tileset.json", "tileset.tsj", "tileset.tres")   # .tres: Godot 4 TileSet


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
    count = grid["columns"] * grid["rows"]
    for key in ("empty_tiles", "solid_tiles"):
        ids = record.get(key)
        if not isinstance(ids, list) or any(type(i) is not int or not 0 <= i < count for i in ids):
            raise ValueError("The stored tile IDs are invalid.")
    from . import tile_collision as tc
    tw, th = grid["tile_width"], grid["tile_height"]
    if "tile_shapes" in record:
        shapes = record["tile_shapes"]
        if not isinstance(shapes, dict) or any(not k.isdigit() or int(k) not in record["solid_tiles"] for k in shapes):
            raise ValueError("The stored collision shapes are invalid.")
        record["tile_shapes"] = {k: v for k, v in ((k, tc.clean_shape(v, tw, th)) for k, v in shapes.items()) if v}
    if "tile_properties" in record:
        props = record["tile_properties"]
        if not isinstance(props, dict) or any(not k.isdigit() or not 0 <= int(k) < count for k in props):
            raise ValueError("The stored tile properties are invalid.")
        record["tile_properties"] = {k: tc.clean_properties(v) for k, v in props.items() if v}
    if "tile_probability" in record:
        weights = record["tile_probability"]
        if not isinstance(weights, dict) or any(not k.isdigit() or not 0 <= int(k) < count for k in weights):
            raise ValueError("The stored tile weights are invalid.")
        record["tile_probability"] = {k: _weight(v) for k, v in weights.items()}
    if "terrain" in record:
        record["terrain"] = terrain.normalize(record["terrain"], count)
    if "animations" in record:
        animations = record["animations"]
        valid_ids = {str(i) for i in range(count)}
        if not isinstance(animations, dict) or any(key not in valid_ids or not frames for key, frames in animations.items()):
            raise ValueError("The stored tile animations are invalid.")
        for frames in animations.values():
            _validate_frames(frames, count)
    if "modules" in record:
        _validate_modules(record["modules"], count)
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
            for key in ("terrain", "animations", "modules", "tile_shapes", "tile_properties", "tile_probability"):
                if key in previous:
                    record[key] = previous[key]
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


@contextmanager
def _locked_record(job: Job):
    directory = _workspace(job)
    if not directory.is_dir():
        raise ValueError("Import a tile sheet first.")
    with fsutil.locked(directory / ".workspace.lock", "This tileset is being written. Try again."):
        record = _read(directory)
        if not record:
            raise ValueError("Import a tile sheet first.")
        yield directory, record


@contextmanager
def _edit(job: Job, revision: str | None):
    with _locked_record(job) as (directory, record):
        if revision is not None and revision != _revision(record):
            raise ValueError("The tileset changed. Reload it before editing.")
        yield record
        fsutil.write_text(directory / "tileset.json", json.dumps(record, indent=2))


def collision(job: Job, tile: int, solid: bool, revision: str | None = None, shape: dict | None = None) -> dict:
    """Set or clear a tile's collision. shape (optional, solid tiles only): {"shape": preset} or
    {"points": [[x, y], ...]} plus "one_way" (core/tile_collision.py); None = the full square."""
    from . import tile_collision as tc
    with _edit(job, revision) as record:
        grid = record["grid"]
        if type(solid) is not bool or type(tile) is not int or not 0 <= tile < grid["columns"] * grid["rows"]:
            raise ValueError("Choose a tile in the grid and set collision to true or false.")
        cleaned = tc.clean_shape(shape, grid["tile_width"], grid["tile_height"]) if solid else None
        ids = set(record["solid_tiles"])
        (ids.add if solid else ids.discard)(tile)
        record["solid_tiles"] = sorted(ids)
        shapes = record.get("tile_shapes") or {}
        if cleaned:
            shapes[str(tile)] = cleaned
        else:
            shapes.pop(str(tile), None)
        if shapes:
            record["tile_shapes"] = dict(sorted(shapes.items(), key=lambda kv: int(kv[0])))
        else:
            record.pop("tile_shapes", None)
    return inspect(job)

def properties(job: Job, tile: int, values: dict, revision: str | None = None) -> dict:
    """Replace a tile's custom properties ({} clears them). One type per name across the tileset."""
    from . import tile_collision as tc
    with _edit(job, revision) as record:
        grid = record["grid"]
        if type(tile) is not int or not 0 <= tile < grid["columns"] * grid["rows"]:
            raise ValueError("Choose a tile in the grid.")
        props = record.get("tile_properties") or {}
        cleaned = tc.clean_properties(values, {k: v for k, v in props.items() if k != str(tile)})
        if cleaned:
            props[str(tile)] = cleaned
        else:
            props.pop(str(tile), None)
        if props:
            record["tile_properties"] = dict(sorted(props.items(), key=lambda kv: int(kv[0])))
        else:
            record.pop("tile_properties", None)
    return inspect(job)


MAX_WEIGHT = 1000


def _weight(value) -> float:
    """A tile's random weight: a number from 0 (never picked at random) to MAX_WEIGHT; 1 is normal."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_WEIGHT or value != value:
        raise ValueError(f"A tile weight is a number from 0 to {MAX_WEIGHT} (1 is normal).")
    return round(float(value), 4)


def probability(job: Job, tile: int, weight, revision: str | None = None) -> dict:
    """Set how often Tiled picks this tile among tiles that fit the same place (random brush,
    terrain fill): exported as the tile's "probability". None or 1 resets it."""
    with _edit(job, revision) as record:
        grid = record["grid"]
        if type(tile) is not int or not 0 <= tile < grid["columns"] * grid["rows"]:
            raise ValueError("Choose a tile in the grid.")
        weights = record.get("tile_probability") or {}
        value = 1.0 if weight is None else _weight(weight)
        if value == 1.0:
            weights.pop(str(tile), None)
        else:
            weights[str(tile)] = value
        if weights:
            record["tile_probability"] = dict(sorted(weights.items(), key=lambda kv: int(kv[0])))
        else:
            record.pop("tile_probability", None)
    return inspect(job)


def update_terrain(job: Job, rules: dict, revision: str | None = None) -> dict:
    with _edit(job, revision) as record:
        grid = record["grid"]
        rules = terrain.normalize(rules, grid["columns"] * grid["rows"])
        if rules["colors"]:
            record["terrain"] = rules
        else:
            record.pop("terrain", None)
    return inspect(job)


def _validate_frames(frames: list, count: int) -> None:
    if not isinstance(frames, list) or (frames and not 2 <= len(frames) <= MAX_ANIMATION_FRAMES):
        raise ValueError(f"Use 2 to {MAX_ANIMATION_FRAMES} frames or an empty list to remove the animation.")
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"tile", "duration_ms"}:
            raise ValueError("Each animation frame needs a tile ID and a duration in milliseconds.")
        tile, duration = frame["tile"], frame["duration_ms"]
        if type(tile) is not int or not 0 <= tile < count:
            raise ValueError("Every animation frame must use a tile ID within the grid.")
        if type(duration) is not int or not 1 <= duration <= MAX_FRAME_DURATION_MS:
            raise ValueError(f"Frame durations must be whole milliseconds from 1 to {MAX_FRAME_DURATION_MS}.")


def update_animation(job: Job, tile: int, frames: list, revision: str | None = None) -> dict:
    with _edit(job, revision) as record:
        grid = record["grid"]
        count = grid["columns"] * grid["rows"]
        if type(tile) is not int or not 0 <= tile < count:
            raise ValueError("Choose a tile ID within the grid.")
        _validate_frames(frames, count)
        animations = record.get("animations", {})
        if frames:
            animations[str(tile)] = frames
            record["animations"] = animations
        else:
            animations.pop(str(tile), None)
            if not animations:
                record.pop("animations", None)
    return inspect(job)


def preview(job: Job, vertices: list, revision: str | None = None, *, allow_unknown: bool = False,
            overrides: dict | None = None, override_atlas: str | None = None, mix: bool = False) -> dict:
    record = _read(_workspace(job))
    if record is None:
        raise ValueError("Import a tile sheet first.")
    if revision is not None and revision != _revision(record):
        raise ValueError("The tileset changed. Reload it before previewing.")
    return _preview(record, vertices, allow_unknown=allow_unknown, overrides=overrides, override_atlas=override_atlas,
                    mix=mix)


def _atlas_revision(record: dict) -> str:
    return _revision({key: record[key] for key in ("digest", "grid")})


def _module_name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 64 or len(value.strip().splitlines()) != 1:
        raise ValueError("Enter a module name of 1 to 64 characters on one line.")
    return value.strip()


def _validate_modules(modules: list, count: int) -> None:
    if not isinstance(modules, list) or len(modules) > MAX_MODULES:
        raise ValueError("The saved tile module list is invalid.")
    names = set()
    for module in modules:
        if not isinstance(module, dict) or set(module) != {"name", "width", "height", "tiles"}:
            raise ValueError("A saved tile module has an unsupported format.")
        name = _module_name(module["name"]).casefold()
        if name in names:
            raise ValueError("Tile module names must be unique.")
        names.add(name)
        width, height, rows = module["width"], module["height"], module["tiles"]
        if (type(width) is not int or type(height) is not int or not 1 <= width <= MAX_MODULE_SIDE
                or not 1 <= height <= MAX_MODULE_SIDE or not isinstance(rows, list) or len(rows) != height
                or any(not isinstance(row, list) or len(row) != width for row in rows)):
            raise ValueError("A saved tile module has invalid dimensions.")
        cells = [tile for row in rows for tile in row if tile is not None]
        if not cells or any(type(tile) is not int or not 0 <= tile < count for tile in cells):
            raise ValueError("A saved tile module contains invalid atlas tiles.")


def save_module(job: Job, name: str, start: int, end: int, revision: str | None = None) -> dict:
    name = _module_name(name)
    with _edit(job, revision) as record:
        modules = record.setdefault("modules", [])
        if len(modules) >= MAX_MODULES:
            raise ValueError(f"A tileset can hold up to {MAX_MODULES} modules.")
        if any(module["name"].casefold() == name.casefold() for module in modules):
            raise ValueError("A module already has that name.")
        grid = record["grid"]
        cols = grid["columns"]
        if any(type(tile) is not int or not 0 <= tile < cols * grid["rows"] for tile in (start, end)):
            raise ValueError("Choose two corner tile IDs inside the atlas.")
        y0, y1 = sorted(tile // cols for tile in (start, end))
        x0, x1 = sorted(tile % cols for tile in (start, end))
        width, height = x1 - x0 + 1, y1 - y0 + 1
        if max(width, height) > MAX_MODULE_SIDE:
            raise ValueError(f"A module can cover at most {MAX_MODULE_SIDE} × {MAX_MODULE_SIDE} tiles.")
        empty = set(record["empty_tiles"])
        rows = [[None if tile in empty else tile for tile in range(y * cols + x0, y * cols + x1 + 1)]
                for y in range(y0, y1 + 1)]
        if all(tile is None for row in rows for tile in row):
            raise ValueError("Choose a region with at least one visible tile.")
        modules.append({"name": name, "width": width, "height": height, "tiles": rows})
    return inspect(job)


def _get_module(record: dict, name: str) -> dict:
    label = _module_name(name).casefold()
    module = next((item for item in record.get("modules", []) if item["name"].casefold() == label), None)
    if module is None:
        raise ValueError("Choose a module saved on this tileset.")
    return module


def stamp(job: Job, name: str, cell: int, vertices: list, overrides: dict | None = None,
          override_atlas: str | None = None, revision: str | None = None) -> dict:
    record = _read(_workspace(job))
    if record is None:
        raise ValueError("Import a tile sheet first.")
    if revision is not None and revision != _revision(record):
        raise ValueError("The tileset changed. Reload it before placing the module.")
    module = _get_module(record, name)
    layout = _preview(record, vertices, allow_unknown=True, overrides=overrides, override_atlas=override_atlas)
    if layout.get("invalid_overrides"):
        raise ValueError("Restore outdated placements before stamping a module.")
    width, height = layout["width"], layout["height"]
    if type(cell) is not int or not 0 <= cell < width * height:
        raise ValueError("Choose a starting cell inside the map.")
    row, col = divmod(cell, width)
    if col + module["width"] > width or row + module["height"] > height:
        raise ValueError("The whole module must fit inside the map.")
    edited = dict(overrides or {})
    for y, line in enumerate(module["tiles"]):
        for x, tile in enumerate(line):
            if tile is not None:
                edited[str((row + y) * width + col + x)] = tile
    return {"overrides": edited, "override_atlas": _atlas_revision(record)}


def _preview(record: dict, vertices: list, *, allow_unknown: bool = False,
             overrides: dict | None = None, override_atlas: str | None = None, mix: bool = False) -> dict:
    weights = {int(k): w for k, w in (record.get("tile_probability") or {}).items()} if mix else None
    result = terrain.preview(record.get("terrain", {"colors": [], "tiles": {}}), vertices, allow_unknown=allow_unknown,
                             weights=weights)
    if overrides is None:
        return result
    width, height = result["width"], result["height"]
    cells = {str(i): i for i in range(width * height)}
    if not isinstance(overrides, dict) or any(key not in cells for key in overrides):
        raise ValueError("Use zero-based map cell IDs for placement overrides.")
    if override_atlas is not None and (
        not isinstance(override_atlas, str) or not re.fullmatch(r"[0-9a-f]{64}", override_atlas)
    ):
        raise ValueError("The placement atlas revision is invalid.")
    stale = override_atlas is not None and override_atlas != _atlas_revision(record)
    grid = record["grid"]
    count = MAX_TILES if stale else grid["columns"] * grid["rows"]
    missing = {(x, y) for x, y in result["missing"]}
    invalid = []
    for key, tile in overrides.items():
        if tile is not None and (type(tile) is not int or not 0 <= tile < count):
            raise ValueError("Use an atlas tile ID within the grid, or null to leave the cell empty.")
        y, x = divmod(cells[key], width)
        if stale and tile is not None:
            invalid.append([x, y])
            missing.add((x, y))
            result["tiles"][y][x] = None
        else:
            missing.discard((x, y))
            result["tiles"][y][x] = tile
    result["missing"] = [[x, y] for x, y in sorted(missing, key=lambda cell: (cell[1], cell[0]))]
    if invalid:
        result["invalid_overrides"] = sorted(invalid, key=lambda cell: (cell[1], cell[0]))
    return result


def _snapshot(job: Job, directory: Path, record: dict) -> dict:
    return receipt.snapshot(job.root, [_source(directory, record)],
                            {key: record[key] for key in ("grid", "solid_tiles", "terrain", "animations", "modules",
                                                         "tile_shapes", "tile_properties", "tile_probability")
                             if key in record})


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
    return {"tileset": record, "revision": _revision(record), "atlas_revision": _atlas_revision(record),
            "preview": source.relative_to(job.root).as_posix() if source.is_file() else None,
            "export": state, "files": files}


TILED_VERSION = "1.10.2"                       # the Tiled release whose JSON format we write


def _export_metadata(record: dict, name: str) -> tuple[dict, dict]:
    grid = record["grid"]
    ids, blank = set(record["solid_tiles"]), set(record["empty_tiles"])
    animations = {int(tile): frames for tile, frames in record.get("animations", {}).items()}
    rects = list(_rectangles(grid))
    native = {"schema_version": 1, "image": "tiles.png", "grid": grid,
              "tiles": [{"id": i, "rect": list(rect), "empty": i in blank, "solid": i in ids}
                        for i, rect in enumerate(rects)]}
    w, h = grid["tile_width"], grid["tile_height"]
    collision_layer = {"type": "objectgroup", "draworder": "index", "name": "Collision", "visible": True,
                       "opacity": 1, "x": 0, "y": 0, "objects": [{"id": 1, "name": "", "x": 0, "y": 0,
                           "width": w, "height": h, "rotation": 0, "visible": True}]}
    from . import tile_collision as tc
    shapes, props = record.get("tile_shapes") or {}, record.get("tile_properties") or {}
    weights = record.get("tile_probability") or {}
    tiled_tiles = []
    for tile in sorted(ids | animations.keys() | {int(k) for k in props} | {int(k) for k in weights}):
        entry = {"id": tile}
        if str(tile) in weights:
            native["tiles"][tile]["probability"] = entry["probability"] = weights[str(tile)]
        shape = shapes.get(str(tile))
        if tile in ids and shape:
            pts = tc.polygon(shape, w, h)
            native["tiles"][tile]["collision"] = {**({"shape": shape["shape"]} if "shape" in shape else {}),
                                                  "polygon": pts, "one_way": bool(shape.get("one_way"))}
            obj = {"id": 1, "name": "", "x": 0, "y": 0, "rotation": 0, "visible": True,
                   "polygon": [{"x": x, "y": y} for x, y in pts]}
            if shape.get("one_way"):
                obj["properties"] = [{"name": "one_way", "type": "bool", "value": True}]
            entry["objectgroup"] = {**collision_layer, "objects": [obj]}
        elif tile in ids:
            entry["objectgroup"] = collision_layer
        if str(tile) in props:
            native["tiles"][tile]["properties"] = props[str(tile)]
            entry["properties"] = tc.tiled_properties(props[str(tile)])
        if tile in animations:
            frames = animations[tile]
            native["tiles"][tile]["animation"] = frames
            entry["animation"] = [{"tileid": frame["tile"], "duration": frame["duration_ms"]} for frame in frames]
        tiled_tiles.append(entry)
    tiled = {"type": "tileset", "version": "1.10", "tiledversion": TILED_VERSION, "name": name, "image": "tiles.png",
             "imagewidth": grid["width"], "imageheight": grid["height"], "columns": grid["columns"],
             "tilecount": len(rects), "tilewidth": w, "tileheight": h, "margin": grid["margin"],
             "spacing": grid["spacing"], "tiles": tiled_tiles}
    if rules := record.get("terrain"):
        native["terrain"] = rules
        tiled["wangsets"] = [terrain.tiled_wangset(rules)]
    if modules := record.get("modules"):
        native["modules"] = modules
    return native, tiled


def _export_image(directory: Path, record: dict) -> tuple[Path, bytes]:
    path = _source(directory, record)
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or sha256(data).hexdigest() != record["digest"]:
        raise ValueError("The retained PNG changed. Import a valid tile sheet again.")
    return path, data


def export(job: Job) -> dict:
    with _locked_record(job) as (directory, record):
        path, data = _export_image(directory, record)
        native, tiled = _export_metadata(record, job.root.parent.name)
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
        from ..export import godot
        fsutil.write_text(out / FILES[3], godot.tileset(record, FILES[0]))
        if _read(directory) != record or _snapshot(job, directory, record) != before:
            raise RuntimeError("Tileset inputs changed during export. Export again.")
        receipt.save(receipt_path, out, before, [out / name for name in FILES])
    return inspect(job)
