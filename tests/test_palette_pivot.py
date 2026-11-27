"""One palette per job and one feet pivot per character (audit findings 3 and 4)."""
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import job_palette, stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.core.queue import Queue
from spritewaffle.export import aseprite, character
from spritewaffle.frames import layout
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render, write_clip

PROF = GameProfile(name="p", cell_size=32, sprite_height_px=24)


def _stills(job):
    Image.fromarray(render(draw_sprite(), canvas=(256, 256))).save(job.root / "01_anchor" / "anchor.png")
    for f, step in (("S", 0), ("E", 1), ("N", 2)):
        Image.fromarray(render(draw_sprite(step), canvas=(256, 256), seed=step)).save(job.root / "02_facings" / f"{f}.png")


def test_load_palette_files(tmp_path):
    gpl = tmp_path / "p.gpl"
    gpl.write_text("GIMP Palette\nName: t\n#\n  0   0   0\tblack\n255 0 77 red\n")
    assert job_palette.load_file(gpl) == ["#000000", "#ff004d"]
    hx = tmp_path / "p.hex"
    hx.write_text("1d2b53\n#7e2553\n\n")
    assert job_palette.load_file(hx) == ["#1d2b53", "#7e2553"]
    im = np.zeros((2, 2, 4), np.uint8)
    im[0, 0] = (10, 20, 30, 255)
    im[1, 1] = (40, 50, 60, 255)
    Image.fromarray(im).save(tmp_path / "p.png")
    assert job_palette.load_file(tmp_path / "p.png") == ["#0a141e", "#28323c"]


