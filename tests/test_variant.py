"""Variants: a character with one change, drawn from the base job's own facings."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import generate, variant
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.prompts import builder
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render


class FakeComfy:
    def __init__(self):
        self.calls = []

    def run_template(self, slot, values, out_dir):
        self.calls.append((slot, values))
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "o.png"
        Image.fromarray(render(draw_sprite(len(self.calls) % 3), canvas=(256, 256), seed=len(self.calls))).save(p)
        return {"files": [str(p)], "values": {"prompt": values.get("prompt"), "seed": 1}, "template": slot}


def _base(tmp_path):
    b = Job.create("knight", "k1", base=tmp_path, description="small knight", style="pixel")
    Image.fromarray(render(draw_sprite(), canvas=(256, 256))).save(b.root / "01_anchor" / "anchor.png")
    for i, f in enumerate(builder.CARDINALS + builder.DIAGONALS):
        Image.fromarray(render(draw_sprite(i % 3), canvas=(256, 256), seed=i)).save(b.root / "02_facings" / f"{f}.png")
    b.set_stage("anchor", "approved")
    return b


def test_create_needs_approved_facings_and_a_change(tmp_path):
    b = _base(tmp_path)
    with pytest.raises(ValueError):
        variant.create(b, "  ")
    with pytest.raises(RuntimeError):
        variant.create(b, "add a cape")                    # facings not approved yet
    b.set_stage("facings", "approved")
    v = variant.create(b, "Add a long green cape.")
    m = v.read_meta()["inputs"]
    assert v.root.name == "k1_add_a_long_green" and m["edit"] == "Add a long green cape"
    assert m["description"] == "small knight; Add a long green cape" and Path(m["base_job"]) == b.root
    with pytest.raises(FileExistsError):
        variant.create(b, "add a long green cape")


def test_edit_prompts_keep_the_rules():
    a = builder.edit_anchor("add a cape")
    f = builder.edit_facing("NE", "add a cape")
    for p in (a, f):
        assert "add a cape" in p and builder.FRAMING in p and "Same camera angle" in p
    assert "<Picture 2>" not in f and builder.VIEW["NE"] in f


def test_variant_anchor_and_facings_come_from_the_base(tmp_path):
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    v = variant.create(b, "add a cape")
    c = FakeComfy()
    prof = GameProfile(name="p")
    variant.anchor(v, prof, client=c)
    assert c.calls[0][1]["ref_images"] == [b.root / "01_anchor" / "anchor.png"]
    v.set_stage("anchor", "approved")
    rep = generate.facings(v, prof, client=c)              # the normal entry point routes variants
    assert rep["edit"] == "add a cape" and set(rep["facings"]) == set(builder.CARDINALS + builder.DIAGONALS) - {"S"}
    ne = next(vals for slot, vals in c.calls if "turned 45" in vals["prompt"] or builder.VIEW["NE"] in vals["prompt"])
    assert ne["ref_images"] == [b.root / "02_facings" / "NE.png"]
    assert v.read_meta()["stages"]["facings"]["status"] == "review"


def test_variant_api(tmp_path):
    b = _base(tmp_path)
    with TestClient(create_app(tmp_path, worker=False)) as c:
        assert c.post("/api/jobs/knight/k1/variant", json={"instruction": "add a cape"}).status_code == 400
        b.set_stage("facings", "approved")
        r = c.post("/api/jobs/knight/k1/variant", json={"instruction": "add a cape", "job_id": "caped"}).json()
        assert r["job_id"] == "caped" and len(r["tasks"]) == 1
        j = c.get("/api/jobs/knight/caped").json()
        assert j["variant"] == {"base": "k1", "edit": "add a cape", "item": None, "item_job": None}
        assert c.get("/api/queue").json()[0]["stage"] == "anchor"


def test_item_edit_puts_the_description_where_this_is():
    d = "A pixel-art golden breastplate featuring a central red gemstone."
    assert variant.item_edit("wearing this", d) == "wearing a golden breastplate featuring a central red gemstone"
    assert variant.item_edit("holding this in the right hand", "A short sword.") == "holding a short sword in the right hand"
    assert variant.item_edit("add", "A red cape") == "add a red cape"


def test_variant_from_an_item_picture(tmp_path, monkeypatch):
    from spritewaffle.prompts import writer
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    item = tmp_path / "armor.png"
    Image.fromarray(render(draw_sprite(1), canvas=(256, 256))).save(item)
    monkeypatch.setattr(writer, "describe_item", lambda image, client=None, seed=0: "A golden breastplate with a red gem.")
    v = variant.create(b, "wearing this", job_id="gold", item=item)
    m = v.read_meta()["inputs"]
    assert m["edit"] == "wearing a golden breastplate with a red gem" and m["item_description"].startswith("A golden")
    assert (v.root / "01_anchor" / "item.png").exists()
    with pytest.raises(FileNotFoundError):
        variant.create(b, "wearing this", job_id="gold2", item=tmp_path / "nope.png")


def test_back_views_get_the_item_without_its_front_details():
    assert variant.item_core("A golden breastplate featuring a central red gemstone, detailed with gold") == "A golden breastplate"
    assert variant.item_core("a short sword with a ruby pommel") == "a short sword"
    assert variant.item_core("a plain iron helmet") == "a plain iron helmet"


def test_item_variant_sends_the_item_as_picture_2(tmp_path, monkeypatch):
    from spritewaffle.prompts import writer
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    item = tmp_path / "armor.png"
    Image.fromarray(render(draw_sprite(1), canvas=(256, 256))).save(item)
    monkeypatch.setattr(writer, "describe_item", lambda image, client=None, seed=0: "A golden breastplate with a red gem.")
    v = variant.create(b, "wearing this", job_id="gold", item=item)
    ref = v.root / "01_anchor" / "item_ref.png"
    card = Image.open(ref)
    assert card.size == (1024, 1024) and card.getpixel((5, 5)) == (205, 205, 210)   # small item on a grey card
    assert v.read_meta()["inputs"]["character_description"] == "small knight"
    c = FakeComfy()
    prof = GameProfile(name="p")
    variant.anchor(v, prof, client=c)
    assert c.calls[0][1]["ref_images"] == [b.root / "01_anchor" / "anchor.png", ref]
    assert "<Subject 3>" in c.calls[0][1]["prompt"] and "wearing <Subject 2>" in c.calls[0][1]["prompt"]
    v.set_stage("anchor", "approved")
    variant.facings(v, prof, client=c)
    n = next(vals for _, vals in c.calls if vals["ref_images"][0] == b.root / "02_facings" / "NE.png")
    assert n["ref_images"][1] == ref and "only the back of it shows: golden breastplate; the gem" in n["prompt"]


def test_item_reference_caption_uses_the_subject_format():
    p = builder.item_reference("E", "small knight", "a short sword with a ruby pommel", "holding this in the right hand")
    assert p.startswith("The small knight in <Picture 1> is <Subject 1>. The short sword")
    assert "holding <Subject 2> in the right hand" in p and builder.VIEW["E"] in p and builder.FRAMING in p
    assert "Seen from behind" not in p
