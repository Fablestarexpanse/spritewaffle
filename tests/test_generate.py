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


# --- step 2: actions + bridges ----------------------------------------------------------------
import cv2
from synth import write_clip


class VideoStub(StubClient):
    """Image slots as StubClient; h3_* slots write an mp4 (frozen for FL2VA when frozen_fl2va)."""

    def __init__(self, frozen_fl2va=False):
        super().__init__()
        self.frozen_fl2va = frozen_fl2va

    def run_template(self, slot, values, out_dir):
        if not slot.startswith("h3_"):
            return super().run_template(slot, values, out_dir)
        self.calls.append((slot, values))
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "clip.mp4"
        if slot == "h3_action_fl2va" and self.frozen_fl2va:
            img = cv2.cvtColor(render(draw_sprite(0), scale=8, offset=(60, 40), canvas=(256, 256)), cv2.COLOR_RGB2BGR)
            vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 24, (256, 256))
            for _ in range(24):
                vw.write(img)
            vw.release()
        else:
            write_clip(p, frames=24, canvas=(320, 320))
        return {"slot": slot, "prompt_id": "v", "values": values, "files": [str(p)]}


@pytest.fixture
def ready(job):
    generate.approve(job, "anchor")
    generate.facings(job, GameProfile(name="p"), client=StubClient())
    return job


def test_action_requires_approved_facings(ready):
    with pytest.raises(RuntimeError, match="facings"):
        generate.action(ready, GameProfile(name="p"), "E", "walk", client=VideoStub())


def test_cyclic_action_transition_first_and_last(ready):
    generate.approve(ready, "facings")
    c = VideoStub()
    rep = generate.action(ready, GameProfile(name="p"), "E", "walk", client=c)
    slots = [s for s, _ in c.calls[-2:]]
    assert slots == ["transition_pose", "h3_action_fl2va"]
    v = c.calls[-1][1]
    assert Path(v["first_frame"]).name == Path(v["last_frame"]).name == "transition.png"
    assert v["prompt"].startswith("How the reference pictures align") and "marches in place" in v["prompt"]
    assert rep["mode_used"] == "fl2va" and (ready.root / "03_actions/E/walk/extracted").is_dir()


def test_frozen_fl2va_falls_back_to_i2v(ready):
    generate.approve(ready, "facings")
    c = VideoStub(frozen_fl2va=True)
    rep = generate.action(ready, GameProfile(name="p"), "E", "walk", client=c)
    assert rep["fl2va_frozen"]["frozen"] and rep["mode_used"] == "i2v"
    assert c.calls[-1][0] == "h3_action_i2v" and "last_frame" not in c.calls[-1][1]
    assert (ready.root / "03_actions/E/walk/raw_frozen_fl2va.mp4").exists()


def test_one_shot_action_ends_on_idle_facing(ready):
    generate.approve(ready, "facings")
    c = VideoStub()
    generate.action(ready, GameProfile(name="p"), "E", "attack", client=c)
    assert Path(c.calls[-1][1]["last_frame"]).name == "E.png"


def test_video_bridge_keeps_middle_frame(ready):
    c = VideoStub()
    f = ready.root / "02_facings"
    out = generate.bridge(ready, f / "E.png", f / "W.png", ready.root / "b" / "x.png", client=c)
    assert c.calls[-1][0] == "h3_action_fl2va" and out.exists()
    assert tuple(np.array(Image.open(out))[0, 0]) == (0, 255, 0)


# --- experimental motion library + TARA transfer ------------------------------------------------
from spritewaffle.core import motion


def _library_clip(tmp_path, job):
    """A finished action in another job, added to the library."""
    src = Job.create("mannequin", "m", base=tmp_path)
    d = src.action_dir("S", "walk")
    write_clip(d / "raw.mp4", frames=30)
    return motion.add("walk_S", src, "S", "walk", base=tmp_path)


def test_motion_library_add_approve_list(ready, tmp_path):
    meta = _library_clip(tmp_path, ready)
    assert meta["status"] == "review" and meta["frames"] == 30
    with pytest.raises(ValueError):
        motion.add("bad name!", ready, "S", "walk", base=tmp_path)
    assert motion.approve("walk_S", tmp_path)["status"] == "approved"
    assert [m["name"] for m in motion.list_all(tmp_path)] == ["walk_S"]


def test_transfer_needs_approved_motion_and_uses_facing_as_identity(ready, tmp_path):
    generate.approve(ready, "facings")
    _library_clip(tmp_path, ready)
    c = VideoStub()
    with pytest.raises(RuntimeError, match="approve"):
        generate.transfer(ready, GameProfile(name="p"), "S", "walk", "walk_S", client=c)
    motion.approve("walk_S", tmp_path)
    rep = generate.transfer(ready, GameProfile(name="p"), "S", "walk", "walk_S", client=c)
    slot, v = c.calls[-1]
    assert slot == "h3_tara_transfer" and Path(v["ref_images"][0]).name == "S.png"
    assert Path(v["ref_video"]).name == "clip.mp4" and v["frames"] == 22          # 30 -> 17n+5 <= 30
    assert rep["experimental"] and rep["mode_used"] == "tara" and "mean" in rep["identity_drift"]
    assert (ready.root / "03_actions/S/walk/extracted").is_dir()


def test_pipeline_with_motion_starts_with_transfer(ready, tmp_path):
    from spritewaffle.core.queue import Queue
    q = Queue(tmp_path)
    ts = q.submit_action_pipeline(ready.root, "S", "walk", motion="walk_S")
    assert [t["stage"] for t in ts] == ["transfer", "select", "pixelize", "qa", "export"]
    assert ts[0]["resource"] == "gpu" and ts[0]["args"]["motion"] == "walk_S"


# --- experimental pixel-exact flow transfer ---------------------------------------------------------
from spritewaffle.core import stages


def test_flow_transfer_stage_then_qa_export(ready, tmp_path):
    generate.approve(ready, "facings")
    _library_clip(tmp_path, ready)
    prof = GameProfile(name="p")
    with pytest.raises(RuntimeError, match="approve"):
        stages.flow_transfer(ready, prof, "S", "walk", "walk_S")
    motion.approve("walk_S", tmp_path)
    info = stages.flow_transfer(ready, prof, "S", "walk", "walk_S")
    assert info["method"] == "flow" and set(info["sets"]) == {"12", "24"}
    palette = {tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in info["palette"]}
    cells = np.stack([np.array(Image.open(p)) for p in sorted((ready.root / "04_pixel/S/walk/12f/frames").glob("*.png"))])
    used = {tuple(c) for c in cells[cells[..., 3] > 0][:, :3].tolist()}
    assert used <= palette                                   # only the facing's own pixels
    qa = stages.qa(ready, prof, "S", "walk")
    assert set(qa) == {"12f", "24f"}
    out = stages.export(ready, prof, "S", "walk")
    assert Path(out["12f"]["aseprite"]).exists()


def test_flow_pipeline_chain(ready, tmp_path):
    from spritewaffle.core.queue import Queue
    ts = Queue(tmp_path).submit_action_pipeline(ready.root, "S", "walk", motion="walk_S", method="flow")
    assert [t["stage"] for t in ts] == ["flow", "qa", "export"] and ts[0]["resource"] == "cpu"
