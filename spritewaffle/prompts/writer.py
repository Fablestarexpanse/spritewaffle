"""Optional prompt writer: a small local vision-language model (Qwen3-VL 4B, run by ComfyUI) fills
the *creative* parts of prompts; the rules (green background, framing, facing text, in-place motion,
H3 structure) stay in builder.py around whatever it writes.

Everything the model returns is checked (JSON shape, length, banned phrases). On a failed check it
retries once with a new seed, then the caller falls back to the template text, so turning the
writer on can never produce a prompt that breaks a kickoff rule.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..comfy.client import ComfyClient, ComfyError

# phrases that would undo a rule: camera moves, leaving the spot, turning, background changes,
# projection words (rule 6: never "isometric/top-down" unless the frame really is)
BANNED = re.compile(
    r"\b(isometric|top[- ]down|bird'?s[- ]eye|camera|zoom|pan(s|ning)?|tracking shot|close[- ]?up|"
    r"walks? (forward|away|toward|towards|off|across|into)|runs? (forward|away|toward|towards|off|across|into)|"
    r"steps? (forward|backward|back|ahead|away)|stepping (forward|backward|ahead)|(forward|backward) step|moves? (forward|backward|left|right)|"
    r"across the (screen|frame|scene)|turns? (around|away|to face)|leaves? the|exits?|enters?|"
    r"background|scenery|landscape|forest|sky)\b", re.I)

# No literal braces in system prompts: with a JSON example like {"motion": ...} in the system
# prompt ComfyUI's text generation returned an empty string (measured 0/5 -> 6/6 valid without).
SYS_DESCRIBE = (
    "You describe video game sprites for an image generator. Write exactly one plain sentence of at "
    "most 45 words naming body type, outfit, colours, materials and carried items. No headings, no "
    "lists, no quotes. Do not mention the background, the pose, the camera, lighting or the art style. "
    "Keep colours natural for the subject unless the request names them.")

SYS_ACTION = (
    "You write motion text for a short looping 2D game sprite animation made by a video model. The "
    "character stays on the same spot, facing the same way; the camera never moves. Answer with one "
    "JSON object and nothing else. Keys: motion (what the body does, at most 30 words, literal, using "
    "the items the character holds), transition (the very first small step out of the idle pose, at "
    "most 20 words, not the extreme pose), sound (at most 12 words), cyclic (true for loops like idle, "
    "walk, run; false for one-shot actions that return to the idle pose). Walking and running happen in "
    "place: feet lift and land on the same spot. Never move forward or backward, never turn around, "
    "never mention the camera, the background or the screen.")


class WriterError(RuntimeError):
    pass


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise WriterError(f"no JSON in model output: {text[:120]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise WriterError(f"bad JSON from model: {e}") from e


def _clean(s, limit: int, field: str) -> str:
    if not isinstance(s, str) or not s.strip():
        raise WriterError(f"{field}: empty")
    s = re.sub(r"\s+", " ", s.replace("*", "").replace("#", "")).strip().rstrip(".")
    if len(s.split()) > limit:
        raise WriterError(f"{field}: {len(s.split())} words > {limit}")
    hit = BANNED.search(s)
    if hit:
        raise WriterError(f"{field}: banned phrase {hit.group(0)!r}")
    return s


def sprite_view(image: Path, out: Path | None = None, size: int = 512) -> Path:
    """The sprite cut out of its green canvas and enlarged (nearest) on neutral grey: a 2048² mostly
    green image leaves a 4B model guessing (measured: it called the goblin's club an axe/staff)."""
    import numpy as np
    from PIL import Image
    from ..pixel import chroma
    image = Path(image)
    out = out or image.parent / f".{image.stem}.writer.png"
    if out.exists() and out.stat().st_mtime >= image.stat().st_mtime:
        return out
    sprite = Image.fromarray(chroma.crop_sprite(np.array(Image.open(image).convert("RGB"))), "RGBA")
    k = size / max(sprite.size)
    sprite = sprite.resize((max(1, int(sprite.width * k)), max(1, int(sprite.height * k))), Image.NEAREST)
    canvas = Image.new("RGB", (size, size), (128, 128, 128))
    canvas.paste(sprite, ((size - sprite.width) // 2, (size - sprite.height) // 2), sprite)
    canvas.save(out)
    return out


def _ask(client: ComfyClient, system: str, prompt: str, image: Path | None, seed: int) -> dict:
    # max_tokens counts prompt + image tokens too. An empty image list prunes the template's image
    # node: leaving it in fed ComfyUI's example.png to the model (measured: "yellow outfit, pink club").
    vals = {"system": system, "prompt": prompt, "seed": seed, "max_tokens": 1200,
            "ref_images": [sprite_view(image)] if image else []}
    return _json(client.run_text("prompt_writer", vals)["text"])


def _with_retry(fn, seed: int):
    last = None
    for s in (seed, seed + 7919):
        try:
            return fn(s)
        except (WriterError, ComfyError) as e:
            last = e
    raise WriterError(f"prompt writer failed twice: {last}")


def _sentence(text: str) -> str:
    """First real sentence of a plain-text reply (headings, list marks, labels and quotes removed).
    Plain text instead of JSON: the 4B model wrote unquoted keys in 4 of 6 JSON replies."""
    for line in text.splitlines():
        line = line.strip().lstrip("#*->0123456789. ").strip().strip('"')
        for label in ("assistant:", "description:", "answer:"):
            if line.lower().startswith(label):
                line = line[len(label):].strip().strip('"')
        if len(line.split()) >= 6:
            return line
    raise WriterError(f"no sentence in model output: {text[:120]!r}")


def describe(idea: str, asset_type: str = "character", image: Path | None = None,
             client: ComfyClient | None = None, seed: int = 0) -> str:
    """Short idea (or an image of the asset) -> one concrete visual description."""
    client = client or ComfyClient()
    task = (f"Describe this {asset_type}" + (f" ({idea})" if idea else "") + "." if image
            else f"Describe this {asset_type}: {idea}.")
    keywords = [w for w in re.findall(r"[a-z]{4,}", (idea or "").lower()) if w not in {"with", "small", "large", "wearing"}]

    def one(s):
        vals = {"system": SYS_DESCRIBE, "prompt": task, "seed": s, "max_tokens": 1200,
                "ref_images": [sprite_view(image)] if image else []}
        d = _clean(_sentence(client.run_text("prompt_writer", vals)["text"]), 45, "description")
        missing = [k for k in keywords if k not in d.lower()]
        if missing:                                     # measured: "frost wolf" -> a frost-themed humanoid
            raise WriterError(f"off-topic description (lost {missing}): {d[:80]!r}")
        return d
    return _with_retry(one, seed)


def _short(text: str, max_words: int = 26) -> str:
    """Keep descriptions short in the action request: with a 36-word description ComfyUI's text
    generation returned an empty string at every seed and budget (27 words: fine). Keep the subject
    clause and any clause naming held items (a plain cut dropped the club -> the model wrote "axe")."""
    if len(text.split()) <= max_words:
        return text
    clauses = [c.strip() for c in text.split(",")]
    keep = [clauses[0]] + [c for c in clauses[1:] if any(w in c.lower() for w in ("carry", "hold", "wield", "armed"))]
    out = ", ".join(keep)
    for drop in (" and a ", " and an ", " and "):           # trim trailing extras inside the items clause
        if len(out.split()) > max_words and drop in out:
            out = out[:out.rfind(drop)]
    return " ".join(out.split()[:max_words])


def action_spec(action: str, image: Path | None = None, description: str = "",
                client: ComfyClient | None = None, seed: int = 0, cyclic: bool | None = None) -> dict:
    """Motion/transition/sound text for any action name, written for this character.
    cyclic: force loop / one-shot (known actions); None lets the model decide (new actions)."""
    client = client or ComfyClient()
    who = f" The character: {_short(description)}." if description else ""
    task = f"Action: {action}.{who}"

    def one(s):
        d = _ask(client, SYS_ACTION, task, image, s)
        if cyclic is not None:
            d["cyclic"] = cyclic
        if not isinstance(d.get("cyclic"), bool):
            raise WriterError("cyclic: not true/false")
        return {"motion": _clean(d.get("motion"), 30, "motion"),
                "transition": _clean(d.get("transition"), 20, "transition"),
                "sound": _clean(d.get("sound"), 12, "sound") + ".",
                "cyclic": d["cyclic"]}
    return _with_retry(one, seed)
