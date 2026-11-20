"""Every test gets its own jobs folder: nothing a test does can touch the real jobs/."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_jobs(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path_factory.mktemp("jobs")))
