# Changelog

## Unreleased

- Effects: **Lies flat on the ground** squashes auras and rune circles onto the floor; new **aura** preset; the **slash** preset is reworded and now draws a sweeping arc instead of a crosshair flash.
- Maps can have up to 4 extra **tile layers** above the terrain (decoration, props), exported as extra Tiled and LDtk tile layers.
- **Path sets** from two textures: Transition → Set: Path makes the 16 edge tiles (straights, bends, junctions, crossing, ends) with edge terrain rules, ready for Tiled and Godot.
- **Edge terrain sets** (paths, fences, roads): set type Edges in the Terrain panel; exported as a Tiled edge Wang set and a Godot Match Sides terrain set.
- The Godot TileSet export no longer varies between runs when a tile's terrains tie (its centre came from a set whose order changed per run); the later terrain wins.
- LDtk export includes map objects as entities (one per object kind, with name, state, states, solid and id fields), drawn with each object's current tile.
- Maps up to **64 × 64** (was 32 × 32), with a **Size** control in the map panel; resizing keeps painted corners, placed tiles and objects that still fit and asks before dropping any. New maps in the panel were fixed at 8 × 6 before.
- Textures can export **lighting maps**: a height and a normal map (OpenGL, green up) per tile and as sheets, seamless like the tile, estimated from the colour. Off by default.
- Maps can **mix variants**: tiles with the same terrain corners are picked per cell by tile weight. Off by default; maps saved before keep their first-tile look.
- Tile **Weight** (tileset panel, `tileset weight`, `/tileset/probability`, MCP `weight`): how often Tiled picks a tile among tiles that fit the same place, exported as Tiled's `probability`. Lets a filled area mix texture variants.
- Map ZIPs include `map.ldtk` for LDtk 1.5: the tiles, a Collision IntGrid (solid / one-way), and each tile's collision polygon and properties as per-tile custom data. Square tiles only; the export says when it is left out.
- Prepare map ZIP works with "allow empty cells" ticked (the button stayed disabled while any cell was unresolved).
- UI polish: an imported anchor with no description says so instead of showing an example; the Sizes dialog shows "used by N jobs" with the names folded; an item whose front and back are approved hides Art style, Prompt writer and Prompts (they no longer change it).
- Layered clothing works: fit a second item on an already-fitted body (a cloak over a vest). The showcase subtitle names every layer ("wearing leather vest + blue cloak").
- A queued task without a profile uses the job's own profile (it fell back to the built-in 64 px one, so `spritewaffle animate` without --profile cut a 104 px job's jump off).
- Dark slivers between arms and body are keyed: a black fill touching the sprite outline is found inside its thin green loop, and the dark-green gap mush video models leave (far from #00FF00) is keyed when it is wider than an outline tint. The second only runs when the approved facing has no green of its own, so green clothing is never cut; the pixel report records it.
- Showcase GIF is branded: brand-purple header with the app icon, the character and what it wears, "Made with SpriteWaffle" wordmark, the icon in each compass grid's centre, and a horizontal-logo end card. Turnaround shows the game sprite (not the source painting), actions play idle -> walk -> run -> jump -> attack.
- Re-rendering or re-processing a direction also re-mirrors the directions mirrored from it (NE -> NW), so they don't stay flips of the old clip or block the export as stale.
- The Animations tab shows clips still waiting in the queue as Queued cards (status now lists queued tasks).
- Fitted items: back views name the item without its front details in the caption, so front lacing or buckles stop appearing on the back (3 of 3 plain backs, was 1 of 1 wrong).
- Re-rolling one view of a variant no longer drops the other views' drift and warnings from the facings report. The variant anchor gets **Edit prompt…** too.
- **Edit prompt…** beside each facing's Re-roll: see the exact prompt a view was made with, edit it, save and re-roll just that view (CLI `prompt`, HTTP `/prompt`, MCP `prompt`). The edit is stored per file and applied where every still is generated; provenance marks it.
- An item fitted on a base body (or animal) now gets its facings: they were refused as 'from the turnaround sheet' before the variant check.
- Green-screen keying cleans enclosed gaps in passes: speckled green between arms and legs, black fills ringed by green, and the specks left behind (H3 image edit returns those for item fits). Clean sprites are unchanged.
- Texture variants can share edges ("Variants fit together"; CLI `--shared-edges on`, HTTP/MCP `shared_edges`): each takes variant 1's colour-matched border, joined along least-visible cuts, with one palette for pixel art, so any variant fits next to any other. Mixed preview and a side-by-side score in the UI.
- Queue: a worker that loses the lock (the web UI takes it over) stops claiming tasks and takes the queue back when the holder exits; the MCP server's worker waits in standby instead of giving up. Before, an older MCP worker kept running next to the UI's and failed tasks its code didn't know.
- Checked in Unity 6000.6 (Aseprite Importer 6.0.0): one-shot animations import as non-looping clips with 83 ms frames, and the documented custom pivot puts every frame on the exported foot point. The Unity guide says the default pivot is 1 px low.
- Map export can leave unresolved cells empty (UI checkbox, `--allow-empty`, HTTP/MCP `allow_empty`). Tiled files carry `tiledversion` and the terrain set has an icon tile. One open roadmap (wiki); `.aseprite` ms rounding documented.
- New task-first wiki page, [Guide: what do you want to make?](docs/wiki/Guide.md): one section per job (character, own art, animal, items, effects, seamless ground, transitions, collision, modules, engine import) using only app buttons, plus a glossary.
- Tileset collision shapes: half tiles, 45° and 2:1 slopes, custom polygons and one-way platforms per tile, plus typed per-tile properties. Exported to Tiled (polygon objects, tile properties), Godot (collision polygons with one_way, custom data layers; checked in Godot 4.6), tileset.json and tile modules. UI, CLI (`--shape`, `--points`, `--one-way`, `tileset properties`), HTTP and MCP.
- Character atlas options: power-of-two pages and 0-4 px edge extrusion (UI, CLI `--pot` / `--extrude`, HTTP, MCP). TexturePacker files gain per-frame `duration` and `meta.animations` (fps, loop, `flip_x_of`), so flipped W/NW/SW animations no longer vanish from them. RGBA characters omit the colour list from the atlas JSON (hare: 5.62 MB -> 0.09 MB). Unity guide: one project PPU. Docs say which export folder is the game bundle.
- Godot 4 export: character exports also write a SpriteFrames `.tres` and an AnimatedSprite2D `.tscn` (pivot on the origin). Tileset exports write a TileSet `.tres` with collision and the terrain set. Verified by importing into Godot 4.6.
- Blob (47 + plain) terrain transitions alongside the 16-tile corner sets, with a mixed terrain rule mode exported as a Tiled mixed Wang set and a Godot Match Corners and Sides terrain set. Transitions gain an edge lip. Pixel textures snap to the project master palette (OKLab) and lose orphan pixels without breaking the wrap.
- The app's scripts and page are now served with revalidation and versioned URLs, so a browser picks up an update instead of running cached old JavaScript.
- Added terrain transitions: two approved seamless textures become the 16-tile corner set as a new tileset job with corner terrain rules filled in. Tiles fit together in any arrangement, with a ragged noise border (hard for pixel art, soft for painted). Browser (Make transition…), CLI `transition` and MCP `transition`.
- Added seamless textures: a new asset type that generates tileable ground, wall or water tiles (16–512 px, pixel or painted, 1–16 variants). Edges are joined along the least visible cut so each tile wraps exactly, with a wrap score, a repeat preview with an offset-by-half view, re-roll per variant, re-cutting without a new render, export, and Send to tileset. Browser, CLI (`texture`) and MCP (`texture`).
- Added a file chooser to import a starting image, with original files retained for retries. Approval and the next stage sit beside the image preview.
- Moved existing animation clips above generation and added direct timeline access. The generation form uses the job's supported directions and available artwork.
- Kept queue failures from opening a panel or blocking clicks, preserved drafts and focus on workspace refresh, and added a clear action to empty job searches.
- Added standalone tile module ZIPs with transparent PNG artwork, editable pixel pivots, and collision rectangles. Verified the artwork and geometry in a Godot 4.6 import fixture.
- Added reusable tile modules for modular asset authoring. Save a rectangle from the atlas and stamp it into a map draft, with transparent slots preserving the original ground.
- Reorganized the workspace around the Home link, global New asset, Project menu, job stages, and contextual settings. Added direct Tileset navigation and fixed queue focus, grouped Terrain discovery, and empty export controls.
- Added 28 named local `studio` operations shared by the browser, CLI, and MCP. Brought manual map preview controls and character export options into parity.
- Shortened the README, added workspace screenshots, and moved detailed setup and workflows into the wiki.
- Added reusable object templates scoped to a tileset. Placements retain template provenance and can start in different states on different maps.
- Added cell-aligned map objects with named atlas states, a live preview, and an active-state tile on a separate Tiled layer. Verified a workshop door with open and closed states.
- Added per-cell manual tile placement, explicit empty cells, and restore-to-terrain controls. Tiled 1.12.2 imported and rendered the resulting map and retained its animation, collision, and Wang terrain metadata on re-export.
- Added named terrain maps that reopen across browser sessions. Resolved maps export as a portable ZIP with an orthogonal Tiled map, SpriteWaffle JSON, and the source tileset.
- Added per-tile animations with ordered atlas frames, individual durations, and synchronized playback in the selected-tile and terrain map previews. SpriteWaffle JSON and Tiled TSJ retain the timing, and edits mark prior exports stale.
- Added named corner terrain rules and an 8 × 6 map preview that flags missing transitions. Tileset exports include the saved rules in SpriteWaffle JSON and Tiled Wang-set metadata.
- Added a native Tileset workspace for PNG grid import, tile inspection, full-tile collision, and tracked export to SpriteWaffle JSON and Tiled TSJ.
- Foot alignment now carries depth and normal maps, the character pivot, and effect spawn points with the colour frames. Atlas packing keeps distinct auxiliary texels even when the colour frames are identical.
- Character exports detect stale foot alignment after processed frames, aligned copies, or the camera border change. The export check offers a local rebuild before replacing the existing bundle.
- Mirror and optical-flow export checks now report changes to their source frames or guide. Palette-only rebuilds retain manual frame selections. QA and export use the latest processed frame sets.
- Added the Windows checkout launcher for an installed `.venv`.
- Action and character exports detect stale processed frames after changes to a tracked clip, selection, or palette. Re-process frames can decode a replaced saved clip locally, and stale exports stay intact until they can be rebuilt.
- Fixed standalone Item generation so a library or approved hero reference supplies colour swatches without uploading the subject image. Browser, CLI, and MCP generation preserve the saved Item type when no override is given. Character fitting stays available through Make a variant.
- Added freshness checks for item and effect bundles. A check reports changed inputs, missing or changed outputs, and interrupted writes. Existing bundles can be tracked by exporting the item again or reprocessing the saved effect clip.
- Added project-library image selection for new anchors. The browser previews the chosen image, and the queue rejects archived or missing references. The generated take records the reference ID and opens for review.
- Added a read-only project style check for asset settings and processed clip palettes. It identifies off-palette colours and keeps the job screen available when a clip's processing record is damaged.
- Integrated the official SpriteWaffle artwork into the app header, welcome screen, About dialog, browser favicon, and README. Package the supplied Windows icon and keep the repository social preview artwork outside the app wheel.
- Added project master palettes for new jobs. Pixel-art processing uses the saved project palette when the game profile or job has no fixed colours. Existing assets keep their saved colours when the project palette changes.
- Added a project reference library for local PNG, JPEG, and WebP images. Group references into collections, preview the full image, edit titles and notes, or archive and restore entries. Original copies and previews move with the jobs folder.
- Added project style settings for the default art style, game profile, target engine, and art direction. New jobs can inherit the defaults or override them individually. The job and asset manifest retain the guide saved at creation.
- Camera and project style edits preserve one another and refuse to overwrite a newer project schema. MCP and CLI queue submissions carry the job's game profile into the worker.
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
- Added per-frame-set playback modes and inclusive ranges. The timeline, onion skins, QA seam
  checks, action previews, and Aseprite tags use the saved range. All frames still export.
  A missing or crossed endpoint needs repair before the clip can export.
- Added reversible blank and PNG frame insertion and removal. Inserted frames keep their
  own editable source PNG. Removing a frame leaves its files and edits intact and omits any
  attachment event at that frame until the frame is restored.
- Added named animation ranges with independent loop or play-once preview. Tags follow frame
  IDs, contribute loop seam findings to QA, and export in Aseprite and JSON alongside the
  default animation.
- Added local reprocessing of selected frames with a before-and-after comparison, green spill
  controls, and exact changed-pixel highlighting. Applying saves a reversible version and
  rejects a comparison whose retained master, processing record, or artwork has changed.
- Added whole-pixel frame repositioning and alignment to a reference frame's foot point.
  The comparison shows the measured foot points, refuses clipped artwork, and saves through
  the existing replacement history.
- Added pose markers for eight animation beats, with navigation between marked frames.
  Markers follow frame IDs through sequence edits and export in action and character JSON
  and in the asset manifest.

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
