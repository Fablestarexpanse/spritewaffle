"""Depth + normal maps for animation frames (core/depthmaps.py). No GPU: the depth render is faked."""
import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import alignment, depthmaps, manifest, queue
from test_manifest import _pixel_job


def test_normals_face_away_from_the_slope():
    mask = np.zeros((60, 60), bool)
    mask[10:50, 10:50] = True
    xs = np.tile(np.arange(60, dtype=float), (60, 1))
    _, n = depthmaps.maps_from_depth(xs * 4, mask, (0, 240))          # nearer to the right -> faces left
    assert n[30, 30, 0] < 110 and n[30, 30, 2] > 128
    _, n = depthmaps.maps_from_depth(xs.T * 4, mask, (0, 240))        # nearer further down -> faces up
    assert n[30, 30, 1] > 146
    d, n = depthmaps.maps_from_depth(np.full((60, 60), 100.0), mask, (0, 240))
    assert (n[0, 0] == [128, 128, 255]).all() and d[0, 0] == 0          # outside the sprite: flat, far


def test_one_depth_range_for_the_whole_clip():
    a, b = np.full((4, 4), 10.0), np.full((4, 4), 200.0)
    m = np.ones((4, 4), bool)
    lo, hi = depthmaps.clip_range([a, b], [m, m])
    assert lo < 20 and hi > 190                                          # both frames share it


def _fake_depth(job, facing):
    for m in sorted((job.root / "03_actions" / facing / "walk" / "selected_12f").glob("*.png")):
        w, h = Image.open(m).size
        p = depthmaps.depth_path(m)
        p.parent.mkdir(exist_ok=True)
        Image.fromarray(np.tile(np.linspace(0, 255, w).astype(np.uint8), (h, 1))).save(p)


def test_build_writes_aligned_maps_and_flips_mirrored_normals(tmp_path):
    j, _ = _pixel_job(tmp_path)
    with pytest.raises(FileNotFoundError):
        depthmaps.build(j, "E", "walk", 12)                              # depth not rendered yet
    _fake_depth(j, "E")
    assert depthmaps.frame_sets(j, "W", "walk") == ("E", [12])          # W uses E's masters
    for f in ("E", "W"):
        assert depthmaps.build(j, f, "walk", 12)["frames"] == 4
    e = sorted((j.root / "04_pixel" / "E" / "walk" / "12f" / "frames").glob("[0-9][0-9][0-9].png"))
    w = sorted((j.root / "04_pixel" / "W" / "walk" / "12f" / "frames").glob("[0-9][0-9][0-9].png"))
    for c in e + w:
        col = np.array(Image.open(c).convert("RGBA"))[..., 3] > 0
        for kind in ("depth", "normal"):
            mp = np.array(Image.open(alignment.map_path(c, kind)).convert("RGBA"))[..., 3] > 0
            assert (mp == col).all(), (c.name, kind)                    # pixel for pixel with the colour
    ne = np.array(Image.open(alignment.map_path(e[0], "normal")))
    nw = np.array(Image.open(alignment.map_path(w[0], "normal")))
    lit_e, lit_w = ne[..., 3] > 0, nw[..., 3] > 0
    assert ne[lit_e, 0].mean() < 128 < nw[lit_w, 0].mean()               # E faces left (nearer right); mirrored W faces right
    frames = next(a for a in manifest.read(j)["animations"] if a["action"] == "walk")["frames"]
    assert all(f["depth"] and f["normal"] for f in frames if f["yaw_degrees"] in (90.0, 270.0))


def test_maps_queue_one_task_per_clip(tmp_path):
    j, _ = _pixel_job(tmp_path)
    q = queue.Queue(tmp_path)
    tasks = q.submit_maps(j.root)
    assert sorted((t["args"]["facing"], t["args"]["action"]) for t in tasks) == [("E", "walk"), ("S", "walk"), ("W", "walk")]
    assert all(t["stage"] == "maps" and t["resource"] == "gpu" for t in tasks)
    assert len(q.submit_maps(j.root, facing="E")) == 1


def test_http_run_maps_queues_every_clip(tmp_path):
    from fastapi.testclient import TestClient
    from spritewaffle.ui.server import create_app
    j, _ = _pixel_job(tmp_path)
    with TestClient(create_app(tmp_path, worker=False)) as client:
        ids = client.post("/api/jobs/knight/k1/run", json={"stage": "maps", "args": {}}).json()
        assert len(ids) == 3
        assert len(client.post("/api/jobs/knight/k1/run", json={"stage": "maps", "args": {"facing": "W", "action": "walk"}}).json()) == 1
