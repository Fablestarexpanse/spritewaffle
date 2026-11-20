---
name: spritewaffle
description: Make game-ready pixel-art sprite sets (8 facings x animations, PNG/.aseprite/GIF for Unity) from a text description with the SpriteWaffle MCP tools and the local ComfyUI. Use when asked to create, animate, re-roll or check a game character, creature or prop sprite.
---

# SpriteWaffle

SpriteWaffle turns a description into an approved anchor still, 8 facings, and per-facing
animations, then pixelizes, QA-checks and exports them. Rendering happens on the local ComfyUI;
the MCP tools only queue work. Everything for one asset lives in one job (`character/job_id`).

## Tools

| Tool | Use |
|---|---|
| `generate(character, stage="anchor", description=..., asset_type=..., style_ref=...)` | new job + anchor still |
| `generate(character, stage="facings", job_id=...)` | 8 facings (or `only=["SW"]` to re-roll) |
| `animate(character, job_id, facing, action)` | clip -> frames -> pixel art -> QA -> export |
| `status(character, job_id, wait_seconds=..., include_images=True)` | wait, then see results |
| `approve(character, job_id, stage)` | relay the human's yes |

## Workflow

1. **Hero asset first.** For a new game, make one hero asset and get it approved before anything
   else. Every later asset passes the hero as `style_ref="hero_character/job_id"` so the whole cast
   shares pixel size, outline and palette feel.
2. `generate(stage="anchor")`, then `status(wait_seconds=300, include_images=True)` and **show the
   anchor to the human**. Re-roll with a new `seed` until they like it.
3. `approve(stage="anchor")` **only after the human says yes**. Never approve on your own judgement:
   everything downstream copies the anchor (rule: one approved anchor per character).
4. `generate(stage="facings")`, wait, show the facings sheet. Drift numbers are colour distance
   (0..1) and height ratio vs the anchor; above ~0.35 colour or ±12% height is a re-roll
   (`only=["NW"]`). A drifting facing whose mirror partner is fine is mirrored automatically.
5. Human approves -> `approve(stage="facings")`.
6. `animate` per facing x action. Start with `S idle` and `S walk` to check the look before
   queuing all eight facings. One render takes about 1-4 minutes; queue several and wait once.

## Motion library (experimental)

`animate(..., motion="walk_S_mannequin")` transfers an approved library clip's motion onto the
asset with TARA instead of rendering with H3, so the whole cast shares one timing. `status()`
without a job lists the library. Library clips come from a plain grey mannequin (a costumed
driving character leaks its identity). Each transfer reports `identity_drift`; above 0.35 the
report warns: re-roll with a new seed or animate without `motion`. Show the human the result
before relying on it.

`animate(..., motion=..., method="flow")` is the pixel-exact alternative: no render (seconds, CPU),
the facing's own pixels are moved by the clip's optical flow, so colours and identity are exact.
It cannot turn the character or invent unseen parts; feet can smear where legs cross. Prefer flow
for in-place cycles of the same facing; use TARA or a normal H3 render when the pose changes a lot.

## Asset types and actions

| asset_type | actions that make sense |
|---|---|
| character | idle, walk, run, attack, jump |
| creature | idle, walk, run, attack |
| prop | idle |

Cyclic actions (idle, walk, run) loop; attack and jump end back on the idle pose.

## Shipping

`export_character(character, job_id)` bundles every QA-passed animation into one `.aseprite`
(a tag per `action_facing`; Unity's Aseprite Importer turns each into a clip and builds an
Animator Controller) plus `<character>_atlas.png` + `.json`. It lists what it skipped (QA failures).
Hand the human those paths.

## Sprite stacking (props, vehicles)

For a rigid prop (`asset_type="prop"`, anchor = straight front view, approved by the human):
`stack(character, job_id, height=24)` generates back/right/top views and carves them into
`height` slices + turntable GIF + 8-angle rotation sheet; `regenerate_views=False` only rebuilds
(seconds). Hollows come out solid and the left side mirrors the right: not for characters.

## Reading QA

`status` returns per action and frame set (12f, 24f) a `status` (pass/fail), `errors`,
`warnings` and `reroll` targets. Act on the target:

| reroll target | what to do |
|---|---|
| `select` / `select (loop point)` | `animate(..., reprocess_only=True)`; if it persists, re-render with a new seed |
| `pixelize` | palette or stray-pixel issue: re-process; persistent -> tell the human (profile palette) |
| `action video` | sprite size drifts inside the clip: re-render with a new seed |
| `layout` / `layout/profile cell_size` | sprite touches the cell edge: the profile's cell_size is too small -> tell the human |

A frozen clip is detected and re-rendered automatically (the report says `fallback`).

## Don'ts

- Don't approve stages for the human.
- Don't describe camera angles as isometric/top-down in descriptions; the profile owns projection.
- Don't ask for walk cycles from stills: motion always comes from `animate`.
- Outputs are files on disk (paths in `status`); hand the human the `.aseprite` and PNG paths.
