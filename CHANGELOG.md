# Changelog

## Unreleased

- Added browser-local appearance settings with five themes, live system matching, custom
  accents, interface scaling, spacing, reduced-motion support, and transparent preview backgrounds.
- Added a collapsible job browser, a search shortcut, and keyboard focus for job-stage
  navigation. The queue drawer now fits beneath the toolbar or opens along the bottom on narrow screens.
- Added character export freshness checks to the Export tab, HTTP API, CLI, and MCP. They report
  changed inputs, changed or missing bundle files, and interrupted writes. Re-export an older bundle
  once to start tracking it.
- Added action export freshness and export-only retries to animation details. PNG and Aseprite have
  independent receipts. Indexed Aseprite export reports a mismatch if the stored indices and PNG
  frames disagree.
- Animation details show the frames named by saved QA findings, with thumbnails that open the
  full-size frame. Passing reports with warnings display a Warning badge.
- Added an animation timeline with playback, scrubbing, saved per-frame timing, and reversible
  PNG replacement. Action and character exports use the edited frames. Character export checks
  that QA reviewed active replacements, and the asset manifest records the effective images.
- Added per-frame replacement history with previews and reuse after restoring the source.
  Onion skinning shows the previous and next frames while paused and follows the clip's loop mode.
- Added frame duplication, reordering, and order undo/redo. Copies keep independent timing and
  artwork edits, and attachment events follow their original frames when the order changes.
- Added a frame pixel editor with pencil, eraser, color picker, job palette swatches, zoom,
  pixel grid, keyboard editing, and draft undo and redo. Saves preserve unedited RGBA pixels
  and appear in replacement history. A draft whose frame has changed is refused.
- Added exact RGBA flood fill and rectangular selection with pointer and keyboard controls.
  Selections limit the paint tools and support erasing the selected area as one undoable edit.

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
