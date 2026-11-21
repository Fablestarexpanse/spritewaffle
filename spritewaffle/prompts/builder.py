"""Prompt builder for generation stages. Short, literal, layout rules baked in (rules 3, 4, 6)."""
from __future__ import annotations

from ..core.profile import GameProfile
from . import styles

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
    "topdown_34": "Chunky retro pixel-art style for a top-down RPG, large visible square pixels, bold dark outline, flat cel shading, limited palette.",
    "iso_2to1": "Chunky retro pixel-art style for a tactics game seen from above, large visible square pixels, bold dark outline, flat cel shading, limited palette.",
}


# Per-asset-type presets: subject wording, idle pose, and which actions make sense.
ASSET_TYPES = {
    "character": {"subject": "Full-body video game character sprite",
                  "pose": "Standing in a relaxed idle pose, {view}, arms at sides, feet slightly apart.",
                  "actions": ["idle", "walk", "run", "attack", "jump"]},
    "creature": {"subject": "Full-body video game creature sprite",
                 "pose": "Standing in a neutral idle stance, {view}, all limbs visible.",
                 "actions": ["idle", "walk", "run", "attack"]},
    "animal": {"subject": "Full-body video game animal sprite, a four-legged animal",
               "pose": "Standing on all four legs in a relaxed stance, {view}, all four legs and the tail visible.",
               "actions": ["idle", "walk", "run", "pounce", "sit", "sleep"]},
    "prop": {"subject": "Single video game prop sprite",
             "pose": "Resting upright on its base, {view}, the whole object visible.",
             "actions": ["idle"]},
    "effect": {"subject": "Game visual effect sprite", "pose": "{view}", "actions": []},   # see prompts/effects.py
    # equipment for paper-doll games: drawn on its own, front (anchor) and back (core/item.py), then
    # fitted onto any base character (Ronan 2026-11-21)
    "item": {"subject": "Single video game equipment item sprite, shown on its own and not worn by anyone",
             "pose": "Upright, {view}, shaped as if worn by an invisible body, the whole item visible.",
             "actions": []},
}


def asset(asset_type: str) -> dict:
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"unknown asset type '{asset_type}'; known: {sorted(ASSET_TYPES)}")
    return ASSET_TYPES[asset_type]


# Where the camera is. Measured 2026-11-20: with only the STYLE words ("for a top-down 3/4 game")
# H3 Image kept an eye-level camera and turned the character a quarter instead (a front anchor came
# out as a three-quarter view). Saying where the camera is, and that the body still faces the
# viewer, is what the projection needs; facings and clips then keep "the same camera angle as
# Picture 1".
CAMERA = {
    "side": "",
    "topdown_34": ("The camera is high above, tilted down about 45 degrees like a classic top-down RPG: we look "
                   "down onto the top of the head and the shoulders, the body is foreshortened and the feet "
                   "tuck under it. Only the camera is raised: the chest and face point straight down the screen "
                   "toward us, both shoulders equally visible, not turned left or right."),
    "iso_2to1": ("The camera is above, tilted down about 30 degrees like a tactics game: we see the top of the "
                 "head and shoulders and the body is slightly foreshortened. Only the camera is raised: the chest "
                 "and face point straight down the screen toward us, both shoulders equally visible, not turned "
                 "left or right."),
}


def style_text(profile: GameProfile) -> str:
    """The active style's look sentence (pixel art keeps its projection-specific wording) plus the
    camera sentence for top-down / isometric profiles."""
    st = styles.get()
    look = STYLE[profile.projection] if st["post"] == "pixel" else st["prompt"]
    cam = CAMERA.get(profile.projection, "")
    return f"{look} {cam}".strip()


def anchor(description: str, profile: GameProfile, facing: str = "S", asset_type: str = "character") -> str:
    a = asset(asset_type)
    return (f"{a['subject']}: {description.strip().rstrip('.')}. {a['pose'].format(view=VIEW[facing])} "
            f"{style_text(profile)} {FRAMING}")


def anchor_from_hero(description: str, profile: GameProfile, asset_type: str = "character") -> str:
    """'Hero asset first, then reference it': a new anchor drawn in the approved hero's style."""
    a = asset(asset_type)
    return ("<Picture 1> shows the approved hero sprite of this game. "
            f"Draw a new, different {a['subject'].lower()}: {description.strip().rstrip('.')}. "
            "Use exactly the same art style as <Picture 1>: same "
            + ("pixel size, " if styles.get()["post"] == "pixel" else "") + "outline weight, shading and "
            "palette feel, and the same scale on the canvas. Do not copy the hero's design. "
            f"{a['pose'].format(view=VIEW['S'])} {FRAMING}")


