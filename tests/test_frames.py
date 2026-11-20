import json

import numpy as np

from spritewaffle.frames import analysis, contact, layout, picker, video
from synth import draw_sprite, render, write_clip


def _walk(n=48):
    return [render(draw_sprite(i // 3), scale=6, offset=(80, 40), canvas=(256, 224), seed=i) for i in range(n)]


def test_extract_and_contact_sheet(tmp_path):
    write_clip(tmp_path / "c.mp4", frames=10)
    rep = video.extract(tmp_path / "c.mp4", tmp_path / "ex")
    assert rep["frame_count"] == 10 and rep["fps"] == 24 and rep["source_size"] == [320, 320]
    assert json.loads((tmp_path / "ex" / "extraction_report.json").read_text())["frame_count"] == 10
    frames = video.load(video.list_frames(tmp_path / "ex"))
    out = contact.write(frames, tmp_path / "sheet.png", cols=5, cell=64)
    from PIL import Image
    assert Image.open(out).size == (320, 128)


def test_frozen_detector():
    still = [render(draw_sprite(0), seed=0)] * 12
    moving = _walk(12)
    assert analysis.is_frozen(still)[0]
    assert not analysis.is_frozen(moving)[0]


def test_parse_indices():
    assert picker.parse_indices("1,6,11,17") == [1, 6, 11, 17]
    assert picker.parse_indices("24-27, 30") == [24, 25, 26, 27, 30]


def test_picker_sets_share_start_end_keys_and_skip_bad():
    frames = _walk(48)
    frames[20] = frames[20].copy(); frames[20][:] = (0, 255, 0)      # malformed (empty)
    clip = picker.analyse(frames)
    assert clip.bad.get(20) == "malformed:empty"
    res = picker.select(clip, counts=(12, 24))
    s12, s24 = res["sets"][12].indices, res["sets"][24].indices
    assert len(s12) == 12 and len(s24) == 24
    assert s12[0] == s24[0] == 0 and s12[-1] == s24[-1] == 47
    for k, _ in res["keys"]:
        assert k in s12 and k in s24
    assert 20 not in s12 and 20 not in s24
    assert all(r for r in res["sets"][12].reasons)


def test_loop_point_finds_cycle():
    frames = _walk(40)          # silhouette repeats every 6 frames (steps 0 and 2 share a pose)
    clip = picker.analyse(frames)
    res = picker.select(clip, counts=(12,), loop=True)
    assert res["end"] % 6 == 0 and res["loop_seam"] < 0.05
    assert len(res["sets"][12].indices) == 12


def test_manual_override():
    clip = picker.analyse(_walk(30))
    res = picker.select(clip, manual="1,6,11,17,24-26")
    sel = res["sets"][7]
    assert sel.indices == [1, 6, 11, 17, 24, 25, 26]
    assert set(sel.reasons) == {"manual"}


def test_preserve_canvas_identical_placement_no_recentering():
    a = np.zeros((40, 40, 4), np.uint8); a[10:20, 5:10] = 255
    b = np.zeros((40, 40, 4), np.uint8); b[12:22, 25:30] = 255     # moved right+down
    cells, places = layout.preserve_canvas([a, b], (32, 32))
    assert places[0] == places[1]
    # relative motion preserved: b is 20px right and 2px lower than a in the cell too
    ya, xa = np.argwhere(cells[0][..., 3] > 0).min(0)
    yb, xb = np.argwhere(cells[1][..., 3] > 0).min(0)
    assert (xb - xa, yb - ya) == (20, 2)


def test_foot_anchor_fixed_center_and_feet():
    a = np.zeros((40, 40, 4), np.uint8); a[5:15, 5:11] = 255
    b = np.zeros((40, 40, 4), np.uint8); b[20:38, 22:26] = 255
    cells, _ = layout.foot_anchor([a, b], (32, 32), foot_y=30)
    for c in cells:
        ys, xs = np.where(c[..., 3] > 0)
        assert ys.max() == 30 and abs((xs.min() + xs.max() + 1) / 2 - 16) <= 0.5


def test_sheet_components_row_major():
    sheet = np.zeros((100, 200, 4), np.uint8)
    boxes = [(10, 10), (80, 12), (150, 8), (20, 60), (90, 62)]   # 3 on row 1, 2 on row 2
    for i, (x, y) in enumerate(boxes):
        sheet[y:y + 25, x:x + 15] = (i * 40, 0, 0, 255)
    sheet[30, 160] = (0, 0, 255, 255)          # stray speck must not count
    crops = layout.sheet_components(sheet, 5, join_px=2)
    assert [int(c[..., 0].max()) for c in crops] == [0, 40, 80, 120, 160]


def test_mirror_and_asymmetry():
    sym = np.zeros((20, 20, 4), np.uint8); sym[5:15, 5:15] = (100, 100, 100, 255)
    asym = sym.copy(); asym[5:15, 5:8] = (255, 0, 0, 255); asym[2:5, 12:15] = (100, 100, 100, 255)
    assert not layout.asymmetry(sym)["asymmetric"]
    assert layout.asymmetry(asym)["asymmetric"]
    f = np.arange(2 * 3 * 4 * 4, dtype=np.uint8).reshape(2, 3, 4, 4)
    np.testing.assert_array_equal(layout.mirror(f)[:, :, 0], f[:, :, -1])
