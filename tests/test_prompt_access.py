"""Access to the prompts: see what will be sent, what was sent, edit the creative text only."""
import pytest
from fastapi.testclient import TestClient

from spritewaffle.core import generate, prompt_view
from spritewaffle.core.job import Job
from spritewaffle.prompts import builder
from spritewaffle.ui.server import create_app


@pytest.fixture
def job(tmp_path):
    return Job.create("hero", "j", base=tmp_path)


def test_edited_action_text_wins_and_keeps_the_rest_of_the_preset(job):
    prompt_view.set_action(job, "walk", {"motion": "limps forward in place, dragging the left leg"})
    spec = generate.resolve_action_spec(job, "walk")
    assert spec["motion"].startswith("limps") and spec["transition"] == builder.ACTIONS["walk"]["transition"]
    assert spec["cyclic"] is True and spec["source"] == "edited"
    video = builder.action_video("walk", "S", 2.0, True, spec)
    assert "limps forward" in video and "#00FF00" in video and "must not turn" in video  # rules still there
    prompt_view.set_action(job, "walk", {})                                              # all empty = reset
    assert generate.resolve_action_spec(job, "walk") == builder.ACTIONS["walk"]


def test_new_action_needs_motion_and_transition(job):
    prompt_view.set_action(job, "cast spell", {"motion": "raises the staff and a spark appears"})
    with pytest.raises(ValueError, match="transition"):
        generate.resolve_action_spec(job, "cast spell")
    prompt_view.set_action(job, "cast spell", {"motion": "raises the staff and a spark appears",
                                               "transition": "staff lifted slightly"})
    spec = generate.resolve_action_spec(job, "cast spell")
    assert spec["cyclic"] is False and "staff lifted" in builder.transition("cast spell", "E", spec)


def test_facing_notes_go_into_the_facing_prompt(job):
    prompt_view.set_facing_note(job, "*", "the quiver is always on the back")
    prompt_view.set_facing_note(job, "N", "show the quiver clearly.")
    assert generate.facing_note(job, "N") == "the quiver is always on the back. show the quiver clearly"
    p = builder.facing("N", [], "S", generate.facing_note(job, "N"))
    assert "quiver is always on the back. show the quiver clearly. Same camera angle" in p and builder.FRAMING in p
    assert "show the quiver" not in builder.facing("E", [], "S", generate.facing_note(job, "E"))
    with pytest.raises(ValueError):
        prompt_view.set_facing_note(job, "UP", "x")


def test_view_never_runs_the_ai_writer(job):
    job.update_inputs(prompt_writer="ai", description="a small archer")
    v = prompt_view.view(job)                       # would raise / hang if it called ComfyUI
    assert v["actions"]["walk"]["source"].startswith("preset (AI text")
    assert "a small archer" in v["anchor"]["preview"]


def test_prompts_api(tmp_path, job):
    job.log_provenance("02_facings/N.png", values={"prompt": "the prompt that was sent"})
    with TestClient(create_app(tmp_path, worker=False)) as c:
        v = c.get("/api/jobs/hero/j/prompts").json()
        assert v["facings"]["N"]["used"] == "the prompt that was sent"
        v = c.post("/api/jobs/hero/j/prompts", json={"kind": "action", "action": "idle", "sound": "soft breathing"}).json()
        assert v["actions"]["idle"]["source"] == "edited" and v["actions"]["idle"]["spec"]["sound"] == "soft breathing"
        assert c.post("/api/jobs/hero/j/prompts", json={"kind": "nope"}).status_code == 400
