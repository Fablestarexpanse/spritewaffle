"""Audit additions: paths, mirror, batch animate, queue retry/clear, archive, doctor, CLI errors."""
import json

import numpy as np
import pytest
from PIL import Image

from spritewaffle import cli, paths
from spritewaffle.core import stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.core.queue import Queue


def test_paths_follow_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    monkeypatch.delenv("SPRITEWAFFLE_JOBS", raising=False)
    assert paths.root() == tmp_path.resolve() and paths.jobs() == tmp_path.resolve() / "jobs"
    assert paths.templates() == tmp_path.resolve() / "templates"


def test_templates_found_from_any_directory(tmp_path, monkeypatch):
    from spritewaffle.comfy import templates
    monkeypatch.chdir(tmp_path)                                    # not the repo root
    wf, mp = templates.load("h3_action_i2v")
    assert mp["slot"] == "h3_action_i2v"


def _pixelized(job, facing="E", action="walk"):
    """A finished 04_pixel action with an asymmetric sprite (left half red)."""
    art = np.zeros((20, 20, 4), np.uint8)
    art[4:16, 6:10] = (200, 0, 0, 255)
    art[4:16, 10:14] = (0, 0, 200, 255)
    stages._write_pixel_sets(job, GameProfile(name="p", cell_size=32, sprite_height_px=24), facing, action,
                             {"12": ([art] * 12, list(range(12)))}, np.array([[200, 0, 0], [0, 0, 200]], np.uint8),
                             {"grid": {"size": 1}})
    d = job.action_dir(facing, action)
    (d / "selection_report.json").write_text(json.dumps({"loop": True}))


def test_mirror_action_flips_partner(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _pixelized(job)
    out = stages.mirror_action(job, GameProfile(name="p", cell_size=32, sprite_height_px=24), "W", "walk")
    e = np.array(Image.open(job.root / "04_pixel/E/walk/12f/frames/000.png"))
    w = np.array(Image.open(job.root / "04_pixel/W/walk/12f/frames/000.png"))
    assert out["method"] == "mirror" and out["source"] == "E"
    np.testing.assert_array_equal(np.nonzero(w[..., 3])[0], np.nonzero(e[:, ::-1, 3])[0])
    assert stages.qa(job, GameProfile(name="p", cell_size=32, sprite_height_px=24), "W", "walk")
    with pytest.raises(RuntimeError, match="mirror_allowed"):
        stages.mirror_action(job, GameProfile(name="p", mirror_allowed=False), "W", "walk")
    with pytest.raises(FileNotFoundError, match="not pixelized"):
        stages.mirror_action(job, GameProfile(name="p"), "NW", "walk")


def test_batch_animate_mirrors_west_side(tmp_path):
    q = Queue(tmp_path)
    ts = q.submit_animate(tmp_path / "hero/j", ["S", "E", "W"], ["walk"])
    stages_by_facing = {}
    for t in ts:
        stages_by_facing.setdefault(t["args"]["facing"], []).append(t["stage"])
    assert stages_by_facing["W"] == ["mirror", "qa", "export"]
    assert stages_by_facing["E"][0] == "action" and stages_by_facing["S"][0] == "action"
    e_pix = next(t for t in ts if t["args"]["facing"] == "E" and t["stage"] == "pixelize")
    w_mirror = next(t for t in ts if t["args"]["facing"] == "W" and t["stage"] == "mirror")
    assert w_mirror["after"] == [e_pix["id"]]
    no_mirror = q.submit_animate(tmp_path / "hero/j", ["W"], ["idle"])     # partner not requested -> render
    assert no_mirror[0]["stage"] == "action"


def test_queue_retry_and_clear(tmp_path):
    q = Queue(tmp_path)
    a = q.submit(tmp_path / "x", "qa", {"facing": "S", "action": "walk"})
    with pytest.raises(ValueError):
        q.retry(a["id"])
    q.update(a["id"], status="failed")
    b = q.retry(a["id"])
    assert b["stage"] == "qa" and b["status"] == "queued" and b["id"] != a["id"]
    q.update(b["id"], status="done")
    assert q.clear() == 1 and [t["id"] for t in q.list()] == [a["id"]]
    assert q.clear(("failed",)) == 1 and q.list() == []


def test_archive_moves_job(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    dest = job.archive()
    assert dest == tmp_path / "_archive" / "hero" / "j" and (dest / "job.json").exists()
    assert not (tmp_path / "hero").exists()


def test_doctor_runs_without_comfy(monkeypatch):
    from spritewaffle import doctor
    rows = doctor.check("http://127.0.0.1:1")
    names = {r[1]: r[0] for r in rows}
    assert names["ComfyUI"] == doctor.FAIL and names["python"] == doctor.OK and names["jobs folder"] == doctor.OK
    assert "[FAIL]" in doctor.render(rows)


def test_cli_known_errors_print_one_line(capsys):
    assert cli.main(["approve", "anchor", "--job", "nobody/none"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "Traceback" not in err
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "spritewaffle 0.2.0" in capsys.readouterr().out
