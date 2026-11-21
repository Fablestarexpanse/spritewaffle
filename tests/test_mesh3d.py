"""Sprite stacks from a 3D model: GLB reading, voxelizing, palette."""
import json
import struct

import numpy as np

from spritewaffle.stack import carve, mesh3d


def _cube_glb(path, colour_linear=(0.2, 0.5, 0.05)):
    """A unit cube (y-up), every vertex the same linear colour, as glTF binary."""
    v = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)], np.float32)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    idx = np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))], np.uint32).ravel()
    col = np.tile(np.array(colour_linear, np.float32), (8, 1))
    blobs = [v.tobytes(), idx.tobytes(), col.tobytes()]
    offs = np.cumsum([0] + [len(b) for b in blobs])
    js = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": int(offs[-1])}],
          "bufferViews": [{"buffer": 0, "byteOffset": int(offs[i]), "byteLength": len(b)} for i, b in enumerate(blobs)],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
                        {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"},
                        {"bufferView": 2, "componentType": 5126, "count": 8, "type": "VEC3"}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 2}, "indices": 1, "mode": 4}]}],
          "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    jb = json.dumps(js).encode()
    jb += b" " * (-len(jb) % 4)
    bb = b"".join(blobs)
    bb += b"\0" * (-len(bb) % 4)
    body = struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(bb), b"BIN\x00") + bb
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


def test_read_glb_converts_linear_colour_to_srgb(tmp_path):
    _cube_glb(tmp_path / "c.glb")
    P, C, F = mesh3d.read_glb(tmp_path / "c.glb")
    assert P.shape == (8, 3) and F.shape == (12, 3)
    assert tuple(C[0]) == (124, 188, 63)                    # linear (.2,.5,.05) -> sRGB, not (51,128,13)


def test_cube_voxelizes_solid_to_the_requested_height(tmp_path):
    _cube_glb(tmp_path / "c.glb")
    occ, col = mesh3d.voxelize(*mesh3d.read_glb(tmp_path / "c.glb"), height=12)
    H, D, W = occ.shape
    assert H == 12 and abs(D - 12) <= 1 and abs(W - 12) <= 1
    assert occ[6, D // 2, W // 2]                           # the inside is filled
    assert occ.mean() > 0.85
    col, pal = mesh3d.quantize(occ, col, 4, palette=["#7cbc3f", "#000000"])
    assert {tuple(c) for c in col[occ].tolist()} == {(124, 188, 63)}
    sl = carve.slices(occ, col)
    assert sl.shape == (12, D, W, 4)


def test_flat_card_stays_flat(tmp_path):
    """What TRELLIS made from a flat pixel-art sprite: a card. Voxelizing must not invent depth."""
    _cube_glb(tmp_path / "c.glb")
    P, C, F = mesh3d.read_glb(tmp_path / "c.glb")
    P[:, 2] *= 0.002
    occ, _ = mesh3d.voxelize(P, C, F, height=12)
    assert occ.shape[1] <= 2
