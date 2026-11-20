"""Generation stages with a stub ComfyUI client (no network)."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import generate
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.prompts import builder
from synth import draw_sprite, render


class StubClient:
    """Records calls; 'renders' the synthetic sprite (flipped for W-ish targets) on off-green noise."""

    def __init__(self, drift_for=()):
        self.calls = []
        self.drift_for = set(drift_for)

    def run_template(self, slot, values, out_dir):
        self.calls.append((slot, values))
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        target = next((t for t in builder.VIEW if f", {builder.VIEW[t]}, in the same" in values["prompt"]), "S")
        lab = draw_sprite(0)
        if target in self.drift_for:
            lab = np.where(lab >= 0, 4, -1)                     # all red: colour drift
        img = render(lab, scale=8, offset=(60, 40), canvas=(256, 256), bg=(20, 235, 35), noise=6)
        if "W" in target:
            img = img[:, ::-1]
        p = out_dir / "out.png"
        Image.fromarray(img).save(p)
        return {"slot": slot, "prompt_id": "x", "values": values, "files": [str(p)]}


@pytest.fixture
def job(tmp_path):
    j = Job.create("hero", "j", base=tmp_path)
    anchor = tmp_path / "a.png"
    Image.fromarray(render(draw_sprite(0), scale=8, offset=(60, 40), canvas=(256, 256))).save(anchor)
    generate.anchor(j, GameProfile(name="p"), image=anchor)
    return j


def test_facings_refuse_unapproved_anchor(job):
    with pytest.raises(RuntimeError, match="approve"):
        generate.facings(job, GameProfile(name="p"), client=StubClient())


def test_flatten_makes_background_exact_green(job):
    img = np.array(Image.open(job.root / "01_anchor" / "anchor.png"))
    assert tuple(img[0, 0]) == (0, 255, 0) and tuple(img[-1, -1]) == (0, 255, 0)


def test_staged_facings_nearest_refs_and_order(job):
    generate.approve(job, "anchor")
    c = StubClient()
    rep = generate.facings(job, GameProfile(name="p"), client=c, seed=1)
    targets = [next(t for t in builder.VIEW if f", {builder.VIEW[t]}, in the same" in v["prompt"]) for _, v in c.calls]
    assert targets[:3] == ["E", "N", "W"] and set(targets[3:]) == {"SE", "NE", "NW", "SW"}
    for _, v in c.calls:
        assert len(v["ref_images"]) == 1                     # nearest: one reference
    ne = next(v for _, v in c.calls if "turned toward screen right" in v["prompt"] and "back" in v["prompt"])
    assert Path(ne["ref_images"][0]).name == "N.png"
    assert set(rep["facings"]) == {"S", "E", "N", "W", "SE", "NE", "NW", "SW"}
    for f in rep["facings"]:
        assert tuple(np.array(Image.open(job.root / "02_facings" / f"{f}.png"))[0, 0]) == (0, 255, 0)


def test_multi_mode_uses_anchor_plus_cardinals(job):
    generate.approve(job, "anchor")
    c = StubClient()
    generate.facings(job, GameProfile(name="p"), client=c, diagonals="multi")
    ne = [v for _, v in c.calls if builder.VIEW["NE"] in v["prompt"].split("Draw this exact character again, ")[1]][0]
    assert [Path(p).name for p in ne["ref_images"]] == ["S.png", "N.png", "E.png"]


def test_drifting_facing_is_mirrored_from_partner(job):
    generate.approve(job, "anchor")
    rep = generate.facings(job, GameProfile(name="p"), client=StubClient(drift_for={"W"}))
    assert rep["mirrored"].get("W", {}).get("from") == "E"
    e = np.array(Image.open(job.root / "02_facings" / "E.png"))
    w = np.array(Image.open(job.root / "02_facings" / "W.png"))
    np.testing.assert_array_equal(w, e[:, ::-1])


def test_prompts_use_semantic_diagonal_text():
    assert "mostly back, plus left side" in builder.facing("NW", [], "N")
    assert "#00FF00" in builder.anchor("a knight", GameProfile(name="p"))
