"""Cell / sprite size settings: profile validation, editor API, fit warnings."""
import pytest
from fastapi.testclient import TestClient

from spritewaffle.core import stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile, resolve, save_named
from spritewaffle.frames.layout import Placement
from spritewaffle.ui.server import create_app


def test_profile_refuses_sizes_that_cannot_work():
    with pytest.raises(ValueError, match="sprite height"):
        GameProfile(name="p", cell_size=32, sprite_height_px=48)
    with pytest.raises(ValueError, match="palette"):
        GameProfile(name="p", palette=300)
    with pytest.raises(ValueError, match="fps"):
        GameProfile(name="p", fps_per_action={"walk": 0})


def test_save_named_keeps_other_fields_and_rejects_bad_names(tmp_path):
    p = save_named("big", {"cell_size": "96", "sprite_height_px": "72", "fps_per_action": {"walk": "10"}}, tmp_path)
    assert (p.cell_size, p.sprite_height_px, p.fps("walk"), p.despill) == (96, 72, 10, "all")
    p = save_named("big", {"palette": 24}, tmp_path)
    assert p.cell_size == 96 and p.palette == 24                 # earlier fields kept
    for bad in ("default", "Big Name", "", "../x"):
        with pytest.raises(ValueError):
            save_named(bad, {}, tmp_path)


def test_editor_api_lists_saves_and_switches_job(tmp_path, monkeypatch):
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    Job.create("hero", "j", base=tmp_path / "jobs")
    with TestClient(create_app(tmp_path / "jobs", worker=False)) as c:
        ps = c.get("/api/profiles").json()
        assert ps[0]["name"] == "default" and ps[0]["builtin"] and ps[0]["used_by"] == ["hero/j"]
        r = c.post("/api/profiles", json={"name": "wide", "cell_size": 96, "sprite_height_px": 64, "use_for": "hero/j"})
        assert r.status_code == 200 and r.json()["cell_size"] == 96
        assert c.get("/api/jobs/hero/j").json()["inputs"]["profile"] == "wide"
        assert c.post("/api/profiles", json={"name": "bad", "cell_size": 32, "sprite_height_px": 40}).status_code == 400
        assert c.post("/api/jobs/hero/j/settings", json={"profile": None}).status_code == 200   # back to default
        assert "profile" not in c.get("/api/jobs/hero/j").json()["inputs"]
    assert resolve("wide").cell_size == 96


def test_fit_warnings_name_a_cell_that_fits():
    centred = Placement(1.0, (0, 0, 40, 50), (12, 13), (32.0, 63.0))
    assert stages._fit_warnings(centred, 64, 64) == []
    wide = Placement(1.0, (0, 0, 62, 50), (1, 13), (36.0, 63.0))      # feet 35 px from the art's left edge
    w = stages._fit_warnings(wide, 64, 64)
    assert len(w) == 1 and "4px right" in w[0] and "a 72px profile cell" in w[0]
    tall = Placement(1.0, (0, 0, 40, 300), (108, -45), (128.0, 255.0))  # painted x4: 256 px cell, profile 64
    w = stages._fit_warnings(tall, 256, 64)
    assert w[0].startswith("cut off: the top 45px") and "a 80px profile cell" in w[0]


def test_turned_from_flags_copies_not_turns():
    import numpy as np
    from spritewaffle.core import generate
    a = np.zeros((100, 60, 4), np.uint8)
    a[10:90, 15:45] = (200, 50, 50, 255)
    a[10:30, 15:45] = (240, 220, 180, 255)                     # face
    same = a.copy()
    same[50:52, 20:22] = (190, 60, 60, 255)                    # a few pixels moved: still a copy
    turned = a.copy()
    turned[10:90, 15:45] = (40, 60, 200, 255)                  # back view: different colours everywhere
    assert generate.turned_from(same, a) < generate.COPY_DIFF < generate.turned_from(turned, a)


def test_job_page_knows_four_direction_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    save_named("four", {"directions": 4}, tmp_path / "profiles")
    j = Job.create("hero", "j", base=tmp_path / "jobs")
    j.update_inputs(profile="four")
    Job.create("hero", "k", base=tmp_path / "jobs").update_inputs(profile="gone")
    with TestClient(create_app(tmp_path / "jobs", worker=False)) as c:
        assert c.get("/api/jobs/hero/j").json()["directions"] == 4
        assert c.get("/api/jobs/hero/k").json()["directions"] == 8        # missing profile: page still loads
