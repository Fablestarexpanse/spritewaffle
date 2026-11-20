"""Art styles: prompt wording, smooth post-processing, RGBA export, pixel-only stages refuse."""
import json

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.export import aseprite
from spritewaffle.pixel import smooth
from spritewaffle.prompts import builder, styles
from synth import draw_sprite, render, write_clip


def test_prompts_follow_the_style():
    p = GameProfile(name="p")
    styles.use("pixel")
    assert "pixel-art" in builder.anchor("a knight", p)
    styles.use("anime")
    a = builder.anchor("a knight", p)
    assert "Anime cel-shaded" in a and "pixel" not in a and "#00FF00" in a
    assert "anime cel-shaded look" in builder.action_video("walk", "S", 2, True)
    assert "pixel size" not in builder.anchor_from_hero("an orc", p)
    styles.use("pixel")
    with pytest.raises(ValueError):
        styles.get("watercolour")


def test_smooth_scales_whole_clip_with_soft_edges():
    frames = [render(draw_sprite(i), scale=8, offset=(40, 20), canvas=(256, 256), seed=i) for i in range(3)]
    out, k = smooth.process(frames, target_height=96)
    assert abs(k - 96 / (24 * 8)) < 0.05
    ys = np.where((out[0][..., 3] > 0).any(1))[0]
    assert abs((ys[-1] - ys[0] + 1) - 96) <= 3
    a = out[0][..., 3]
    assert ((a > 0) & (a < 255)).any()                        # anti-aliased edge
    g = out[0][a > 0][:, :3].astype(int)
    assert not ((g[:, 1] > g[:, 0] + 60) & (g[:, 1] > g[:, 2] + 60)).any()   # no green fringe


def test_smooth_pipeline_exports_rgba(tmp_path):
    job = Job.create("hero", "j", base=tmp_path, style="painted")
    clip = tmp_path / "w.mp4"
    write_clip(clip, frames=48)
    prof = GameProfile(name="p", cell_size=32, sprite_height_px=24)
    stages.extract(job, clip, "S", "walk")
    stages.select(job, "S", "walk")
    info = stages.pixel(job, prof, "S", "walk")
    assert info["style"] == "painted" and info["palette"] == [] and info["cell"] == 128
    assert not (job.root / "04_pixel/S/walk/12f/indices.npy").exists()
    assert stages.qa(job, prof, "S", "walk")["12f"] in ("pass", "fail")
    out = stages.export(job, prof, "S", "walk")
    doc = aseprite.read(out["12f"]["aseprite"])
    assert doc.depth == 32 and doc.width == 128
    w = stages.mirror_action(job, prof, "N", "walk", source="S")    # mirroring works on full colour too
    assert w["palette"] == [] and w["cell"] == 128


def test_pixel_only_stages_refuse_other_styles(tmp_path):
    from spritewaffle.stack import stage as stack_stage
    job = Job.create("hero", "j", base=tmp_path, style="comic")
    job.set_stage("facings", "approved")
    with pytest.raises(RuntimeError, match="pixel art only"):
        stages.flow_transfer(job, GameProfile(name="p"), "S", "walk", "m")
    with pytest.raises(RuntimeError, match="pixel art only"):
        stack_stage.build(job, GameProfile(name="p"))
