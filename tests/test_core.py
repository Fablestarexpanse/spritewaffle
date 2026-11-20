import pytest

from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile, resolve


def test_profile_roundtrip(tmp_path):
    p = GameProfile(name="hero", palette=["#000000", "#ffffff"], outline="dark_1px")
    p.save(tmp_path / "hero.json")
    q = resolve("hero", tmp_path)
    assert q == p and q.palette_size == 2 and q.locked_palette == ["#000000", "#ffffff"]


def test_profile_rejects_bad_values():
    with pytest.raises(ValueError):
        GameProfile(name="x", projection="3d")


def test_job_layout_and_meta(tmp_path):
    job = Job.create("knight", "j1", base=tmp_path, source="a.mp4")
    assert (job.root / "04_pixel").is_dir()
    job.set_stage("extract", "done", frames=10)
    job.log_provenance("raw.mp4", model="h3", seed=1)
    meta = Job.open(job.root).read_meta()
    assert meta["stages"]["extract"]["frames"] == 10
    assert meta["provenance"][0]["seed"] == 1
    assert meta["inputs"]["source"] == "a.mp4"