# Facings under a raised camera (top-down, isometric). Measured 2026-11-20 (knight, seed 21):
# side-view words alone -> E/W dropped to an eye-level profile, diagonals copied their reference;
# screen-direction words ("toward the lower-right corner") -> nothing rotated at all. This keeps
# the side-view words (they do rotate) and adds the camera.
VIEW_RAISED = {f: (f"{v}, still seen from the same high camera above, looking down on the top of the head"
                   if f != "S" else v) for f, v in VIEW.items()}


# Four-legged animals: say where the BODY points, nose to tail. Measured 2026-11-20 (cat): with the
# character words every facing came out as a copy of the three-quarter anchor.
VIEW_ANIMAL = {
    "S": "front view: head and chest facing the viewer, the body going straight back behind them",
    "N": "back view: seen from behind, the tail and hindquarters toward the viewer, the head facing away",
    "E": "exact side view: the whole body in profile from nose to tail, the head pointing to screen right, "
         "all four legs visible in a row",
    "W": "exact side view: the whole body in profile from nose to tail, the head pointing to screen left, "
         "all four legs visible in a row",
    "SE": "three-quarter front view: the head and chest toward the viewer and to the right, the body angled back to the left",
    "SW": "three-quarter front view: the head and chest toward the viewer and to the left, the body angled back to the right",
    "NE": "three-quarter back view: the hindquarters toward the viewer, the head pointing away and to the right",
    "NW": "three-quarter back view: the hindquarters toward the viewer, the head pointing away and to the left",
}


TURNAROUND_VIEWS = ("S", "E", "N", "SE", "NE")      # left to right on the sheet; W/SW/NW are mirrored


def turnaround(description: str, profile: GameProfile, asset_type: str = "animal") -> str:
    """Text-to-image prompt: one model sheet with five views of the same subject in a row.
    Measured 2026-11-20: H3 Image edit would not turn a four-legged cat away from its anchor (every
    facing a copy, whatever the wording); one sheet drawn in one go turns it and keeps the design."""
    a = asset(asset_type)
    stance = "standing on all four legs, " if asset_type == "animal" else ""
    return (f"Turnaround model sheet for a video game: the same {description.strip().rstrip('.')}, shown five times "
            f"side by side in one row, same size, {stance}evenly spaced with clear gaps between them. Left to right: "
            "1) front view, head and chest facing the viewer; 2) exact side view, the whole body in profile, head "
            "pointing to the right; 3) back view, seen from behind; 4) three-quarter front view turned toward the "
            "right; 5) three-quarter back view turned toward the right. "
            f"{style_text(profile)} Background is one perfectly flat solid pure green #00FF00: uniform, no floor, "
            f"no shadow, no text, no labels, no numbers. ({a['subject']}.)")


def view_words(raised: bool = False, animal: bool = False) -> dict:
    """Facing wording for this camera and body plan."""
    if animal:
        return {f: (f"{v}, still seen from the same high camera above" if raised and f != "S" else v)
                for f, v in VIEW_ANIMAL.items()}
    return VIEW_RAISED if raised else VIEW


def facing(target: str, refs: list[str], first: str = "S", note: str = "", raised: bool = False,
           animal: bool = False) -> str:
    """Edit prompt for one facing. <Picture 1> shows facing `first` (the anchor when S);
    refs = facings shown in <Picture 2..n>. note: the human's extra detail for this view (e.g.
    "the quiver is visible on the back"); the framing rules always follow it. raised: top-down /
    isometric camera, so directions are said as screen directions."""
    V = view_words(raised, animal)
    parts = [f"<Picture 1> shows the character, {V[first]}."]
    for i, f in enumerate(refs, start=2):
        parts.append(f"<Picture {i}> shows the same character, {V[f]}.")
    parts.append(
        f"Draw this exact character again, {V[target]}, in the same relaxed idle pose. "
        f"Keep the identical outfit, colors, proportions, size, {styles.get()['noun']} style and outline as <Picture 1>. "
        + (f"{note.strip().rstrip('.')}. " if note.strip() else "")
        + "Same camera angle, scale and position in the frame as <Picture 1>. " + FRAMING)
    return " ".join(parts)


# --- variants: an approved character with one change ---------------------------------------
def edit_anchor(instruction: str) -> str:
    """Image-edit prompt: the anchor (Picture 1) with only the requested change."""
    return (f"<Picture 1> shows a character, {VIEW['S']}. Draw this exact character again in the same relaxed idle "
            f"pose and view, changed only like this: {instruction.strip().rstrip('.')}. Everything else stays "
            f"identical: face, body, proportions, size, colors, {styles.get()['noun']} style and outline. "
            "Same camera angle, scale and position in the frame as <Picture 1>. " + FRAMING)


