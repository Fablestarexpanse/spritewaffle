"""Art styles. One entry = how prompts describe the look + which post-processing path the frames take.

post="pixel":  the pixelizer (grid, shared palette, hard alpha) — the original SpriteWaffle path.
post="smooth": chroma key + despill + one locked placement per clip + smooth resize with soft
               (anti-aliased) edges at `scale` x the profile size; full-colour export.
Add a style by adding an entry; the UI, CLI and MCP list whatever is here.
"""
from __future__ import annotations

from contextvars import ContextVar

STYLES = {
    "pixel": {"label": "Pixel art", "post": "pixel", "noun": "pixel-art", "look": "chunky pixel-art look",
              "prompt": None},   # projection-specific wording lives in builder.STYLE
    "painted": {"label": "Hand-painted", "post": "smooth", "scale": 4, "noun": "hand-painted",
                "look": "hand-painted look",
                "prompt": "Hand-painted 2D game art with soft painterly brushwork, visible brush texture, rich "
                          "shading and a clean readable silhouette."},
    "anime": {"label": "Anime cel", "post": "smooth", "scale": 4, "noun": "anime cel-shaded",
              "look": "anime cel-shaded look",
              "prompt": "Anime cel-shaded 2D game art with clean dark line art, flat cel shading with one shadow "
                        "tone and bright saturated colours."},
    "comic": {"label": "Comic ink", "post": "smooth", "scale": 4, "noun": "comic ink",
              "look": "comic ink look",
              "prompt": "Comic book ink 2D game art with bold black ink outlines, hatched shadows and flat colour "
                        "fills."},
}

_current: ContextVar[str] = ContextVar("spritewaffle_style", default="pixel")


def get(name: str | None = None) -> dict:
    name = name or _current.get()
    if name not in STYLES:
        raise ValueError(f"unknown style '{name}'; known: {', '.join(STYLES)}")
    return {"name": name, **STYLES[name]}


def use(name: str | None) -> None:
    """Make `name` the style for prompts built in this thread (each stage calls it for its job)."""
    _current.set(get(name or "pixel")["name"])


def of_job(job) -> str:
    return job.read_meta()["inputs"].get("style") or "pixel"
