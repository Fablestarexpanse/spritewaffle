# Changelog

## Unreleased

- Added browser-local appearance settings with five themes, live system matching, custom
  accents, interface scaling, spacing, reduced-motion support, and transparent preview backgrounds.
- Added a collapsible job browser, a search shortcut, and keyboard focus for job-stage
  navigation. The queue drawer now fits beneath the toolbar or opens along the bottom on narrow screens.

## 2026-11-21: directional sprite readiness

Additive only: with nothing new set, generation, the UI flow and every output are unchanged.
See [docs/MANIFEST.md](docs/MANIFEST.md) for the schema and all calls, and
[docs/PLAN_DIRECTIONAL.md](docs/PLAN_DIRECTIONAL.md) for the plan and decisions.

- **Asset manifest** `jobs/<c>/<j>/manifest.json` (schema_version 1): per-frame yaw for any view
  count (0 = facing the camera, clockwise seen from above), elevation, view index, mirrored +
  source view, foot point, colour / depth / normal / high-res master paths and a replayable
  downscale record. Built from existing files, so it doubles as the migration:
  `spritewaffle manifest`, MCP `manifest_migrate`. Kept current by the queue.
- **Camera profile** per project (`<jobs>/project.json`) with per-asset override: elevation,
  framing, character scale, light, background mode, canvas border, style notes. Applied to every
  still generation (one extra sentence, only when it says something the game profile doesn't)
  and to the pixel stage's character height. Snapshot in the manifest and each provenance
  entry. UI: Camera…; HTTP `/api/project/camera`, `/api/jobs/{c}/{j}/camera`; MCP `camera_profile`.
- **Foot points** for every frame (`footpoints.json`), and an optional **Align feet** stage
  (`frames_aligned/`, 2 px border by default; originals kept; export uses them once aligned).
- **Depth / normal slots**: `<frame>_depth.png`, `<frame>_normal.png` are picked up by the
  manifest and exported as atlas pages with the colour pages' exact layout. Everything that
  reads frames now reads colour frames only.
- **Mirror policy** per asset: `legacy` (default, today's behaviour), `none`,
  `mirror_left_from_right`, `custom`. Honoured by facings and animations. UI select with a hint
  for asymmetric characters; HTTP `/api/jobs/{c}/{j}/mirror_policy`; MCP `mirror_policy`.
- **Turntable** (Facings / Animations → Turntable…): read-only spin through the views in yaw
  order, speed, scrub, snap or crossfade between the two nearest views, hide mirrored views,
  foot-point overlay.
- Fixed while doing it: the character export, per-clip QA/export, mirroring, effect attaching
  and the showcase read every PNG in `frames/`, so a map file would have become an animation frame.
- Item pages no longer list fits whose job was archived.