def edit_facing(target: str, instruction: str, raised: bool = False) -> str:
    """Image-edit prompt: one base facing (Picture 1) with the change, said in words only.
    Measured 2026-11-20: giving the edited front view as Picture 2 made every facing come out as
    that front view; one picture keeps the base pose."""
    V = VIEW_RAISED if raised else VIEW
    return (f"<Picture 1> shows a character, {V[target]}. Draw this exact character again in exactly the same "
            f"view, pose and position, changed only like this: {instruction.strip().rstrip('.')}, as it looks "
            f"from this side. "
            + ("Seen from behind, anything on the front of it (a gem, an emblem, a buckle on the chest) is hidden. "
               if target in ("N", "NE", "NW") else "")
            + f"Everything else stays identical: face, body, outfit, proportions, size, colors, "
            f"{styles.get()['noun']} style and outline. "
            "Same camera angle, scale and position in the frame as <Picture 1>. " + FRAMING)


BACK = ("N", "NE", "NW")


def item_back(description: str = "") -> str:
    """Image-edit prompt: an item's front (Picture 1) -> the same item seen from behind. Measured
    2026-11-21 (red cape): "draw the same item seen from behind" gave a copy of the front (open front,
    clasp; turned_from 5.2); "turn it around 180 degrees" + "the back is one closed outer surface"
    gave closed backs at 18-20 (one seed in two still showed the clasp: re-roll)."""
    what = f": {description.strip().rstrip('.')}" if description.strip() else ""
    return (f"<Picture 1> shows a video game equipment item from the front{what}. Turn the item around 180 degrees "
            "and draw its back side, the side that faces away from the viewer in <Picture 1>. From behind, the "
            "opening, the inner lining and anything fastened at the front (clasp, buckle, gem, emblem, lacing) "
            "cannot be seen: the back is one closed outer surface with only its outline, seams and trim. Same shape, "
            f"size, colours, materials, {styles.get()['noun']} style and outline. Same scale and position in the frame "
            "as <Picture 1>. " + FRAMING)


def item_reference(target: str, character: str, item: str, how: str, back_item: str = "",
                   raised: bool = False, back_ref: bool = False) -> str:
    """H3 Image edit caption for base facing (<Picture 1>) + item picture (<Picture 2>), written in the
    enhancer's own Subject format (facing_multiref node 39). <Subject 3> pins the canvas to Picture 1:
    without it the item picture was read as the canvas (huge armor, tiny knight). how: "wearing this",
    "holding this in the right hand" ('this' becomes <Subject 2>). back_item: the item without its
    front details, for back views. back_ref: <Picture 2> is the item's own back view (item jobs)."""
    V = VIEW_RAISED if raised else VIEW
    def bare(t):                                   # "The" is added here; drop the writer's own article
        t = t.strip().rstrip(".")
        for art in ("a ", "an ", "the "):
            if t.lower().startswith(art):
                return t[len(art):]
        return t
    c, i = bare(character), bare(item)
    use = how.strip().rstrip(".") or "wearing this"
    use = use.replace("this", "<Subject 2>", 1) if "this" in use else f"{use} <Subject 2>"
    back = target in BACK
    if back and back_ref:
        seen = ("<Picture 2> shows the back of <Subject 2>; seen from behind it looks exactly like that back, "
                "and its front details are hidden. ")
    elif back:
        seen = (f"Seen from behind, only the back of it shows: {(bare(back_item) or 'its plain back')}; "
                "the gem, emblem and other front details are hidden. ")
    else:
        seen = "It is shown as it looks from this side. "
    noun = styles.get()["noun"]
    return (f"The {c} in <Picture 1> is <Subject 1>. The {i} in <Picture 2> is <Subject 2>. "
            "The flat pure green background, framing and camera of <Picture 1> are <Subject 3>. "
            f"The target image shows <Subject 1> {use}, {V[target]}, in exactly the same pose, within <Subject 3>. "
            "<Subject 1> is partially preserved; the head, face, body, limbs, pose, view, size, position in the frame "
            f"and {noun} style with its outline remain, while the part of the outfit where <Subject 2> sits is now "
            "covered by it. "
            f"<Subject 2> supplies only its design, transferred onto <Subject 1> at the character's scale: its shape, "
            "colours, materials and details are matched; its backdrop and its size in <Picture 2> are not used. "
            "<Subject 3> is fully preserved. "
            + seen + "The face stays fully visible; <Subject 2> is shaded with the same light as the character, in the "
            f"same {noun} style and outline. " + FRAMING)


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

