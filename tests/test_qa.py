import numpy as np

from spritewaffle.qa import checks


def _cells(n=6, h=24, w=20):
    c = np.zeros((n, h, w, 4), np.uint8)
    for i in range(n):
        c[i, 6:20, 6 + i % 2:12 + i % 2] = (200, 50, 50, 255)
        c[i, 8, 8] = (250, 250, 250, 255)
    return c


P = [{"scale": 1, "crop": [0, 0, 10, 10], "paste": [3, 4]}]


def test_clean_animation_passes():
    r = checks.run(_cells(), P * 6, "preserve-canvas", palette_size=4, loop=True)
    assert r["status"] == "pass", r["errors"]
    assert r["placements_identical"] and r["sheet_size"] == [120, 24] and r["palette_used"] == 2


def test_failures_and_reroll_targets():
    c = _cells()
    c[2, 0, 5] = (1, 2, 3, 255)                                     # edge contact + new colour + stray
    places = P * 5 + [{"scale": 1, "crop": [0, 0, 10, 10], "paste": [4, 4]}]
    r = checks.run(c, places, "preserve-canvas", palette_size=2, loop=False)
    assert r["status"] == "fail"
    assert r["edge_contact_frames"] == [2]
    assert not r["placements_identical"]
    assert {"layout", "pixelize", "layout/profile cell_size"} <= set(r["reroll"])


def test_motion_pop_detected():
    c = np.repeat(_cells(1), 8, axis=0)
    c[:, 19, 6:12] = 0
    for i in range(8):
        c[i, 19, 6 + i % 3] = (200, 50, 50, 255)                    # small steady motion
    c[4] = 0
    c[4, 2:22, 2:18] = (200, 50, 50, 255)                           # sudden big change
    r = checks.run(c, P * 8, "preserve-canvas", palette_size=4, loop=False)
    assert 3 in r["motion_pops"] or 4 in r["motion_pops"]


def test_review_locates_findings_from_existing_report_fields():
    cells = _cells()
    cells[2] = 0
    cells[4, 0, 5] = (200, 50, 50, 255)
    cells[5, 2, [1, 3, 5, 7]] = (200, 50, 50, 255)
    report = checks.run(cells, P * len(cells), "preserve-canvas", palette_size=4, loop=False)
    review = checks.review(report)
    by_frame = {f["frame"]: f["issues"] for f in review["frame_findings"]}
    assert review["classification"] == "fail"
    assert any(i["code"] == "empty" for i in by_frame[2])
    assert any(i["code"] == "border" for i in by_frame[4])
    assert any(i["code"] == "stray" and i["severity"] == "warn" for i in by_frame[5])
    assert review["errors"] == report["errors"]


def test_review_labels_passing_reports_with_warnings_and_loads_legacy_reports():
    cells = np.repeat(_cells(1), 6, axis=0)
    report = checks.run(cells, P * len(cells), "preserve-canvas", palette_size=4, loop=False)
    review = checks.review(report)
    assert review["status"] == "pass" and review["classification"] == "warn"
    assert review["frame_findings"][0]["frame"] == 1
    assert review["frame_findings"][0]["issues"][0]["code"] == "duplicate"
    assert checks.review({"status": "pass"})["frame_findings"] == []
