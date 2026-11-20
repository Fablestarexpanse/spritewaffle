"""AI prompt writer with a fake model: parsing, guards, fallback, caching per character."""
import pytest

from spritewaffle.core import generate
from spritewaffle.core.job import Job
from spritewaffle.prompts import builder, writer


class FakeModel:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def run_text(self, slot, values):
        self.calls.append(values)
        return {"text": self.replies.pop(0)}


GOOD = ('# Motion\n```json\n{"motion": "swings the club down in place", "transition": "lifts the club a little", '
        '"sound": "whoosh and thud", "cyclic": true}\n```')


def test_action_spec_parses_markdown_wrapped_json_and_forces_cyclic():
    m = FakeModel([GOOD.replace("\\n", "\n")])
    spec = writer.action_spec("attack", client=m, cyclic=False)
    assert spec == {"motion": "swings the club down in place", "transition": "lifts the club a little",
                    "sound": "whoosh and thud.", "cyclic": False}
    assert m.calls[0]["ref_images"] == []                       # no image -> image node pruned


@pytest.mark.parametrize("bad", ['{"motion": "walks forward across the screen", "transition": "x y", "sound": "s", "cyclic": true}',
                                 '{"motion": "the camera zooms in", "transition": "x", "sound": "s", "cyclic": true}',
                                 "## no json here",
                                 '{"motion": "' + "word " * 40 + '", "transition": "x", "sound": "s", "cyclic": true}'])
def test_rule_breaking_or_broken_replies_are_rejected(bad):
    with pytest.raises(writer.WriterError):
        writer.action_spec("walk", client=FakeModel([bad, bad]))


def test_describe_plain_sentence_and_on_topic_check():
    m = FakeModel(["Assistant: A frost wolf with pale blue fur, icy fangs and a silver collar."])
    assert writer.describe("frost wolf", client=m).startswith("A frost wolf with pale blue fur")
    off = "A muscular man with a leather vest and a dagger in his belt pouch."
    with pytest.raises(writer.WriterError, match="off-topic"):
        writer.describe("frost wolf", client=FakeModel([off, off]))


def test_resolve_action_spec_template_ai_cache_and_fallback(tmp_path, monkeypatch):
    job = Job.create("gob", "g", base=tmp_path)
    assert generate.resolve_action_spec(job, "walk") is builder.ACTIONS["walk"]
    with pytest.raises(ValueError, match="AI prompt writer"):
        generate.resolve_action_spec(job, "cast spell")
    job.update_inputs(prompt_writer="ai")
    m = FakeModel([GOOD.replace("\\n", "\n")])
    spec = generate.resolve_action_spec(job, "cast spell", client=m)
    assert spec["writer"] == "qwen3vl_4b" and spec["cyclic"] is True
    assert generate.resolve_action_spec(job, "cast spell", client=FakeModel([])) == spec   # cached: no second call
    broken = FakeModel(["nope", "nope"])
    assert generate.resolve_action_spec(job, "walk", client=broken) is builder.ACTIONS["walk"]  # preset fallback
    with pytest.raises(RuntimeError, match="could not write"):
        generate.resolve_action_spec(job, "dance", client=FakeModel(["nope", "nope"]))
