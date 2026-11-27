"""Effects: brightness key, frame picking, processing, settings API."""
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import effect
from spritewaffle.core.job import Job
from spritewaffle.prompts import effects as fx
from spritewaffle.ui.server import create_app


def _clip(path, n=48, grow=False, size=256):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24, (size, size))
    for i in range(n):
        f = np.zeros((size, size, 3), np.uint8)
        if grow:
            r = int(4 + 80 * min(1, i / 20)) if i < 36 else 0           # spark -> burst -> gone
        else:
            r = 40 + int(6 * np.sin(i / n * 2 * np.pi * 2))              # pulsing, loops twice
        if r:
            cv2.circle(f, (size // 2, size // 2), r, (40, 160, 255), -1)
            cv2.circle(f, (size // 2, size // 2), r // 2, (220, 240, 255), -1)
        vw.write(f)
    vw.release()


def test_luma_key_black_is_transparent_and_colour_survives():
    rgb = np.zeros((4, 4, 3), np.uint8)
    rgb[1, 1] = (255, 120, 0)
    rgb[2, 2] = (64, 30, 0)                                   # dim version of the same colour
    soft = effect.luma_key(rgb)
    assert soft[0, 0, 3] == 0 and soft[1, 1, 3] == 255 and 0 < soft[2, 2, 3] < 255
    assert abs(int(soft[2, 2, 0]) - 255) <= 2                 # un-premultiplied: same hue, less alpha
    hard = effect.luma_key(rgb, soft=False)
    assert set(np.unique(hard[..., 3])) <= {0, 255}


def test_pick_one_shot_covers_the_active_part_and_loop_skips_the_start():
    frames = [np.zeros((32, 32, 4), np.uint8) for _ in range(40)]
    for i in range(5, 30):
        frames[i][10:20, 10:20, 3] = 255
    idx, info = effect.pick(frames, loop=False, count=8)
    assert info["start"] == 5 and info["end"] == 29 and len(idx) == 8
    idx, info = effect.pick(frames, loop=True, count=8)
    assert info["start"] >= 40 // 6 and info["kind"] == "loop"


def test_process_writes_game_ready_files(tmp_path):
    for style, grow in (("pixel", False), ("painted", True)):
        j = Job.create("fx", f"t_{style}", base=tmp_path, asset_type="effect", style=style,
                       effect_name="orb", still="orb", motion="pulses", loop=not grow, size=32, frame_count=8)
        _clip(j.action_dir("S", "effect") / "raw.mp4", grow=grow)
        m = effect.process(j)
        d = j.root / "06_export" / "effect" / "orb"
        want = 32 if style == "pixel" else 128                  # painted draws at x4
        assert m["frames"] == 8 and abs(max(m["cell"]) - want) <= 2, m["cell"]
        for f in ("orb.png", "orb_sheet.png", "orb.aseprite", "orb_preview.gif", "orb.json"):
            assert (d / f).exists(), f
        assert json.loads((d / "orb.json").read_text())["sheet"]["cols"] == 3
        a = np.array(Image.open(d / "frames" / "orb_000.png"))[..., 3]
        assert a[0, 0] == 0 and a.max() == 255                 # transparent corner, opaque core
        if style == "pixel":
            assert set(np.unique(a)) <= {0, 255}               # pixel art: hard alpha


def test_presets_and_prompts_keep_the_rules():
    for name, p in fx.PRESETS.items():
        s = fx.still(p["still"], p.get("start_small", False))
        assert "#000000" in s and "no characters" in s
        assert "locked camera" in fx.video(p["motion"]) and "#000000" in fx.video(p["motion"])
    assert "10 percent" in fx.still("spark", start_small=True)


def test_effect_api(tmp_path):
    Job.create("boom", "b1", base=tmp_path, asset_type="effect")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.post("/api/jobs/boom/b1/effect", json={"preset": "explosion", "size": 48, "queue": "render"}).json()
        assert r["spec"]["loop"] is False and r["spec"]["size"] == 48 and len(r["tasks"]) == 2
        assert [t["stage"] for t in c.get("/api/queue").json()][::-1] == ["effect_render", "effect_process"]
        assert c.post("/api/jobs/boom/b1/effect", json={"preset": "nope"}).status_code == 400
        assert c.post("/api/jobs/boom/b1/effect", json={"bg": "purple"}).status_code == 400
        assert c.post("/api/jobs/boom/b1/effect", json={"fps": 0}).status_code == 400
        assert c.get("/api/jobs/boom/b1").json()["effect"]["spec"]["still"].startswith("a tiny bright")


def test_green_card_on_black_is_keyed_away():
    f = np.zeros((200, 200, 3), np.uint8)
    f[50:150, 50:150] = (0, 255, 0)                      # a green card on a black frame
    f[90:110, 95:105] = (150, 90, 40)                    # the object
    assert effect.detect_bg(f) == "black+green"
    k = effect.key_frames([f], "black+green", soft=False)[0]
    assert k[60, 60, 3] == 0 and k[10, 10, 3] == 0 and k[100, 100, 3] == 255
    g = np.zeros((200, 200, 3), np.uint8); g[:] = (0, 250, 10)
    assert effect.detect_bg(g) == "green"
    with pytest.raises(ValueError):
        effect.detect_bg(np.full((200, 200, 3), 128, np.uint8))


def test_lay_flat_squashes_a_circle_onto_the_ground():
    from spritewaffle.core import effect as fxc
    yy, xx = np.mgrid[0:40, 0:40]
    ring = (np.hypot(xx - 19.5, yy - 19.5) < 18).astype(np.uint8)
    frame = np.dstack([ring * 255, ring * 200, ring * 50, ring * 255]).astype(np.uint8)
    flat, = fxc.lay_flat([frame], 0.5)
    assert flat.shape == (20, 40, 4)
    ys, xs = np.where(flat[..., 3] > 127)
    assert xs.max() - xs.min() > 1.8 * (ys.max() - ys.min())            # an ellipse twice as wide as tall
    assert abs(flat[10, 20, 0] - 255) <= 1                                # colour kept inside


def test_aura_preset_lies_flat_and_others_do_not(tmp_path):
    from fastapi.testclient import TestClient
    from spritewaffle.core import effect as fxc
    from spritewaffle.ui.server import create_app
    j = Job.create("glow", "a1", base=tmp_path, asset_type="effect", preset="aura")
    assert fxc.spec(j)["ground"] == 0.5 and fxc.spec(j)["loop"] is True
    k = Job.create("bolt", "l1", base=tmp_path, asset_type="effect", preset="lightning")
    assert fxc.spec(k)["ground"] == 0
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.post("/api/jobs/bolt/l1/effect", json={"ground": 0.95}).status_code == 400
        assert client.post("/api/jobs/bolt/l1/effect", json={"ground": "0.35"}).status_code == 200
    assert fxc.spec(k)["ground"] == 0.35
