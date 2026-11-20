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


# Per-asset-type presets: subject wording, idle pose, and which actions make sense.
ASSET_TYPES = {
    "character": {"subject": "Full-body video game character sprite",
                  "pose": "Standing in a relaxed idle pose, {view}, arms at sides, feet slightly apart.",
                  "actions": ["idle", "walk", "run", "attack", "jump"]},
    "creature": {"subject": "Full-body video game creature sprite",
                 "pose": "Standing in a neutral idle stance, {view}, all limbs visible.",
                 "actions": ["idle", "walk", "run", "attack"]},
    "prop": {"subject": "Single video game prop sprite",
             "pose": "Resting upright on its base, {view}, the whole object visible.",
             "actions": ["idle"]},
}


def asset(asset_type: str) -> dict:
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"unknown asset type '{asset_type}'; known: {sorted(ASSET_TYPES)}")
    return ASSET_TYPES[asset_type]


def anchor(description: str, profile: GameProfile, facing: str = "S", asset_type: str = "character") -> str:
    a = asset(asset_type)
    return (f"{a['subject']}: {description.strip().rstrip('.')}. {a['pose'].format(view=VIEW[facing])} "
            f"{STYLE[profile.projection]} {FRAMING}")


def anchor_from_hero(description: str, profile: GameProfile, asset_type: str = "character") -> str:
    """'Hero asset first, then reference it': a new anchor drawn in the approved hero's style."""
    a = asset(asset_type)
    return ("<Picture 1> shows the approved hero sprite of this game. "
            f"Draw a new, different {a['subject'].lower()}: {description.strip().rstrip('.')}. "
            "Use exactly the same art style as <Picture 1>: same pixel size, outline weight, shading and "
            "palette feel, and the same scale on the canvas. Do not copy the hero's design. "
            f"{a['pose'].format(view=VIEW['S'])} {FRAMING}")


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


# --- actions (rules 5, 6) ---------------------------------------------------------------------
# motion: short and literal; transition: a small step away from idle, never the extreme pose.
ACTIONS = {
    "idle": {"cyclic": True, "transition": None,
             "motion": "breathes gently while standing still, with a small up-and-down body bob",
             "sound": "Near silence with soft breathing."},
    "walk": {"cyclic": True,
             "transition": "just beginning to march in place: one foot lifted slightly off the ground, arms barely moving",
             "motion": "marches in place: left foot up, right foot up, steady rhythm, arms swinging a little",
             "sound": "Soft footstep taps in a steady rhythm."},
    "run": {"cyclic": True,
            "transition": "just beginning to run in place: one knee lifted slightly, leaning forward a little",
            "motion": "runs in place with quick high-knee strides and pumping arms",
            "sound": "Quick light footstep taps."},
    "attack": {"cyclic": False,
               "transition": "just beginning an attack: weapon or fists raised slightly from the idle pose",
               "motion": "makes one forward strike and then returns to the starting pose",
               "sound": "A short swoosh and a soft impact."},
    "jump": {"cyclic": False,
             "transition": "just beginning to jump: knees bent slightly, arms drawn back a little",
             "motion": "crouches, jumps straight up in place and lands back on the same spot",
             "sound": "A soft push-off and a light landing thud."},
}

HOLD = {"S": "keeps facing the viewer", "N": "keeps its back to the viewer",
        "E": "keeps facing screen right in side view", "W": "keeps facing screen left in side view",
        "SE": "keeps the three-quarter front view toward screen right",
        "SW": "keeps the three-quarter front view toward screen left",
        "NE": "keeps the three-quarter back view toward screen right",
        "NW": "keeps the three-quarter back view toward screen left"}


def action_spec(action: str) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"no preset for action '{action}'; known: {sorted(ACTIONS)}")
    return ACTIONS[action]


def transition(action: str, facing_: str) -> str:
    """Image-edit prompt: the transition pose that becomes the video's first frame (rule 5)."""
    return (f"<Picture 1> shows the character, {VIEW[facing_]}, in its idle pose. "
            f"Draw this exact character in the same facing, {action_spec(action)['transition']}. "
            "This is only a small step away from the idle pose, not the extreme pose. "
            "Keep the identical outfit, colors, proportions, size, pixel-art style and outline. "
            "Same scale and same position in the frame as <Picture 1>. " + FRAMING)


def action_video(action: str, facing_: str, seconds: float, last_frame: bool) -> str:
    """H3 video prompt (FL2VA when last_frame, else I2VA), structured per the H3 prompt guide;
    body short and literal (rule 6)."""
    spec = action_spec(action)
    if last_frame:
        head = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with "
                f"the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the {seconds:.2f}-second "
                "mark of the target video.")
        end = " At the end of the shot it settles into the pose and position established by Picture 2."
    else:
        head = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
        end = ""
    body = (f"[Shot 1] 2D pixel-art game sprite with a locked camera: no zoom, no pan. The character begins in the pose "
            f"and position established by Picture 1, pinned to the center of the frame, and {spec['motion']}. "
            f"It {HOLD[facing_]}; it must not turn or move across the screen. The flat #00FF00 background stays "
            f"unchanged for the whole shot, and the chunky pixel-art look stays the same.{end}")
    return (f"{head}\n\nintegrated_multimodal_description: {body}\n\n"
            f"overall_soundscape: {spec['sound']}\n\nnon_diegetic_music: None.")


def motion_transfer() -> str:
    """TARA prompt (author's motion_transfer structure): identity from <Picture 1>, motion from <Video 1>."""
    return ("motion_transfer:\nsubject_definitions:\n<Subject 1> is the pixel-art game character in <Picture 1>; "
            "preserve its identity, colors, outfit, proportions and chunky pixel-art style.\nsummary:\n"
            "[video generation + reference] Transfer the performance of <Video 1> to <Subject 1>, preserving the "
            "action order, timing and the locked camera of the guide.\nretention_analysis:\n<Subject 1>: preserve "
            "the reference identity and pixel-art look throughout the clip. Keep the guide's flat #00FF00 "
            "background and framing. The guide figure is a plain grey mannequin; never copy its grey look.\n"
            "detailed_description:\n[Shot 1] <Subject 1> follows the guide's motion, poses and body movement in "
            "order and at matching times, pinned to the center of the frame at the same size as the guide figure. "
            "Do not copy <Picture 1>'s still pose as the motion.\noverall_soundscape:\nSoft footstep taps.\n"
            "non_diegetic_music:\nNone.")


def bridge_video(seconds: float) -> str:
    """FL2VA prompt for a short clip that moves from Picture 1's pose to Picture 2's pose."""
    return ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the "
            f"0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the {seconds:.2f}-second mark "
            "of the target video.\n\nintegrated_multimodal_description: [Shot 1] 2D pixel-art game sprite with a "
            "locked camera: no zoom, no pan. The character begins in the pose and position established by Picture 1, "
            "pinned to the center of the frame, and moves smoothly and evenly into the pose established by Picture 2. "
            "It keeps the same facing and must not move across the screen. The flat #00FF00 background stays "
            "unchanged for the whole shot.\n\noverall_soundscape: Near silence.\n\nnon_diegetic_music: None.")


def bridge() -> str:
    return ("<Picture 1> and <Picture 2> show the same character in two poses with the same facing. "
            "Draw the single in-between pose exactly halfway between them. Keep the identical outfit, colors, "
            "proportions, size, pixel-art style and outline, same scale and same position in the frame. " + FRAMING)