def test_every_clip_of_a_job_shares_the_palette_built_from_its_stills(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _stills(job)
    clip = tmp_path / "w.mp4"
    write_clip(clip, frames=48)
    for f in ("S", "E"):
        stages.extract(job, clip, f, "walk")
        stages.select(job, f, "walk")
        stages.pixel(job, PROF, f, "walk")
    jp = job_palette.get(job)
    assert jp and jp["source"].startswith("anchor + facings (4 stills)")
    pals = [json.loads((job.root / f"04_pixel/{f}/walk/pixel_report.json").read_text())["palette"] for f in ("S", "E")]
    assert pals[0] == pals[1] == jp["colours"]


def test_job_without_stills_locks_its_first_clip(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    clip = tmp_path / "w.mp4"
    write_clip(clip, frames=48)
    stages.extract(job, clip, "S", "walk")
    stages.select(job, "S", "walk")
    stages.pixel(job, PROF, "S", "walk")
    assert job_palette.get(job)["source"] == "first pixelized clip (S/walk)"


def test_feet_on_centre_line_whatever_the_weapon_does():
    body = np.zeros((40, 80, 4), np.uint8)
    body[5:40, 20:30] = 255                     # character, feet at x 20..30
    swing = body.copy()
    swing[10:14, 30:50] = 255                   # weapon out to the right: bbox centre moves, feet don't
    for frames in ([body, body], [body, swing]):
        cells, places = layout.preserve_canvas(frames, (64, 64))
        assert places[0].pivot == (32.0, 63.0)
        cols = np.where(cells[0][-3:, :, 3].any(0))[0]
        assert (cols.min() + cols.max() + 1) / 2 == 32


def test_too_wide_action_is_shifted_and_says_where_the_feet_are():
    f = np.zeros((40, 100, 4), np.uint8)
    f[5:40, 10:20] = 255                        # feet at 10..20
    f[10:14, 20:68] = 255                       # 58 px wide in a 64 px cell: can't centre the feet
    cells, places = layout.preserve_canvas([f], (64, 64))
    assert cells[0][..., 3].any(0).sum() == 58  # nothing cut off
    assert places[0].pivot[0] != 32.0 and places[0].pivot[1] == 63.0


def test_pivot_slice_round_trips_and_character_has_one_pivot(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _stills(job)
    clip = tmp_path / "w.mp4"
    write_clip(clip, frames=48)
    stages.extract(job, clip, "S", "walk")
    stages.select(job, "S", "walk")
    stages.pixel(job, PROF, "S", "walk")
    stages.mirror_action(job, PROF, "N", "walk", source="S")
    for f in ("S", "N"):
        stages.qa(job, PROF, f, "walk")
    out = stages.export(job, PROF, "S", "walk")
    doc = aseprite.read(out["12f"]["aseprite"])
    assert doc.slices["pivot"][0][5:] == (16, 31)
    res = character.export(job.root, job.root / "06_export" / "character", "hero", lambda a: 12, require_pass=False)
    meta = json.loads(open(res["json"]).read())
    assert meta["pivot"] == [16.0, 31.0] and meta["pivot_norm"] == [0.5, 1 - 31 / 32]
    assert meta["palette"] == job_palette.get(job)["colours"]            # the job palette, in its order
    assert aseprite.read(res["aseprite"]).slices["pivot"] == [(0, 0, 0, 32, 32, 16, 31)]


def test_reprocess_chains_mirrors_after_their_source(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    for f, method in (("E", None), ("W", "mirror")):
        d = job.root / "04_pixel" / f / "walk"
        d.mkdir(parents=True)
        (d / "pixel_report.json").write_text(json.dumps({"palette": [], "method": method, "source": "E"} if method
                                                        else {"palette": []}))
    ts = Queue(tmp_path).submit_reprocess(job.root)
    assert [t["stage"] for t in ts] == ["pixelize", "qa", "export", "mirror", "qa", "export"]
    assert ts[3]["after"] == [ts[0]["id"]] and ts[3]["args"]["source"] == "E"


def test_palette_endpoint_load_and_stale(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    d = job.root / "04_pixel" / "S" / "walk"
    d.mkdir(parents=True)
    (d / "pixel_report.json").write_text(json.dumps({"palette": ["#ffffff"]}))
    (tmp_path / "p.hex").write_text("000000\nff004d\n")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.post("/api/jobs/hero/j/palette", json={"op": "file", "file": str(tmp_path / "p.hex")}).json()
        assert r["colours"] == ["#000000", "#ff004d"] and r["stale"] == ["walk S"]
        assert c.get("/api/jobs/hero/j").json()["palette"]["source"] == "file p.hex"
        assert c.post("/api/jobs/hero/j/palette", json={"op": "nope"}).status_code == 400
        assert len(c.post("/api/jobs/hero/j/run", json={"stage": "reprocess"}).json()) == 3


def test_shifted_action_keeps_off_the_border():
    f = np.zeros((40, 100, 4), np.uint8)
    f[5:40, 10:20] = 255
    f[10:14, 20:60] = 255                       # 50 px wide: fits only if moved off centre
    cells, _ = layout.preserve_canvas([f], (64, 64))
    a = cells[0][..., 3] > 0
    assert not (a[:, 0].any() or a[:, -1].any())


def test_extend_keeps_the_base_and_adds_only_what_is_new():
    from spritewaffle.pixel import palette as palmod
    from spritewaffle.pixel.color import srgb_to_oklab
    base = srgb_to_oklab(np.array([[220, 150, 127], [40, 30, 30]], float))
    img = np.zeros((1, 8, 8, 3))
    img[0, :, :4] = [220, 150, 127]                     # skin: the base draws it
    img[0, :, 4:] = [60, 80, 160]                       # a blue cloak: new
    lab = srgb_to_oklab(img)
    alpha = np.ones((1, 8, 8), bool)
    out = palmod.extend(lab, alpha, base, 4)
    assert np.allclose(out[:2], base) and len(out) == 3                 # base first, exactly; one blue added
    assert len(palmod.extend(lab[:, :, :4], alpha[:, :, :4], base, 4)) == 2   # nothing new -> base only


def test_variant_palette_keeps_its_base_colours_exactly(tmp_path):
    """2026-11-27: the vest body and the cloak body over it shared 0 of 15 colours (the skin moved)."""
    prof = GameProfile(name="p", cell_size=64, sprite_height_px=40)
    base = Job.create("hero", "base", base=tmp_path, description="hero")
    _stills(base)
    job_palette.rebuild(base, prof)
    var = Job.create("hero", "cloak", base=tmp_path, base_job=str(base.root), item_description="a blue cloak")
    for p in sorted((base.root / "01_anchor").glob("*.png")) + sorted((base.root / "02_facings").glob("*.png")):
        a = np.array(Image.open(p).convert("RGB"))
        keyed = (a[..., 1] > 200) & (a[..., 0] < 90)
        ys, xs = np.where(~keyed)
        a[ys.min():ys.min() + (ys.max() - ys.min()) // 2, xs.min():xs.max()] = [40, 60, 170]   # cloak on top half
        dest = var.root / p.relative_to(base.root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(a).save(dest)
    got = job_palette.rebuild(var, prof)
    base_cols = job_palette.get(base)["colours"]
    assert got["colours"][:len(base_cols)] == base_cols                 # every base colour, same hex, same order
    assert 0 < len(got["colours"]) - len(base_cols) <= prof.palette_size // 2
    assert "family" in got["source"] and "hero/base" in got["source"]
