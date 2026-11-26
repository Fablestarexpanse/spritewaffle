"""Per-tile collision shapes and custom properties for the tileset workspace.

A solid tile (record["solid_tiles"]) collides with its whole square unless record["tile_shapes"]
gives it a preset shape (slopes, half tiles), its own polygon, or marks it one-way (platforms you
jump up through). record["tile_properties"] holds free key/value pairs per tile (bool, int, float,
or string: "damage": 5, "water": true, "footstep": "grass"). Both keys are optional, so older
tilesets read and export exactly as before.

Points are tile pixels, origin top-left, y down. Slope names say which way the floor rises when
walking right: slope_up is the triangle filling the bottom-right half; the low/high pairs are the
two halves of a 2:1 (22.5 degree) slope.
"""
from __future__ import annotations

import re

SHAPES = {
    "full":            lambda w, h: [(0, 0), (w, 0), (w, h), (0, h)],
    "half_bottom":     lambda w, h: [(0, h / 2), (w, h / 2), (w, h), (0, h)],
    "half_top":        lambda w, h: [(0, 0), (w, 0), (w, h / 2), (0, h / 2)],
    "slope_up":        lambda w, h: [(0, h), (w, 0), (w, h)],
    "slope_down":      lambda w, h: [(0, 0), (w, h), (0, h)],
    "slope_up_low":    lambda w, h: [(0, h), (w, h / 2), (w, h)],
    "slope_up_high":   lambda w, h: [(0, h / 2), (w, 0), (w, h), (0, h)],
    "slope_down_high": lambda w, h: [(0, 0), (w, h / 2), (w, h), (0, h)],
    "slope_down_low":  lambda w, h: [(0, h / 2), (w, h), (0, h)],
}
MAX_POINTS = 16
MAX_PROPERTIES = 16
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}")


def _num(v: float) -> int | float:
    return int(v) if float(v).is_integer() else round(float(v), 3)


def clean_shape(entry, w: int, h: int) -> dict | None:
    """Validate one tile's shape entry: {"shape": name} or {"points": [[x, y], ...]}, plus optional
    "one_way": true. Returns the stored form, or None when it is the plain full square."""
    if entry is None:
        return None
    if not isinstance(entry, dict) or set(entry) - {"shape", "points", "one_way"}:
        raise ValueError("A collision shape has shape (a preset name) or points, and optional one_way.")
    one_way = entry.get("one_way", False)
    if type(one_way) is not bool:
        raise ValueError("one_way must be true or false.")
    points = entry.get("points")
    shape = entry.get("shape")
    if points is not None and shape not in (None, "custom"):
        raise ValueError("Give either a preset shape or points, not both.")
    if points is not None:
        if (not isinstance(points, list) or not 3 <= len(points) <= MAX_POINTS
                or any(not isinstance(p, (list, tuple)) or len(p) != 2
                       or any(type(c) not in (int, float) or not 0 <= c <= lim for c, lim in zip(p, (w, h)))
                       for p in points)):
            raise ValueError(f"A collision polygon needs 3-{MAX_POINTS} [x, y] points inside the {w} x {h} tile.")
        out = {"points": [[_num(x), _num(y)] for x, y in points]}
    else:
        shape = shape or "full"
        if shape not in SHAPES:
            raise ValueError(f"Unknown collision shape {shape!r}; use one of {', '.join(SHAPES)} or points.")
        out = {} if shape == "full" else {"shape": shape}
    if one_way:
        out["one_way"] = True
    return out or None


def polygon(entry: dict | None, w: int, h: int) -> list[list[int | float]]:
    """The tile's collision polygon in tile pixels (top-left origin)."""
    if entry and entry.get("points"):
        return [list(p) for p in entry["points"]]
    return [[_num(x), _num(y)] for x, y in SHAPES[(entry or {}).get("shape", "full")](w, h)]


def clean_properties(props, others: dict | None = None) -> dict:
    """Validate a tile's properties. others: {tile: properties} of the other tiles, so one name
    keeps one type across the tileset (Godot custom data layers are typed)."""
    if not isinstance(props, dict) or len(props) > MAX_PROPERTIES:
        raise ValueError(f"Tile properties are up to {MAX_PROPERTIES} name: value pairs.")
    known = {}
    for values in (others or {}).values():
        for k, v in values.items():
            known.setdefault(k, type(v))
    out = {}
    for k, v in props.items():
        if not isinstance(k, str) or not KEY.fullmatch(k):
            raise ValueError(f"Property name {k!r}: letters, digits and _, starting with a letter or _.")
        if type(v) not in (bool, int, float, str) or (type(v) is str and len(v) > 200):
            raise ValueError(f"Property {k}: use true/false, a number, or text up to 200 characters.")
        if k in known and known[k] is not type(v):
            raise ValueError(f"Property {k} is a {known[k].__name__} on other tiles; keep one type per name.")
        out[k] = v
    return out


def property_layers(record: dict) -> list[tuple[str, type]]:
    """Every property name with its type, sorted by name (Godot custom data layer order)."""
    found: dict[str, type] = {}
    for values in (record.get("tile_properties") or {}).values():
        for k, v in values.items():
            found.setdefault(k, type(v))
    return sorted(found.items())


def tiled_properties(props: dict) -> list[dict]:
    kind = {bool: "bool", int: "int", float: "float", str: "string"}
    return [{"name": k, "type": kind[type(v)], "value": v} for k, v in sorted(props.items())]


def parse_text(text: str) -> dict:
    """'damage=5, water=true, footstep=grass' -> typed dict (CLI convenience)."""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        if "=" not in part:
            raise ValueError(f"Write properties as name=value, not {part!r}.")
        k, v = (s.strip() for s in part.split("=", 1))
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        elif re.fullmatch(r"-?\d*\.\d+", v):
            out[k] = float(v)
        else:
            out[k] = v
    return out
