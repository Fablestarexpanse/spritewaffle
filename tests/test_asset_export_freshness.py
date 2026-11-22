from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spritewaffle import cli
from spritewaffle.core import effect, item
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_effect import _clip
from test_item import _item
from test_mcp import call, text
from test_variant import FakeComfy


def _ready_item(base):
    j = _item(base)
    item.facings(j, GameProfile(name="default"), client=FakeComfy())
    j.set_stage("facings", "approved")
    return j


def _ready_effect(base):
    j = Job.create("orb", "e1", base=base, asset_type="effect", style="painted", frame_count=8, size=16)
    _clip(j.action_dir("S", "effect") / "raw.mp4", n=32, size=128)
    return j


def test_item_freshness_tracks_faces_fit_settings_and_output_bytes(tmp_path):
    j = _ready_item(tmp_path)
    profile = GameProfile(name="default")
    assert item.export_status(j, profile) == {"status": "missing"}
    out = j.root / "06_export/item"
    out.mkdir()
    (out / "gold_cape_item.json").write_text("{}", encoding="utf-8")
    assert item.export_status(j, profile) == {"status": "untracked"}
    item.export(j, profile)
    assert item.export_status(j, profile)["status"] == "current"
    renamed_profile = GameProfile(name="other", cell_size=80, sprite_height_px=48)
    assert item.export_status(j, renamed_profile)["status"] == "current"
    j.update_inputs(fits=[{"character": "knight", "job_id": "cape", "base": "plain"}])
    (j.root / "02_facings/N.png").unlink()
    (out / "gold_cape_front.png").write_bytes(b"replaced bytes")
    status = item.export_status(j, profile)
    assert status == {"status": "stale", "settings_changed": ["fits"], "changed_inputs": ["02_facings/N.png"],
                      "changed_outputs": ["gold_cape_front.png"]}


def test_effect_freshness_tracks_raw_clip_timing_frames_and_bundle_rename(tmp_path):
    j = _ready_effect(tmp_path)
    assert effect.export_status(j) == {"status": "missing"}
    out = Path(effect.process(j)["dir"])
    assert effect.export_status(j)["status"] == "current"
    j.update_inputs(still="red glow", seconds=7, motion="slow pulse")
    assert effect.export_status(j)["status"] == "current"
    j.update_inputs(fps=20, effect_name="Blue orb")
    (out / "frames/orb_004.png").unlink()
    assert effect.export_status(j) == {"status": "stale", "settings_changed": ["fps", "name"], "changed_inputs": [],
                                       "changed_outputs": ["orb/frames/orb_004.png"]}
    renamed = Path(effect.process(j)["dir"])
    assert renamed.name == "Blue_orb" and out.is_dir()
    assert effect.export_status(j)["status"] == "current"
    (j.root / "03_actions/S/effect/raw.mp4").unlink()
    assert effect.export_status(j)["changed_inputs"] == ["03_actions/S/effect/raw.mp4"]


def test_effect_refuses_to_verify_an_interrupted_output(tmp_path, monkeypatch):
    j = _ready_effect(tmp_path)
    effect.process(j)
    write = effect.export

    def changed(*a, **kw):
        out = write(*a, **kw)
        j.update_inputs(fps=20)
        return out

    monkeypatch.setattr(effect, "export", changed)
    with pytest.raises(RuntimeError, match="changed during"):
        effect.process(j)
    assert effect.export_status(j) == {"status": "incomplete"}


def test_item_and_effect_freshness_across_http_cli_and_mcp(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    j = _ready_item(tmp_path)
    fx = _ready_effect(tmp_path)
    fx_dir = Path(effect.process(fx)["dir"])
    with TestClient(create_app(tmp_path, worker=False)) as c:
        c.post("/api/jobs/gold_cape/i1/export_item").raise_for_status()
        for name, job_id, kind in (("gold_cape", "i1", "item"), ("orb", "e1", "effect")):
            api = c.get(f"/api/jobs/{name}/{job_id}/export_{kind}")
            assert api.status_code == 200 and api.json()["status"] == "current"
            assert cli.main([f"export-{kind}-status", "--job", f"{name}/{job_id}"]) == 0
            assert json.loads(capsys.readouterr().out) == api.json()
            mcp, _ = build(tmp_path)
            assert text(call(mcp, f"{kind}_export_status", character=name, job_id=job_id)) == api.json()
        fx.update_inputs(effect_name="Different name")
        old_preview = c.get("/api/jobs/orb/e1").json()["effect"]["preview"]
        assert f"/effect/{fx_dir.name}/orb_preview.gif" in old_preview
