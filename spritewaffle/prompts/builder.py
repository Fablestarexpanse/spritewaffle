"""Prompt builder for generation stages. Short, literal, layout rules baked in (rules 3, 4, 6)."""
from __future__ import annotations

from ..core.profile import GameProfile

CARDINALS = ("S", "E", "N", "W")
DIAGONALS = ("SE", "NE", "NW", "SW")

# what the viewer sees; E/W are screen right/left
VIEW = {
    "S": "front view, facing the viewer",
    "N": "back view, facing directly away from the viewer",
    "E": "side view (profile), facing screen right",
    "W": "side view (profile), facing screen left",
    # rule 4: diagonals use semantic text, not angles
    "NE": "mostly back, plus right side: three-quarter back view turned toward screen right",
    "NW": "mostly back, plus left side: three-quarter back view turned toward screen left",
    "SE": "mostly front, plus right side: three-quarter front view turned toward screen right",
    "SW": "mostly front, plus left side: three-quarter front view turned toward screen left",
}

# diagonal -> cardinals it is built from. "multi" = kickoff rule 4 (anchor + cardinals);
# "nearest" = only the nearest cardinal as <Picture 1>. Measured 2026-11-20 on H3 Image edit: extra
# reference pictures pull the pose to the reference (SE came out as pure E); nearest gives true 3/4.
DIAGONAL_REFS = {"NE": ("N", "E"), "NW": ("N", "W"), "SE": ("E",), "SW": ("W",)}
DIAGONAL_NEAREST = {"NE": "N", "NW": "N", "SE": "S", "SW": "S"}

FRAMING = ("The character is centered and occupies about 45 percent of the image height, with wide "
           "empty margins on all sides; nothing within the outer quarter of the frame. Background is "
           "one perfectly flat solid pure green #00FF00: uniform, no floor, no shadow, no gradient, "
           "no texture, no text.")

STYLE = {
    "side": "Chunky retro pixel-art style with large visible square pixels, bold dark outline, flat cel shading, limited palette.",
    "topdown_34": "Chunky retro pixel-art style for a top-down 3/4 game, large visible square pixels, bold dark outline, flat cel shading, limited palette.",
    "iso_2to1": "Chunky retro pixel-art style for a 2:1 isometric game, large visible square pixels, bold dark outline, flat cel shading, limited palette.",
}


def anchor(description: str, profile: GameProfile, facing: str = "S") -> str:
    return (f"Full-body video game character sprite: {description.strip().rstrip('.')}. "
            f"Standing in a relaxed idle pose, {VIEW[facing]}, arms at sides, feet slightly apart. "
            f"{STYLE[profile.projection]} {FRAMING}")


def facing(target: str, refs: list[str], first: str = "S") -> str:
    """Edit prompt for one facing. <Picture 1> shows facing `first` (the anchor when S);
    refs = facings shown in <Picture 2..n>."""
    parts = [f"<Picture 1> shows the character, {VIEW[first]}."]
    for i, f in enumerate(refs, start=2):
        parts.append(f"<Picture {i}> shows the same character, {VIEW[f]}.")
    parts.append(
        f"Draw this exact character again, {VIEW[target]}, in the same relaxed idle pose. "
        "Keep the identical outfit, colors, proportions, size, pixel-art style and outline as <Picture 1>. "
        "Same scale and same position in the frame as <Picture 1>. " + FRAMING)
    return " ".join(parts)
