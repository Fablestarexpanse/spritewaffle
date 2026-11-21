# Beyond walk and idle: spells, effects, creatures, thrown objects (research, 2026-11-20)

Ronan: "make all kinds of animations, not just our stock ones: magic spells, this guy throwing his
shield, a cat doing something, a special-effects section." What exists, what the web and the local
ComfyUI offer, and what to build, in order.

## What the tool can already do

- **Any custom action, today**: Prompts… → Actions → *Add* ("cast spell", "throw shield",
  "pounce"), write motion + transition, render. With the AI writer on, it writes them.
- **Creatures**: an asset type exists, but the actions and wording are biped (walk = "marches in
  place"). A cat will tend to walk like a person (seen in generated assets elsewhere: a grey cat on
  two legs with a human gait).
- **Effects drawn into the clip** (a glowing hand while casting) work, but they come out on the
  green background with the character: keyed together, spill on the glow, no separate layer.

## Findings

| Topic | What exists | Source |
|---|---|---|
| Effects on black | The common route for AI VFX: render the effect on pure black, pack frames into a flipbook, play it with an **additive** material — black disappears, no alpha needed. Brightness can become alpha when real transparency is wanted. Keep the background truly black. | [Atlas Cloud](https://www.atlascloud.ai/blog/tips/video-to-sprite-sheet), [vfxdoc](https://vfxdoc.readthedocs.io/en/latest/textures/overview/), [VFX Apprentice](https://www.vfxapprentice.com/blog/what-are-flipbooks-in-games), [Kenney](https://www.kenney.nl/learn/drawing-particle-effect-sprites) |
| Native transparent video | **Wan-Alpha** (open, on Wan 2.1, 14B) generates RGBA video; official ComfyUI template ("Wan 2.1 Alpha T2V 14B"), RGBA PNG frames out. **Not installed here** (new model download). Research: TransPixar, TransAnimate. | [Comfy docs](https://docs.comfy.org/tutorials/video/wan/wan-alpha), [Wan-Alpha](https://huggingface.co/htdong/Wan-Alpha), [TransAnimate](https://arxiv.org/html/2503.17934v1) |
| Thrown objects | No ready tool; the game convention is two sprites: the character's throw animation with a **release event**, and the projectile as its own looping sprite. Locally, **SAM 3 video tracking** (`SAM3_VideoTrack`, installed) can cut a moving object out of a clip as its own layer. | local ComfyUI |
| Quadrupeds | Tools exist (SpriteCook, Pixelcut) but no measured quality. Prompts need explicit four-legged gait words, side views matter most. Hand-made cat sheets (12-frame walk) are the yardstick. | [SpriteCook](https://www.spritecook.ai/walk-cycle-generator), [Sprite Sheet Diffusion](https://arxiv.org/html/2412.03685v2), [itch.io cat set](https://bragorn.itch.io/pixel-cat-animation-set) |
| Effect quality of H3 | Nothing published on fire / particles / magic; needs our own test. | [MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3) |
| 3D for sprite stacks | **TRELLIS 2** and **Pixal3D** (both installed, ComfyUI nodes present) turn an image into a 3D model (sparse voxels). Slicing that would replace today's outline carving: hollows and non-mirrored sides come out right. | [TRELLIS.2](https://microsoft.github.io/TRELLIS.2), [Comfy TRELLIS 2](https://docs.comfy.org/tutorials/3d/trellis2) |

## Proposed additions, in order

1. **Effects section (new asset type `effect`).** Describe it ("fireball", "healing sparkles", "slash
   arc", "explosion") → H3 renders it on pure black (first frame from H3 Image, clip from H3) →
   brightness-to-alpha key (new, next to the green key) → loop or one-shot → flipbook sheet + frames +
   GIF; export notes for additive materials. No facings (or 8 by rotating where it makes sense,
   e.g. projectiles). *First test: does H3 keep a black background and make readable effects?*
2. **Creature presets.** Four-legged wording for walk/run/idle, creature actions (pounce, sit,
   sleep, groom, eat), side views first. Test on a cat; compare with a hand-made 12-frame walk.
3. **Character + effect = two layers.** Render the action on green (cast pose) and the effect on
   black separately; the animation JSON gets an **event** ("spawn effect at frame 6, at the hand").
   The empty `events` field in the export JSON finally gets used.
4. **Thrown objects.** Throw action with a release event + the projectile as an effect/prop
   animation (spinning shield). Optional: SAM 3 video tracking to split an object out of one clip.
5. **Item from a picture** (Ronan: "show it an image of an item and add it, like new armor"):
   variants take an item image as Picture 2 on the anchor edit. Caution from the variant work: a
   second picture of the whole character made the facings copy it; an item-only picture needs its
   own test before facings use it.
6. **Sprite stacks from real 3D.** TRELLIS 2 / Pixal3D → voxels → slices, replacing the outline
   carve. Biggest quality jump for props; local, no download.
7. **Wan-Alpha (optional download)** if H3-on-black effects turn out weak: native transparent effects.

Each needs a real run before it is called done; 1 and 6 are the most promising because the models
are already here.
