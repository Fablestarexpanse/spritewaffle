"""Godot 4 export: native resources next to the atlas pages, so a character drops into a Godot
project with no plugin (audit 2026-11-26 P1 #2: Godot 4 reads neither .aseprite nor TexturePacker).

- <name>.tres: a SpriteFrames resource. Every frame is an AtlasTexture cut from the atlas pages,
  with its trim restored (margin), so all frames keep the cell size and line up. Per-frame
  durations (timeline edits) become relative frame durations; speed = the animation's fps.
- <name>.tscn: an AnimatedSprite2D using it, offset so the character's pivot (feet) sits on the
  node's origin, with nearest-neighbour filtering for pixel art.

Paths inside the files are relative to the files themselves, so the folder can be copied
anywhere inside a Godot project (Godot's text resource loader resolves relative paths against the
resource's own folder; verified by importing into Godot 4.6, DECISIONS.md 2026-11-26).
Mirrored animations the atlas leaves out (mirror="flip") use their source frames; the scene's
metadata `flip_h` lists them so a game sets AnimatedSprite2D.flip_h for those.
"""
from __future__ import annotations

from pathlib import Path


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def sprite_frames(meta: dict) -> tuple[str, dict]:
    """(SpriteFrames .tres text, {flipped animation: its source}) from a character atlas JSON."""
    pages = meta["pages"]
    cw, ch = meta["cell"]
    ext = [f'[ext_resource type="Texture2D" path="{_q(p["image"])}" id="{i + 1}_page"]' for i, p in enumerate(pages)]
    subs, anims, flips = [], [], {}
    by_name = {a["name"]: a for a in meta["animations"]}
    n = 0
    for a in meta["animations"]:
        src = by_name.get(a.get("flip_x_of") or "", a)
        if a.get("flip_x_of"):
            flips[a["name"]] = a["flip_x_of"]
        frames = src.get("frames_atlas") or []
        durs = a.get("durations_ms") or src.get("durations_ms")
        base = 1000.0 / max(1, a.get("fps") or 12)
        items = []
        for k, f in enumerate(frames):
            n += 1
            sid = f"AtlasTexture_{n}"
            subs.append(f'[sub_resource type="AtlasTexture" id="{sid}"]\n'
                        f'atlas = ExtResource("{f["page"] + 1}_page")\n'
                        f'region = Rect2({f["x"]}, {f["y"]}, {f["w"]}, {f["h"]})\n'
                        f'margin = Rect2({f["ox"]}, {f["oy"]}, {cw - f["w"]}, {ch - f["h"]})\n'
                        "filter_clip = true")
            d = (durs[k] / base) if durs and k < len(durs) and durs[k] else 1.0
            items.append(f'{{\n"duration": {round(d, 4)},\n"texture": SubResource("{sid}")\n}}')
        anims.append('{\n"frames": [' + ", ".join(items) + f'],\n"loop": {"true" if a.get("loop") else "false"},\n'
                     f'"name": &"{_q(a["name"])}",\n"speed": {float(a.get("fps") or 12)}\n}}')
    head = f'[gd_resource type="SpriteFrames" load_steps={len(ext) + len(subs) + 1} format=3]'
    text = "\n\n".join([head, "\n".join(ext), *subs, "[resource]\nanimations = [" + ", ".join(anims) + "]"]) + "\n"
    return text, flips


def scene(meta: dict, frames_file: str, flips: dict, pixel: bool) -> str:
    """An AnimatedSprite2D scene whose origin is the character's pivot (feet)."""
    cw, ch = meta["cell"]
    pivot = meta.get("pivot") or (meta["animations"][0].get("pivot") if meta["animations"] else None) or [cw / 2, ch]
    first = meta["animations"][0]["name"] if meta["animations"] else ""
    flip_meta = ", ".join(f'"{_q(k)}": "{_q(v)}"' for k, v in flips.items())
    return "\n".join([
        '[gd_scene load_steps=2 format=3]', "",
        f'[ext_resource type="SpriteFrames" path="{_q(frames_file)}" id="1_frames"]', "",
        f'[node name="{_q(meta["character"])}" type="AnimatedSprite2D"]',
        *(["texture_filter = 1"] if pixel else []),
        'sprite_frames = ExtResource("1_frames")',
        f'animation = &"{_q(first)}"',
        f"offset = Vector2({cw / 2 - pivot[0]}, {ch / 2 - pivot[1]})",
        *([f"metadata/flip_h = {{{flip_meta}}}"] if flips else []), ""])


def write(out_dir: Path, meta: dict, pixel: bool) -> list[Path]:
    """Write <character>.tres and <character>.tscn next to the atlas pages."""
    name = meta["character"]
    tres, flips = sprite_frames(meta)
    a = Path(out_dir) / f"{name}.tres"
    b = Path(out_dir) / f"{name}.tscn"
    a.write_text(tres, encoding="utf-8")
    b.write_text(scene(meta, a.name, flips, pixel), encoding="utf-8")
    return [a, b]


