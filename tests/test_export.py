import json

import numpy as np
from PIL import Image

from spritewaffle.export import aseprite, sheet


def _frames(n=3, h=8, w=6):
    rng = np.random.default_rng(0)
    idx = rng.integers(-1, 4, size=(n, h, w))
    pal = np.array([[10, 20, 30], [200, 10, 10], [10, 200, 10], [250, 250, 250]], np.uint8)
    return idx, pal


def test_aseprite_indexed_roundtrip(tmp_path):
    idx, pal = _frames()
    p = tmp_path / "a.aseprite"
    aseprite.write(p, idx, pal, durations_ms=[100, 80, 120], tags=[("walk_S", 0, 2, "forward")])
    data = p.read_bytes()
    assert int.from_bytes(data[:4], "little") == len(data)
    doc = aseprite.read(p)
    assert (doc.width, doc.height, doc.depth) == (6, 8, 8)
    assert doc.durations == [100, 80, 120]
    assert doc.tags == [("walk_S", 0, 2, "forward")]
    assert doc.layers == ["sprite"]
    # transparent index 0, real colours shifted by one
    assert doc.transparent_index == 0
    np.testing.assert_array_equal(doc.palette[1:, :3], pal)
    for f in range(3):
        np.testing.assert_array_equal(doc.frames[f], np.where(idx[f] >= 0, idx[f] + 1, 0))


def test_aseprite_rgba_roundtrip(tmp_path):
    idx, pal = _frames()
    rgba = np.zeros(idx.shape + (4,), np.uint8)
    m = idx >= 0
    rgba[m, :3] = pal[idx[m]]
    rgba[m, 3] = 255
    p = tmp_path / "b.aseprite"
    aseprite.write_rgba(p, rgba, durations_ms=[50] * 3, tags=[("idle", 0, 2, "pingpong")])
    doc = aseprite.read(p)
    assert doc.depth == 32 and doc.tags == [("idle", 0, 2, "pingpong")]
    np.testing.assert_array_equal(np.stack(doc.frames), rgba)


def test_png_strip_json_and_previews(tmp_path):
    frames = np.zeros((4, 16, 12, 4), np.uint8)
    for i in range(4):
        frames[i, 4 + i:14, 3:9] = (200, 50, 50, 255)    # feet at y=13
    out = sheet.export_png(tmp_path, "walk_S", frames, fps=10, loop=True,
                           events={"step": [1, 3]}, hitboxes={0: [3, 4, 6, 10]})
    strip = Image.open(out["strip"])
    assert strip.size == (48, 16)
    meta = json.loads(out["json"].read_text())
    assert [f["rect"] for f in meta["frames"]] == [[i * 12, 0, 12, 16] for i in range(4)]
    assert meta["frames"][0]["duration_ms"] == 100 and meta["loop"] is True
    assert meta["pivot"] == [6, 14]                       # bottom-centre of union bbox (feet)
    assert meta["events"] == {"step": [1, 3]}
    assert len(list((tmp_path / "frames").glob("*.png"))) == 4
    gif = Image.open(out["gif"])
    assert gif.n_frames == 4 and gif.size == (12 * 4, 16 * 4)
    assert Image.open(out["apng"]).n_frames == 4
