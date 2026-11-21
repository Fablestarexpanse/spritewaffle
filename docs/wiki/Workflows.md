# Workflows

Every asset is a **job**: `jobs/<character>/<job_id>/`. New → pick the kind:

| Kind | Steps | Notes |
|---|---|---|
| character / creature | Anchor → Facings (8 or 4) → Animations → Export | the main pipeline |
| base body | Anchor (turnaround sheet) → Facings (from the sheet) → Animations → Export | plain grey undershirt + shorts, to fit items on |
| item | Anchor (front) → Facings (back) → Export | armor, cape, weapon; kept as the original asset |
| animal | Anchor (turnaround sheet) → Facings → Animations → Export | four legs; all views from one sheet |
| effect | Effect tab: render → process → flipbook | spells, fire, explosions; loop or one-shot |
| prop | Anchor → Sprite stack → Export | slices you can spin; TRELLIS.2 3D by default |

## Characters

- **Style reference:** make one hero, approve it, then pick it as the style reference for new
  anchors ("hero first, then reference it").
- **Prompt writer:** Template (fixed wording) or AI (Qwen3-VL 4B writes descriptions and
  motion; checked, falls back to the template). **Prompts…** shows what will be sent and what
  was sent, and lets you edit the creative text; the rules around it can't be removed.
- **Sizes…:** game profile: cell size, sprite height, palette size, outline, camera angle
  (side / top-down 3/4 / iso), 4 or 8 directions, mirroring, fps per action.
- **Palette:** one per job, built from the anchor + every facing (so back-only colours are in
  it), or loaded from `.gpl` / `.hex` / `.png`.
- **Actions:** presets (idle, walk, run, attack, jump) or your own via Prompts… → Actions (e.g.
  "throw shield"). A non-looping action can end "anywhere" (a thrown shield doesn't come back).
- **Motion library** (experimental): approved driving clips reused through flow transfer or TARA.

## Variants (one change)

On a character with approved facings, **Make a variant…** has three modes:

1. **Fit one of your items** (below).
2. **Describe a change**: "add a long green cape".
3. **From a picture**: an item image plus how it's used ("wearing this").

Each facing is redrawn from the base's own facing, so poses line up frame for frame. The
variant is listed under its base in the job list.

## Equipment (paper doll)

The flow Ronan set: make the item **separately** (front + back), keep it as the original, and
put it on any base body. Nothing is cut back off the character.

1. New → **item**: describe it; the anchor is the front, Facings draws the back. Approve both.
2. New → **base body** (or use any character): approve its facings.
3. On the item: **Fit on…** → pick the body, "wearing this". Or, from the body: Make a variant…
   → Fit one of your items. Result: the body wearing the item, all 8 facings, animatable.
4. The item's **Export** tab saves its front and back as sprites (icon, ground drop).

Front/side views use the item front as a reference picture; NE/NW use its back; N uses words
(see [Prompting lessons](Prompting-Lessons.md)). Review each facing; Re-roll the odd one.

## Animals

The anchor step draws one **turnaround sheet** (front, side, back, two 3/4 views), SAM 3 cuts it
apart, and W/SW/NW are mirrored. Facings → **Re-draw sheet** makes a new sheet; single views can
still be re-rolled. Animal actions: idle, walk, run, pounce, sit, sleep.

## Effects

New → effect: describe the look and the motion, choose loop / one-shot, background (black or
green). H3 renders it; brightness becomes alpha; frames are picked and exported as a flipbook.
Attach an effect to a character's animation (spawn point, frame, front/behind, projectile) from
the animation's detail view; the export JSON carries the event.

## Props / sprite stacks

New → prop: a straight front-view anchor → **Sprite stack**: TRELLIS.2 builds a 3D model from a
3D-look render of the anchor, which is sliced into layers. The spin viewer and the spin / build-up
GIFs are on the same tab.

## Styles

Pixel art (default; grid detection, palette, cleanup), Hand-painted, Anime cel, Comic ink
(smooth styles draw at 4× and skip the palette). Set per job; change it before generating.