# Four-legged animals. Without gait words a cat walks like a person (seen in generated assets).
ANIMAL_ACTIONS = {
    "idle": {"cyclic": True, "transition": None,
             "motion": "stands on all four legs breathing gently, tail swaying slowly, ears twitching",
             "sound": "Soft breathing."},
    "walk": {"cyclic": True,
             "transition": "just beginning to walk in place on all four legs: one front paw lifted slightly",
             "motion": "walks in place on all four legs: the legs move in diagonal pairs, front left with back right, "
                       "then front right with back left, body level, tail swaying",
             "sound": "Soft padded paw steps."},
    "run": {"cyclic": True,
            "transition": "just beginning to gallop in place: front paws lifted slightly, body leaning forward",
            "motion": "gallops in place on all four legs: front legs reach out together, back legs push together, "
                      "the back flexing, ears back",
            "sound": "Quick padded paw steps."},
    "pounce": {"cyclic": False, "transition": "crouching slightly on all four legs, ready to spring",
               "motion": "crouches low, springs forward a short way with front paws raised, and lands back in place",
               "sound": "A quick rustle and a soft landing."},
    "sit": {"cyclic": False, "transition": "just beginning to sit: hindquarters lowering slightly",
            "motion": "lowers its hindquarters and sits down, front legs straight, tail curling around its paws",
            "sound": "A soft rustle."},
    "sleep": {"cyclic": True, "transition": "lying curled up on the ground with eyes closed",
              "motion": "lies curled up asleep, breathing slowly, the body gently rising and falling",
              "sound": "Slow, soft breathing."},
    "jump": {"cyclic": False, "transition": "crouching slightly on all four legs, ready to leap",
             "motion": "crouches and leaps straight up on all fours, then lands back on the same spot",
             "sound": "A soft push-off and a light landing."},
}


def actions_for(asset_type: str | None) -> dict:
    """The action presets that fit this asset type."""
    return ANIMAL_ACTIONS if asset_type == "animal" else ACTIONS


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


def transition(action: str, facing_: str, spec: dict | None = None) -> str:
    """Image-edit prompt: the transition pose that becomes the video's first frame (rule 5)."""
    return (f"<Picture 1> shows the character, {VIEW[facing_]}, in its idle pose. "
            f"Draw this exact character in the same facing, {(spec or action_spec(action))['transition']}. "
            "This is only a small step away from the idle pose, not the extreme pose. "
            f"Keep the identical outfit, colors, proportions, size, {styles.get()['noun']} style and outline. "
            "Same camera angle, scale and position in the frame as <Picture 1>. " + FRAMING)


def action_video(action: str, facing_: str, seconds: float, last_frame: bool, spec: dict | None = None) -> str:
    """H3 video prompt (FL2VA when last_frame, else I2VA), structured per the H3 prompt guide;
    body short and literal (rule 6)."""
    spec = spec or action_spec(action)
    if last_frame:
        head = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with "
                f"the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the {seconds:.2f}-second "
                "mark of the target video.")
        end = " At the end of the shot it settles into the pose and position established by Picture 2."
    else:
        head = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
        end = ""
    body = (f"[Shot 1] 2D {styles.get()['noun']} game sprite with a locked camera: no zoom, no pan, the same camera height and angle as Picture 1. The character begins in the pose "
            f"and position established by Picture 1, pinned to the center of the frame, and {spec['motion']}. "
            f"It {HOLD[facing_]}; it must not turn or move across the screen. The flat #00FF00 background stays "
            f"unchanged for the whole shot, and the {styles.get()['look']} stays the same.{end}")
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
            "of the target video.\n\nintegrated_multimodal_description: [Shot 1] 2D " + styles.get()["noun"] + " game sprite with a "
            "locked camera: no zoom, no pan. The character begins in the pose and position established by Picture 1, "
            "pinned to the center of the frame, and moves smoothly and evenly into the pose established by Picture 2. "
            "It keeps the same facing and must not move across the screen. The flat #00FF00 background stays "
            "unchanged for the whole shot.\n\noverall_soundscape: Near silence.\n\nnon_diegetic_music: None.")


def bridge() -> str:
    return ("<Picture 1> and <Picture 2> show the same character in two poses with the same facing. "
            "Draw the single in-between pose exactly halfway between them. Keep the identical outfit, colors, "
            f"proportions, size, {styles.get()['noun']} style and outline, same scale and same position in the frame. " + FRAMING)
