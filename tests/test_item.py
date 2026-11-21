"""Equipment items: own job (front + back), fitted onto any base character."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import generate, item, variant
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.prompts import builder
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render
from test_variant import FakeComfy, _base


def _item(tmp_path):
    j = Job.create("gold_cape", "i1", base=tmp_path, asset_type="item", description="a long gold cape", style="pixel")
    Image.fromarray(render(draw_sprite(1), canvas=(256, 256))).save(j.root / "01_anchor" / "anchor.png")
    j.set_stage("anchor", "approved")
    return j


def test_item_prompts():
    a = builder.anchor("a long gold cape", GameProfile(name="p"), asset_type="item")
    assert "not worn by anyone" in a and "invisible body" in a
    b = builder.item_back("a long gold cape")
    assert "180 degrees" in b and "one closed outer surface" in b and "a long gold cape" in b and builder.FRAMING in b
    r = builder.item_reference("N", "knight", "gold cape", "wearing this", back_ref=True)
    assert "<Picture 2> shows the back of <Subject 2>" in r


def test_item_facings_are_front_and_back(tmp_path):
    j = _item(tmp_path)
    c = FakeComfy()
    rep = generate.facings(j, GameProfile(name="p"), client=c)       # routed to item.facings
    assert len(c.calls) == 1 and "180 degrees" in c.calls[0][1]["prompt"]
    assert {p.name for p in (j.root / "02_facings").glob("*.png")} == {"S.png", "N.png"}
    assert rep["item"] and j.read_meta()["stages"]["facings"]["status"] == "review"


def test_fit_uses_front_for_front_views_and_back_for_back_views(tmp_path):
    j = _item(tmp_path)
    c = FakeComfy()
    item.facings(j, GameProfile(name="p"), client=c)
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    with pytest.raises(RuntimeError):
        item.fit(j, b)                                          # item back not approved yet
    j.set_stage("facings", "approved")
    with pytest.raises(ValueError):
        item.fit(b, b)                                          # not an item
    v = item.fit(j, b, client=c)
    m = v.read_meta()["inputs"]
    assert v.root.name == "k1_gold_cape" and m["item_description"] == "a long gold cape" and Path(m["item_job"]) == j.root
    assert j.read_meta()["inputs"]["fits"] == [{"character": "knight", "job_id": "k1_gold_cape", "base": "k1"}]
    anchor_dir = v.root / "01_anchor"
    variant.anchor(v, GameProfile(name="p"), client=c)
    assert c.calls[-1][1]["ref_images"][1] == anchor_dir / "item_ref.png"      # front view: item front
    v.set_stage("anchor", "approved")
    c.calls.clear()
    variant.facings(v, GameProfile(name="p"), client=c)
    by_src = {vals["ref_images"][0].stem: vals for _, vals in c.calls}
    assert by_src["NE"]["ref_images"][1] == anchor_dir / "item_ref_back.png" and "shows the back of" in by_src["NE"]["prompt"]
    assert by_src["N"]["ref_images"] == [by_src["N"]["ref_images"][0]] and "Seen from behind" in by_src["N"]["prompt"]   # words
    assert by_src["E"]["ref_images"][1] == anchor_dir / "item_ref.png"


def test_fit_api(tmp_path):
    j = _item(tmp_path)
    item.facings(j, GameProfile(name="p"), client=FakeComfy())
    j.set_stage("facings", "approved")
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        items = c.get("/api/jobs/knight/k1").json()["items"]
        assert items == [{"character": "gold_cape", "job_id": "i1", "thumb": items[0]["thumb"]}]
        r = c.post("/api/jobs/knight/k1/variant", json={"item_job": "gold_cape/i1", "instruction": "wearing this"}).json()
        assert r["job_id"] == "k1_gold_cape"
        assert c.get("/api/jobs/gold_cape/i1").json()["fits"][0]["job_id"] == "k1_gold_cape"


def test_base_body_is_plain_and_animates(tmp_path):
    assert "grey sleeveless undershirt" in builder.BASE_BODY_WEAR and "empty hands" in builder.BASE_BODY_WEAR
    assert "walk" in builder.asset("base_body")["actions"] and builder.actions_for("base_body") is builder.ACTIONS
    j = Job.create("human", "b1", base=tmp_path, asset_type="base_body")
    Image.fromarray(render(draw_sprite(0), canvas=(256, 256))).save(j.root / "01_anchor" / "anchor.png")
    j.set_stage("anchor", "approved")
    with pytest.raises(ValueError, match="base bodies get their facings"):   # from the turnaround sheet
        generate.facings(j, GameProfile(name="p"), client=FakeComfy())


def test_item_export_writes_front_and_back(tmp_path):
    j = _item(tmp_path)
    item.facings(j, GameProfile(name="p"), client=FakeComfy())
    with pytest.raises(RuntimeError):
        item.export(j, GameProfile(name="p"))                 # back not approved
    j.set_stage("facings", "approved")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.post("/api/jobs/gold_cape/i1/export_item").json()
    out = j.root / "06_export" / "item"
    assert (out / "gold_cape_front.png").exists() and (out / "gold_cape_back.png").exists() and (out / "gold_cape_item.json").exists()
    h = r["views"]["front"]["size"][1]
    assert 0.6 * GameProfile(name="p").sprite_height_px <= h <= 1.4 * GameProfile(name="p").sprite_height_px
    assert j.read_meta()["stages"]["export:item"]["status"] == "done"
