"""Sprite stacks from a real 3D model (TRELLIS.2 on ComfyUI) instead of carving outlines.

Measured 2026-11-21 on a tall pine: the outline carve makes a solid cone coloured from the views,
so tiered, overhanging branches turn into speckle and the drooping lowest branches make the
bottom slices a wide disc. TRELLIS.2 turns the anchor into a vertex-coloured mesh (~45 s on a
4090); this module reads the GLB, samples its surface into voxels at the stack's resolution, fills
the inside and hands (occupancy, colour) to the same slice export as the carve.

No extra dependencies: a minimal glTF-binary reader in numpy.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(positions (N,3) float, colours (N,3) uint8, faces (M,3) int) of every triangle primitive.
    Vertices without COLOR_0 get mid grey."""
    data = Path(path).read_bytes()
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError(f"{path} is not a glTF 2 binary")
    off, js, binc = 12, None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8:off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(chunk)
        elif ctype == b"BIN\x00":
            binc = chunk
        off += 8 + clen

    def accessor(i: int) -> np.ndarray:
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        dt = np.dtype(_COMP[a["componentType"]])
        n = _NCOMP[a["type"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or dt.itemsize * n
        raw = np.frombuffer(binc, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * n, offset=start)
        out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * n), (stride, 1)).copy()
        arr = out.view(dt).reshape(a["count"], n)
        if a.get("normalized") and dt.kind in "ui":
            arr = arr.astype(np.float32) / np.iinfo(dt).max
        return arr

    P, C, F = [], [], []
    base = 0
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            pos = accessor(prim["attributes"]["POSITION"]).astype(np.float64)
            if "COLOR_0" in prim["attributes"]:
                col = accessor(prim["attributes"]["COLOR_0"])[:, :3].astype(np.float64)
                col = col / 255 if col.max() > 1.001 else col
                # glTF vertex colours are LINEAR; screens (and our palettes) are sRGB. Read as sRGB
                # they came out far too dark (measured: the pine's greens max ~39/255).
                col = np.where(col <= 0.0031308, col * 12.92, 1.055 * np.power(np.clip(col, 0, 1), 1 / 2.4) - 0.055) * 255
            else:
                col = np.full((len(pos), 3), 128.0)
            idx = accessor(prim["indices"]).reshape(-1, 3) if "indices" in prim else np.arange(len(pos)).reshape(-1, 3)
            P.append(pos)
            C.append(np.clip(np.rint(col), 0, 255).astype(np.uint8))
            F.append(idx.astype(np.int64) + base)
            base += len(pos)
    if not P:
        raise ValueError(f"{path} has no triangle meshes")
    return np.concatenate(P), np.concatenate(C), np.concatenate(F)