# --- TileSet ----------------------------------------------------------------------------------
# Godot's peering bits for square tiles, in the order SpriteWaffle's rules list them
CORNER_BITS = ("top_left_corner", "top_right_corner", "bottom_right_corner", "bottom_left_corner")  # NW NE SE SW
EDGE_BITS = ("top_side", "right_side", "bottom_side", "left_side")                                   # N E S W
MIXED_BITS = ("top_side", "top_right_corner", "right_side", "bottom_right_corner", "bottom_side",
              "bottom_left_corner", "left_side", "top_left_corner")                                # N NE E SE S SW W NW


def _color(hexstr: str) -> str:
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"Color({r:.4f}, {g:.4f}, {b:.4f}, 1)"


def _f(v: float) -> str:
    return str(float(v))


def _value(v) -> str:
    if type(v) is bool:
        return "true" if v else "false"
    if type(v) is str:
        return f'"{_q(v)}"'
    return str(v)


def tileset(record: dict, image: str = "tiles.png") -> str:
    """Godot 4 TileSet .tres for a tileset workspace record: one atlas source over the PNG,
    collision polygons for solid tiles (full square, slope / half presets or custom points; one-way
    where set), tile properties as typed custom data layers, and the terrain rules as a terrain set
    (corner rules -> Match Corners, edge rules -> Match Sides, mixed / blob rules -> Match Corners and Sides)."""
    from ..core import terrain as terrain_mod
    from ..core import tile_collision as tc
    g = record["grid"]
    w, h = g["tile_width"], g["tile_height"]
    solid, empty = set(record.get("solid_tiles") or []), set(record.get("empty_tiles") or [])
    rules = record.get("terrain")
    mode = (rules or {}).get("mode") or "corner"
    mixed = mode == "mixed"
    names = rules["colors"] if rules else []
    index = {n: i for i, n in enumerate(names)}
    lines = ['[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_1"]', 'texture = ExtResource("1_tiles")',
             f"texture_region_size = Vector2i({w}, {h})", f"margins = Vector2i({g['margin']}, {g['margin']})",
             f"separation = Vector2i({g['spacing']}, {g['spacing']})"]
    hw, hh = w / 2, h / 2
    centres = (rules or {}).get("centers") or {}
    shapes, props = record.get("tile_shapes") or {}, record.get("tile_properties") or {}
    layers = tc.property_layers(record)
    for i in range(g["columns"] * g["rows"]):
        if i in empty:
            continue
        c = f"{i % g['columns']}:{i // g['columns']}/0"
        lines.append(f"{c} = 0")
        corners = (rules or {}).get("tiles", {}).get(str(i))
        if not corners and str(i) in centres:            # e.g. the blob island: B centre, A all round
            corners = [names[0]] * (8 if mixed else 4)
        if corners:
            known = [n for n in corners if n is not None]
            # ties go to the later terrain (a path tile with two path and two grass sides is path);
            # sorted, so the same rules always export the same file (a bare set's order varied per run)
            centre = centres.get(str(i)) or max(sorted(set(known), key=index.get), key=lambda n: (known.count(n), index[n]))
            lines += [f"{c}/terrain_set = 0", f"{c}/terrain = {index[centre]}"]
            for bit, n in zip({"mixed": MIXED_BITS, "edge": EDGE_BITS}.get(mode, CORNER_BITS), corners):
                if n is not None:
                    lines.append(f"{c}/terrains_peering_bit/{bit} = {index[n]}")
        if i in solid:
            shape = shapes.get(str(i))
            pts = ", ".join(f"{_f(x - hw)}, {_f(y - hh)}" for x, y in tc.polygon(shape, w, h))
            lines.append(f"{c}/physics_layer_0/polygon_0/points = PackedVector2Array({pts})")
            if shape and shape.get("one_way"):
                lines.append(f"{c}/physics_layer_0/polygon_0/one_way = true")
        for n, (k, _) in enumerate(layers):
            if k in props.get(str(i), {}):
                lines.append(f"{c}/custom_data_{n} = {_value(props[str(i)][k])}")
    res = ["[resource]", f"tile_size = Vector2i({w}, {h})"]
    if solid:
        res += ["physics_layer_0/collision_layer = 1"]
    gd_type = {bool: 1, int: 2, float: 3, str: 4}                 # Godot Variant.Type
    for n, (k, kind) in enumerate(layers):
        res += [f'custom_data_layer_{n}/name = "{_q(k)}"', f"custom_data_layer_{n}/type = {gd_type[kind]}"]
    if names:
        res.append(f"terrain_set_0/mode = {({'mixed': 0, 'corner': 1, 'edge': 2})[mode]}")    # Godot TerrainMode
        for i, n in enumerate(names):
            res += [f'terrain_set_0/terrain_{i}/name = "{_q(n)}"',
                    f"terrain_set_0/terrain_{i}/color = {_color(terrain_mod.SWATCHES[i % len(terrain_mod.SWATCHES)])}"]
    res.append('sources/0 = SubResource("TileSetAtlasSource_1")')
    return "\n\n".join(['[gd_resource type="TileSet" load_steps=3 format=3]',
                        f'[ext_resource type="Texture2D" path="{_q(image)}" id="1_tiles"]',
                        "\n".join(lines), "\n".join(res)]) + "\n"
