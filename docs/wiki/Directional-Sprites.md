# Directional sprites (Myth-style readiness)

Goal: SpriteWaffle's output carries everything a later test of Myth-style billboards needs (units
as upright 2D sprites on 3D terrain, more view angles, crossfading neighbouring angles, per-frame
depth/normal maps for engine lighting). SpriteWaffle produces and stores the data. Blending,
lighting and depth sorting are the engine's job.

Full schema and every call: **[docs/MANIFEST.md](../MANIFEST.md)**. Plan and decisions:
[docs/PLAN_DIRECTIONAL.md](../PLAN_DIRECTIONAL.md).

## In short

- **Manifest** per asset (`manifest.json`, schema_version 1), derived from the job's files. Per
  frame it holds: yaw, elevation, view index/count, mirrored + source view, foot point, colour /
  depth / normal / master paths, and the downscale record. `spritewaffle manifest` migrates old
  jobs; the queue keeps manifests current.
- **Angles:** yaw 0 = facing the camera, clockwise seen from above (S 0, W 90, N 180, E 270). Any
  view count; labels are display only. Generation makes 4 or 8 views today.
- **Camera profile:** per project (`jobs/project.json`) with per-asset override. With none set,
  nothing changes; when set, one extra prompt sentence + character height.
- **Mirror policy:** legacy (default) / none / mirror_left_from_right / custom.
- **Foot points + Align feet:** a foot point per frame; optional aligned copies with a 2 px border.
- **Depth / normal slots:** `000_depth.png`, `000_normal.png` next to the colour frame; exported as
  atlas pages in the same layout. Not generated yet: future maps should be made from the
  **master** and run through `manifest.replay_downscale` so they land on the colour pixels
  (verified to 0.9 % worst case on 250 real frames).
- **Turntable:** read-only viewer (Facings / Animations → Turntable…) with snap or crossfade by
  continuous yaw, scrub, speed, hide mirrored, foot overlay. Use it to spot angle-to-angle drift.

## Not done (by decision)

- Generating more than 8 views (needs prompts worded by yaw degrees). The data model and viewer
  already take any count.
- Depth/normal generation itself.