def voxelize(pos: np.ndarray, col: np.ndarray, faces: np.ndarray, height: int, samples_per_voxel: float = 6.0,
             seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Surface-sample the mesh into a grid `height` voxels tall (glTF y-up), fill the inside.
    Returns (occ (H, D, W) bool, colour (H, D, W, 3) uint8) like carve.carve: index 0 = bottom,
    D index 0 = front (+z)."""
    lo, hi = pos.min(0), pos.max(0)
    vs = (hi[1] - lo[1]) / height                            # voxel size from the height
    a, b, c = pos[faces[:, 0]], pos[faces[:, 1]], pos[faces[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = int(min(6_000_000, max(50_000, area.sum() / vs ** 2 * samples_per_voxel)))
    rng = np.random.default_rng(seed)
    tri = rng.choice(len(faces), n, p=area / area.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    w = 1 - u - v
    f = faces[tri]
    pts = pos[f[:, 0]] * w[:, None] + pos[f[:, 1]] * u[:, None] + pos[f[:, 2]] * v[:, None]
    cols = (col[f[:, 0]] * w[:, None] + col[f[:, 1]] * u[:, None] + col[f[:, 2]] * v[:, None])
    W = int(np.ceil((hi[0] - lo[0]) / vs)) + 1
    D = int(np.ceil((hi[2] - lo[2]) / vs)) + 1
    H = height
    ix = np.clip(((pts[:, 0] - lo[0]) / vs).astype(int), 0, W - 1)
    iy = np.clip(((pts[:, 1] - lo[1]) / vs).astype(int), 0, H - 1)
    iz = np.clip(((hi[2] - pts[:, 2]) / vs).astype(int), 0, D - 1)    # front (+z) = index 0
    flat = (iy * D + iz) * W + ix
    cnt = np.bincount(flat, minlength=H * D * W)
    acc = np.stack([np.bincount(flat, cols[:, k], minlength=H * D * W) for k in range(3)], 1)
    surf = cnt > 0
    colour = np.zeros((H * D * W, 3))
    colour[surf] = acc[surf] / cnt[surf, None]
    surf = surf.reshape(H, D, W)
    colour = colour.reshape(H, D, W, 3)
    # inside = not reachable from outside without crossing the surface (flood fill by dilation)
    pad = np.pad(surf, 1)
    outside = np.zeros_like(pad)
    outside[0, :, :] = outside[-1, :, :] = True
    outside[:, 0, :] = outside[:, -1, :] = True
    outside[:, :, 0] = outside[:, :, -1] = True
    outside &= ~pad
    while True:
        grown = outside.copy()
        grown[1:] |= outside[:-1]; grown[:-1] |= outside[1:]
        grown[:, 1:] |= outside[:, :-1]; grown[:, :-1] |= outside[:, 1:]
        grown[:, :, 1:] |= outside[:, :, :-1]; grown[:, :, :-1] |= outside[:, :, 1:]
        grown &= ~pad
        if (grown == outside).all():
            break
        outside = grown
    occ = ~outside[1:-1, 1:-1, 1:-1]
    # inside voxels take the colour of the nearest surface voxel above them (what a top-down slice shows)
    for y in range(H - 2, -1, -1):
        inner = occ[y] & ~surf[y]
        colour[y][inner] = np.where(occ[y + 1][inner][:, None], colour[y + 1][inner], colour[y][inner])
    return occ, np.clip(colour, 0, 255).astype(np.uint8)


def _in_plane(o: np.ndarray) -> np.ndarray:
    """Occupied left/right/front/back neighbours of every voxel within its own slice."""
    p = np.pad(o, ((0, 0), (1, 1), (1, 1))).astype(np.int8)
    return p[:, :-2, 1:-1] + p[:, 2:, 1:-1] + p[:, 1:-1, :-2] + p[:, 1:-1, 2:]


def trim_strands(occ: np.ndarray, passes: int = 2) -> tuple[np.ndarray, int]:
    """Drop one-voxel-wide strands inside a slice (a voxel with at most one in-slice neighbour that is
    with nothing directly above or below it): sampled branch tips that stacked into single-pixel
    prongs. Measured 2026-11-27: pine 23 of 9780 voxels, prong pixels per rendered frame 8.5 -> 6.7
    (the rest is rotation aliasing, which no voxel change removes); chest unchanged. Returns
    (occupancy, voxels removed)."""
    held = np.zeros_like(occ)                      # a voxel directly above or below: a pole or a tip, kept
    held[:-1] |= occ[1:]
    held[1:] |= occ[:-1]
    o = occ.copy()
    for _ in range(passes):
        cut = o & (_in_plane(o) <= 1) & ~held
        if not cut.any():
            break
        o &= ~cut
    return o, int(occ.sum() - o.sum())


def quantize(occ: np.ndarray, colour: np.ndarray, k: int, palette: list[str] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Voxel colours to a pixel-art palette: the job/profile palette if given, else k colours fitted
    on the visible voxels. Returns (colour, palette rgb)."""
    from ..pixel import palette as palmod
    from ..pixel.color import hex_to_rgb, oklab_to_srgb, srgb_to_oklab
    lab = srgb_to_oklab(colour.reshape(1, 1, -1, 3).astype(float))     # one 1-row "frame": what fit() expects
    alpha = occ.reshape(1, 1, -1)
    if palette:
        pal = np.array([hex_to_rgb(h) for h in palette], np.uint8)
        pal_lab = srgb_to_oklab(pal.astype(float))
    else:
        pal_lab = palmod.fit(lab, alpha, k)
        pal = np.clip(np.rint(oklab_to_srgb(pal_lab)), 0, 255).astype(np.uint8)
    d = ((lab[0, 0][:, None, :] - pal_lab[None]) ** 2).sum(-1)
    out = pal[d.argmin(1)].reshape(colour.shape)
    out[~occ] = 0
    return out, pal
