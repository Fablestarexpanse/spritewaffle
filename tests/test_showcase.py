import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.export import showcase
from synth import draw_sprite, render


def _job(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    for f in ("S", "E", "N", "W"):
        Image.fromarray(render(draw_sprite(0), scale=8, offset=(80, 40), canvas=(256, 256))).save(job.root / "02_facings" / f"{f}.png")
    art = np.zeros((20, 20, 4), np.uint8)
    for f in ("S", "E"):
        frames = []
        for i in range(12):
            a = art.copy(); a[4:16, 6 + i % 2:12 + i % 2] = (200, 30, 30, 255); frames.append(a)
        stages._write_pixel_sets(job, GameProfile(name="p", cell_size=32, sprite_height_px=24), f, "walk",
                                 {"12": (frames, list(range(12)))}, np.array([[200, 30, 30]], np.uint8), {})
    return job


def test_showcase_has_turnaround_then_actions(tmp_path):
    job = _job(tmp_path)
    out = showcase.for_job(job, GameProfile(name="p"), size=384)
    gif = Image.open(out["file"])
    # turnaround = the game sprite of each animated facing (S, E), 2 turns; 2 loops x 12; 1 end card
    assert gif.size == (384, 384) and gif.n_frames == out["frames"] == 2 * 2 + 24 + 1
    assert [s["section"] for s in out["sections"]] == ["turnaround", "walk", "end card"]
    assert out["sections"][0]["facings"] == ["S", "E"]
    assert out["sections"][1]["facings"] == ["S", "E"]
    assert job.read_meta()["stages"]["export:showcase"]["status"] == "done"


def test_showcase_refuses_empty_job(tmp_path):
    with pytest.raises(RuntimeError, match="nothing to show"):
        showcase.for_job(Job.create("x", "y", base=tmp_path), GameProfile(name="p"))


def test_showcase_is_branded(tmp_path):
    """Ronan 2026-11-26: the example GIF must be branded properly and cleanly."""
    job = _job(tmp_path)
    out = showcase.for_job(job, GameProfile(name="p"), size=512)
    gif = Image.open(out["file"])
    first = np.array(gif.convert("RGB"))
    assert (np.abs(first[5, 200].astype(int) - showcase.BRAND_DEEP).max() <= 8)          # header bar in brand purple
    gif.seek(gif.n_frames - 1)
    last = np.array(gif.convert("RGB")).reshape(-1, 3)
    gold = (np.abs(last.astype(int) - showcase.ACCENT).max(1) <= 30).sum()
    assert gold > 500                                                                    # the logo on the end card
    assert showcase._brand_image("horizontal-logo.png", 50) is not None
