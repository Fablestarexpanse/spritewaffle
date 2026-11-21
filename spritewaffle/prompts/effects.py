"""Prompts for visual effects (spells, fire, explosions, impacts): drawn on pure black, so the
engine can blend them additively (black disappears) or the tool can turn brightness into alpha.
Same rules as characters otherwise: locked camera, centred, nothing leaves the frame, short and
literal motion text.
"""
from __future__ import annotations

from . import styles

BLACK = ("Background is one perfectly flat solid pure black #000000: no stars, no gradient, no ground, no smoke "
         "haze across the frame, no text, no characters.")
FRAME_SMALL = ("It is small, about 10 percent of the image height, exactly in the center of the frame, with "
               "empty black all around it.")
FRAME = ("The effect is centered in the frame and occupies about 45 percent of the image height, with wide empty "
         "black margins on all sides; nothing within the outer quarter of the frame.")

# Presets: what the first frame shows, what the clip does, loop or one-shot.
PRESETS = {
    "fireball": {"still": "a round fireball of swirling orange and yellow flames with a bright white-hot core",
                 "motion": "the fireball churns and flickers in place, flames licking outward and small embers "
                           "drifting off, always the same size", "loop": True, "sound": "Low roaring flames."},
    "explosion": {"still": "a tiny bright white-yellow spark, just ignited",
                  "motion": "the spark bursts into a big round explosion of orange fire and dark smoke that expands "
                            "outward, then fades and thins away until only the empty black background is left",
                  "loop": False, "sound": "A deep boom, then crackling.", "start_small": True},
    "magic circle": {"still": "a glowing magic rune circle of thin cyan lines and symbols, seen flat from the front",
                     "motion": "the rune circle slowly rotates in place and pulses brighter and dimmer, sparkles "
                               "rising from its lines", "loop": True, "sound": "A soft magical hum."},
    "healing": {"still": "a soft burst of green and white healing sparkles and small glowing plus signs",
                "motion": "the sparkles rise gently upward and twinkle, new ones appearing at the bottom, the "
                          "cluster staying in the same place", "loop": True, "sound": "Gentle chimes."},
    "slash": {"still": "a thin bright white crescent slash arc with a faint blue glow",
              "motion": "the slash arc sweeps across in a fast curve, flares bright, then fades away to nothing",
              "loop": False, "sound": "A sharp whoosh."},
    "lightning": {"still": "a thin jagged forked lightning strike of bright blue-white light running from the top "
                           "of the effect down to the bottom, with small branching forks, not an icon or symbol",
                  "motion": "the lightning bolt flickers and forks, flashing bright several times, staying in "
                            "place", "loop": True, "sound": "Crackling electricity."},
}


def look() -> str:
    st = styles.get()
    return ("Chunky retro pixel-art game effect, large visible square pixels, limited palette, bright glowing "
            "saturated colors." if st["post"] == "pixel" else f"{st['noun'].capitalize()} game effect, bright glowing "
            "saturated colors.")


GREEN = "Background is one perfectly flat solid pure green #00FF00: uniform, no floor, no shadow, no gradient, no text."


def still_green(description: str, start_small: bool = False) -> str:
    """For objects and dark effects (smoke, dust, a thrown shield): no 'glowing' wording, which pulls
    the background to black."""
    st = styles.get()
    look_ = ("Chunky retro pixel-art game sprite, large visible square pixels, bold dark outline, limited palette."
             if st["post"] == "pixel" else f"{st['noun'].capitalize()} game sprite.")
    return (f"Single game sprite of {description.strip().rstrip('.')}. {look_} "
            f"{FRAME_SMALL if start_small else FRAME} {GREEN}")


def still(description: str, start_small: bool = False) -> str:
    """H3 Image text-to-image: the effect's first frame. start_small: a one-shot that grows from a
    point (explosion) starts tiny; otherwise the effect fills ~45% of the frame."""
    return (f"Game visual effect sprite: {description.strip().rstrip('.')}. {look()} "
            f"{FRAME_SMALL if start_small else FRAME} {BLACK}")


def video(motion: str, sound: str = "", seconds: float = 2.0) -> str:
    """H3 image-to-video: the effect plays out from the first frame, camera locked, background black."""
    head = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    body = (f"[Shot 1] 2D {styles.get()['noun']} game visual effect with a locked camera: no zoom, no pan. It begins "
            f"exactly as in Picture 1, centered in the frame, and {motion.strip().rstrip('.')}. Everything stays inside "
            "the frame and centered; no characters, no hands, no ground. The flat pure black #000000 background stays "
            "unchanged for the whole shot.")
    return (f"{head}\n\nintegrated_multimodal_description: {body}\n\n"
            f"overall_soundscape: {sound or 'Quiet magical whoosh.'}\n\nnon_diegetic_music: None.")
