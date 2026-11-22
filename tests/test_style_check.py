import json

from fastapi.testclient import TestClient

from spritewaffle import cli
from spritewaffle.core import job_palette, project
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.mcp_server import build
from spritewaffle.qa import style_check
from spritewaffle.ui.server import create_app
from test_mcp import call, text


MASTER = ["#080707", "#eff1f2", "#cb7957"]


def clip(job, facing, action, report):
    p = job.root / "04_pixel" / facing / action / "pixel_report.json"
    p.parent.mkdir(parents=True)
    p.write_text(report if isinstance(report, str) else json.dumps(report), encoding="utf-8")
    return p


def test_project_style_check_allows_palette_subsets_and_preserves_files(tmp_path, monkeypatch):
    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    GameProfile(name="game-look", cell_size=80).save(tmp_path / "profiles/game-look.json")
    project.set_style(base, {"default_style": "pixel", "default_profile": "game-look"})
    project.set_palette(base, MASTER)
    job = Job.create("hero", "one", base=base)
    job_palette.save(job, ["#080707", "#eff1f2"], "asset selection")
    p = clip(job, "S", "walk", {"palette": ["#080707", "#EFF1F2"], "sets": {"12": {}}})
    watched = [p, job.meta_path, job_palette.path(job), project.project_path(base)]
    original = [path.read_bytes() for path in watched]

    result = style_check.inspect(job)
    assert result["asset_id"] == "hero/one"
    assert result["classification"] == "pass" and result["clips_checked"] == 1
    assert result["asset"]["palette"]["origin"] == "job" and result["findings"] == []
    assert [path.read_bytes() for path in watched] == original


def test_style_check_separates_current_settings_from_processed_clip_drift(tmp_path):
    base = tmp_path / "jobs"
    project.set_style(base, {"default_style": "pixel", "default_profile": "default"})
    project.set_palette(base, MASTER)
    job = Job.create("hero", "one", base=base, style="painted")
    clip(job, "E", "walk", {"style": "painted", "palette": [], "sets": {"12": {}}})
    clip(job, "S", "idle", {"palette": ["#080707", "#ffffff"], "sets": {"12": {}}})
    result = style_check.inspect(job)
    assert result["classification"] == "warn" and result["clips_checked"] == 2
    issues = {item["code"]: item for item in result["findings"]}
    assert issues.keys() == {"asset_style", "clip_style", "clip_palette"}
    assert issues["clip_style"]["facing"] == "E" and issues["clip_style"]["action"] == "walk"
    assert issues["clip_palette"]["colours"] == ["#ffffff"]
    assert issues["clip_palette"]["facing"] == "S" and issues["clip_palette"]["action"] == "idle"


def test_reports_unverifiable_clip_metadata_and_unconfigured_projects(tmp_path):
    base = tmp_path / "jobs"
    job = Job.create("hero", "one", base=base)
    result = style_check.inspect(job)
    assert result["classification"] == "review"
    assert result["findings"][0]["code"] == "project_style_unconfigured"

    project.set_palette(base, MASTER)
    clip(job, "N", "walk", "{broken")
    clip(job, "S", "idle", {"sets": {"12": {}}})
    result = style_check.inspect(job)
    assert result["classification"] == "review" and result["clips_checked"] == 1
    assert [item["code"] for item in result["findings"]] == ["clip_report_unreadable", "clip_palette_unavailable"]


def test_job_screen_stays_available_when_style_check_evidence_is_missing_or_invalid(tmp_path):
    base = tmp_path / "jobs"
    project.set_palette(base, MASTER)
    job = Job.create("hero", "one", base=base)
    clip(job, "N", "walk", "{broken")
    (job.root / "04_pixel" / "S" / "idle" / "12f" / "frames").mkdir(parents=True)
    with TestClient(create_app(base, worker=False), raise_server_exceptions=False) as client:
        assert client.get("/api/jobs/hero/one").status_code == 200
        report = client.get("/api/jobs/hero/one/style-check").json()
    assert report["classification"] == "review" and report["clips_checked"] == 0
    assert [item["code"] for item in report["findings"]] == ["clip_report_unreadable", "clip_report_missing"]


def test_style_check_agrees_across_ui_http_cli_and_mcp(tmp_path, monkeypatch, capsys):
    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    GameProfile(name="project-look").save(tmp_path / "profiles/project-look.json")
    project.set_style(base, {"default_profile": "project-look"})
    project.set_palette(base, MASTER)
    job = Job.create("hero", "one", base=base, profile=None)
    job_palette.save(job, ["#ffffff"], "override")
    with TestClient(create_app(base, worker=False)) as client:
        page = client.get("/").text
        assert 'id="jStyleCheck"' in page
        assert 'id="styleCheckDialog"' in page
        assert client.get("/api/jobs/missing/one/style-check").status_code == 404
        report = client.get("/api/jobs/hero/one/style-check").json()
    assert [finding["code"] for finding in report["findings"]] == ["asset_profile", "asset_palette"]
    assert cli.main(["style-check", "--job", "hero/one"]) == 0
    assert json.loads(capsys.readouterr().out) == report
    mcp, _ = build(base)
    assert text(call(mcp, "style_check", character="hero", job_id="one")) == report
