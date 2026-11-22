"""Minimal .aseprite writer + reader (https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md).

Writes one layer, one compressed cel per frame, per-frame durations, a palette and animation tags
(Unity's 2D Aseprite Importer turns tags into clips). Indexed files reserve palette index 0 for
transparency; colour i of the sprite palette is stored at index i+1.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DIRECTIONS = {"forward": 0, "reverse": 1, "pingpong": 2, "pingpong_reverse": 3}
_DIR_NAMES = {v: k for k, v in DIRECTIONS.items()}

CHUNK_OLD_PALETTE = 0x0004
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_COLOR_PROFILE = 0x2007
CHUNK_TAGS = 0x2018
CHUNK_SLICE = 0x2022
CHUNK_PALETTE = 0x2019


def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _chunk(ctype: int, data: bytes) -> bytes:
    return struct.pack("<IH", len(data) + 6, ctype) + data


def _header(file_size, frames, w, h, depth, ncolors, transparent=0) -> bytes:
    hdr = struct.pack("<IHHHHHIHIIB3xHBBhhHH", file_size, 0xA5E0, frames, w, h, depth, 1, 100, 0, 0,
                      transparent, ncolors, 1, 1, 0, 0, 16, 16)
    return hdr + bytes(128 - len(hdr))


def _frame(chunks: list[bytes], duration_ms: int) -> bytes:
    body = b"".join(chunks)
    n = len(chunks)
    return struct.pack("<IHHH2xI", len(body) + 16, 0xF1FA, min(n, 0xFFFF), duration_ms, n) + body


def _palette_chunks(rgba: np.ndarray) -> list[bytes]:
    n = len(rgba)
    new = struct.pack("<III8x", n, 0, n - 1) + b"".join(struct.pack("<H4B", 0, *map(int, c)) for c in rgba)
    old = struct.pack("<HBB", 1, 0, n % 256) + b"".join(struct.pack("<3B", *map(int, c[:3])) for c in rgba)
    return [_chunk(CHUNK_OLD_PALETTE, old), _chunk(CHUNK_PALETTE, new)]


def _layer_chunk(name: str) -> bytes:
    return _chunk(CHUNK_LAYER, struct.pack("<HHHHHHB3x", 3, 0, 0, 0, 0, 0, 255) + _string(name))


def _tags_chunk(tags) -> bytes:
    if len(tags) > 65_535:
        raise ValueError("The Aseprite bundle exceeds the animation tag limit.")
    data = struct.pack("<H8x", len(tags))
    for tag in tags:
        name, start, end, direction = tag[:4]
        repeat = tag[4] if len(tag) > 4 else 0            # 0 = loop forever, 1 = play once (one-shot)
        data += struct.pack("<HHBH6x3Bx", start, end, DIRECTIONS[direction], repeat, 0, 0, 0) + _string(name)
    return _chunk(CHUNK_TAGS, data)


def animation_tags(name: str, start: int, end: int, loop: bool, named: list[dict], offset: int = 0) -> list:
    tags = [(name, offset + start, offset + end, "forward", 0 if loop else 1)]
    tags.extend((tag["aseprite_tag"], offset + tag["start"], offset + tag["end"], "forward", 0 if tag["loop"] else 1)
                for tag in named)
    return tags


def _slice_chunk(name: str, keys) -> bytes:
    """keys: [(frame, x, y, w, h, pivot_x, pivot_y)], pivot relative to the slice origin. A key
    holds from its frame until the next key."""
    data = struct.pack("<III", len(keys), 2, 0) + _string(name)          # flags 2 = has pivot
    for frame, x, y, w, h, px, py in keys:
        data += struct.pack("<IiiIIii", frame, x, y, w, h, int(px), int(py))
    return _chunk(CHUNK_SLICE, data)


def _cel_chunk(pixels: np.ndarray) -> bytes:
    h, w = pixels.shape[:2]
    head = struct.pack("<HhhBHh5xHH", 0, 0, 0, 255, 2, 0, w, h)
    return _chunk(CHUNK_CEL, head + zlib.compress(np.ascontiguousarray(pixels).tobytes(), 9))


def _write(path: Path, cels: list[np.ndarray], depth: int, pal_rgba: np.ndarray | None,
           durations_ms, tags, layer: str, slices=()) -> Path:
    h, w = cels[0].shape[:2]
    frames = []
    for i, cel in enumerate(cels):
        chunks = []
        if i == 0:
            chunks.append(_chunk(CHUNK_COLOR_PROFILE, struct.pack("<HHI8x", 1, 0, 0)))
            if pal_rgba is not None:
                chunks += _palette_chunks(pal_rgba)
            chunks.append(_layer_chunk(layer))
            if tags:
                chunks.append(_tags_chunk(tags))
            for name, keys in slices:
                chunks.append(_slice_chunk(name, keys))
        chunks.append(_cel_chunk(cel))
        frames.append(_frame(chunks, int(durations_ms[i])))
    body = b"".join(frames)
    ncolors = len(pal_rgba) if pal_rgba is not None else 0
    data = _header(128 + len(body), len(cels), w, h, depth, ncolors) + body
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def write(path, indices: np.ndarray, palette: np.ndarray, durations_ms, tags=(), layer: str = "sprite",
          slices=()) -> Path:
    """Indexed .aseprite. indices (F,h,w) with -1 = transparent; palette (k<=255, 3) uint8."""
    palette = np.asarray(palette, np.uint8)
    if len(palette) > 255:
        raise ValueError("indexed .aseprite supports at most 255 colours + transparent")
    pal = np.zeros((len(palette) + 1, 4), np.uint8)
    pal[1:, :3] = palette
    pal[1:, 3] = 255
    cels = [np.where(f >= 0, f + 1, 0).astype(np.uint8) for f in indices]
    return _write(path, cels, 8, pal, durations_ms, list(tags), layer, slices)


def write_rgba(path, frames: np.ndarray, durations_ms, tags=(), layer: str = "sprite", slices=()) -> Path:
    """RGBA .aseprite. frames (F,h,w,4) uint8."""
    return _write(path, [np.asarray(f, np.uint8) for f in frames], 32, None, durations_ms, list(tags), layer, slices)


# --- reader (round-trip tests, and later re-import) ----------------------------------------

@dataclass
class AseDoc:
    width: int
    height: int
    depth: int
    transparent_index: int
    frames: list = field(default_factory=list)
    durations: list = field(default_factory=list)
    palette: np.ndarray | None = None
    layers: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    repeats: list = field(default_factory=list)
    slices: dict = field(default_factory=dict)          # name -> [(frame, x, y, w, h, pivot_x, pivot_y)]         # per tag: 0 = loop forever, N = play N times


def _read_string(b: bytes, o: int) -> tuple[str, int]:
    n = struct.unpack_from("<H", b, o)[0]
    return b[o + 2:o + 2 + n].decode("utf-8"), o + 2 + n


def read(path) -> AseDoc:
    b = Path(path).read_bytes()
    size, magic, nframes, w, h, depth = struct.unpack_from("<IHHHHH", b, 0)
    if magic != 0xA5E0 or size != len(b):
        raise ValueError("not a valid .aseprite file")
    doc = AseDoc(w, h, depth, b[28])
    bpp = {32: 4, 16: 2, 8: 1}[depth]
    o = 128
    for _ in range(nframes):
        fsize, fmagic, old_n, dur, new_n = struct.unpack_from("<IHHH2xI", b, o)
        if fmagic != 0xF1FA:
            raise ValueError("bad frame magic")
        doc.durations.append(dur)
        n = new_n or old_n
        c = o + 16
        img = None
        for _ in range(n):
            csize, ctype = struct.unpack_from("<IH", b, c)
            d = b[c + 6:c + csize]
            if ctype == CHUNK_PALETTE:
                psize, first, last = struct.unpack_from("<III", d, 0)
                pal = np.zeros((psize, 4), np.uint8) if doc.palette is None else doc.palette
                p = 20
                for i in range(first, last + 1):
                    flags = struct.unpack_from("<H", d, p)[0]
                    pal[i] = struct.unpack_from("<4B", d, p + 2)
                    p += 6
                    if flags & 1:
                        _, p = _read_string(d, p)
                doc.palette = pal
            elif ctype == CHUNK_LAYER:
                name, _ = _read_string(d, 16)
                doc.layers.append(name)
            elif ctype == CHUNK_TAGS:
                ntags = struct.unpack_from("<H", d, 0)[0]
                p = 10
                for _ in range(ntags):
                    start, end, direction, repeat = struct.unpack_from("<HHBH", d, p)
                    name, p = _read_string(d, p + 17)
                    doc.tags.append((name, start, end, _DIR_NAMES[direction]))
                    doc.repeats.append(repeat)
            elif ctype == CHUNK_SLICE:
                nkeys, flags, _ = struct.unpack_from("<III", d, 0)
                name, p = _read_string(d, 12)
                keys = []
                for _ in range(nkeys):
                    frame, x, y, w, h = struct.unpack_from("<IiiII", d, p)
                    p += 20
                    if flags & 1:
                        p += 16
                    px = py = None
                    if flags & 2:
                        px, py = struct.unpack_from("<ii", d, p)
                        p += 8
                    keys.append((frame, x, y, w, h, px, py))
                doc.slices[name] = keys
            elif ctype == CHUNK_CEL:
                _, x, y, _, ctype2 = struct.unpack_from("<HhhBH", d, 0)
                if ctype2 != 2:
                    raise ValueError(f"cel type {ctype2} not supported by this reader")
                cw, ch = struct.unpack_from("<HH", d, 16)
                px = np.frombuffer(zlib.decompress(d[20:]), np.uint8)
                shape = (ch, cw, bpp) if bpp > 1 else (ch, cw)
                img = np.zeros((h, w, bpp) if bpp > 1 else (h, w), np.uint8)
                img[y:y + ch, x:x + cw] = px.reshape(shape)
            c += csize
        doc.frames.append(img if img is not None else np.zeros((h, w, bpp) if bpp > 1 else (h, w), np.uint8))
        o += fsize
    return doc
