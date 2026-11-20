import json

from spritewaffle import cli
from spritewaffle.export import aseprite
from synth import write_clip


def test_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_clip(tmp_path / "walk.mp4", frames=48)
    assert cli.main(["run", "walk.mp4", "--character", "dude", "--action", "walk", "--facing", "S", "--job-id", "j"]) == 0
    job = tmp_path / "jobs" / "dude" / "j"
    a = job / "03_actions" / "S" / "walk"
    assert (a / "contact_sheet.png").exists() and (a / "selected_12f").is_dir() and (a / "selected_24f").is_dir()
    sel = json.loads((a / "selection_report.json").read_text())
    assert len(sel["sets"]["12"]) == 12 and len(sel["sets"]["24"]) == 24 and all(e["reason"] for e in sel["sets"]["12"])
    for n in ("12f", "24f"):
        r = json.loads((job / "05_qa" / "S" / "walk" / n / "report.json").read_text())
        assert r["status"] == "pass" and r["placements_identical"]
        out = job / "06_export" / "S" / "walk" / n
        doc = aseprite.read(out / f"walk_S_{n}.aseprite")
        assert doc.tags == [("walk_S", 0, int(n[:-1]) - 1, "forward")]
        assert (out / f"walk_S_{n}.png").exists() and (out / f"walk_S_{n}_preview.gif").exists()
    px = json.loads((job / "04_pixel" / "S" / "walk" / "pixel_report.json").read_text())
    assert px["grid"]["size"] == 8 and len(px["palette"]) <= 8
