# Game-developer audit (fresh eyes), 2026-11-26

An agent that had not seen the project audited it as an indie game developer (Unity / Godot /
Aseprite / Tiled). It was read-only. The web UI wasn't running, so UI findings come from code
and docs. Baseline: 340 pytest + 8 node tests passed. Evidence was checked on real exports
(`hare/courier`, `cat/tabby`, `goblin/*`). There were no tileset or map jobs on disk, so the Tiled
points come from the code.

## P1: blocks real use

**Status 2026-11-26:** #1 seamless textures, terrain transitions and project-palette lock done. #2 Godot SpriteFrames/scene/TileSet export done and verified in Godot 4.6. Target engine still doesn't switch presets (Godot files are always written). #3 blob-47 / mixed sets done for generation and Tiled/Godot export. Still open: edge-only sets, layers, maps over 32×32 (paint large maps in Tiled/Godot).

1. **Tileset workspace only imports tiles, it can't generate them.** There's no tile/terrain
   generation, so terrain matching a character's style is open. → Generate terrain/autotile sheets
   from the project palette and style. *(Seamless textures, 2026-11-26, are the first step.)*
2. **Godot 4 has no import path out of the box.** The output is `.aseprite` + TexturePacker JSON-hash
   (atlas.py), neither native to Godot 4. "Target engine" changes no export (core/project.py). →
   Write `SpriteFrames .tres` (AtlasTexture regions, fps) and let target engine pick an export preset.
3. **The terrain system can't express common autotile sets.** It's corner-only (terrain.py:30),
   with one wangset named "Terrain", no edge/mixed sets, no blob-47. Maps are at most 32×32, with one
   layer and one tileset. → Edge and mixed wangsets, a blob-47 template, layers, a larger limit.

## P2: painful

**Status 2026-11-26:** #4 guide fixed (one project PPU). #5 done (no colour list in RGBA mode). #6 done (durations, fps/loop/flip_x_of in meta). #8 done as options (POT, extrude); Unity pivot convention still unverified in an editor. #10 documented (ship `06_export/character`, 21 MB of the hare's 183 MB); per-action previews still always written. #7 done (shapes, one-way, typed properties; Godot 4.6 checked). #9: task-first [Guide](wiki/Guide.md) added (UI steps only, reference kept separate, glossary for job/anchor/stale/freshness); Studio-Guide left as the reference.

4. **Unity PPU guide = each profile's cell size**, so every asset gets a different texel density
   (cat 96, goblin 64, hare 384, tiles 16). This breaks Pixel Perfect Camera. → One project PPU.
5. **Painted characters write a 345,331-entry "palette"** into the atlas JSON (5.6 MB, character.py
   always writes `pal`). → Omit the palette in RGBA mode.
6. **The TexturePacker JSON has no fps/durations.** With `mirror="flip"`, the W/NW/SW animations
   silently disappear from it (atlas.py). → Add frameRate/duration and a flipX source, or keep
   mirrors in that file.
7. **Collision is full-tile rectangles only** (tileset.py): no slopes, polygons, one-way platforms
   or per-tile properties. → Per-tile shapes + properties in `.tsj`.
8. **Atlas pages aren't power-of-two and are over 2048** (hare 4091×2183). There's a 1 px gap with no
   extrude, so frames bleed under bilinear/mipmaps. Pivot conventions in the docs (bottom-origin)
   vs TexturePacker (top-origin) are unverified in Unity. → Optional POT pages, 1–2 px extrude.
9. **User docs read like an API reference** (Studio-Guide lists CLI/HTTP/MCP for every action).
   "Receipt" / "freshness" jargon, and `{character}` in URLs for tilesets. → A task-first guide, with
   the reference separate.
10. **Export bloat:** one painted character's `06_export` is 183 MB (12f + 24f, each with aseprite,
    strip, frames, preview, GIF; untrimmed 384² sheets). → A "game bundle only" export, trimmed sheets.

## P3: polish

**Status 2026-11-26:** #11 test count fixed, UPGRADE_ROADMAP marked as a record (one open list: wiki Roadmap). #12 `tiledversion` and the Wang set icon done; per-tile `probability` waits for variants that share edges. #13 documented. #15 done (allow empty cells). #14 checked in Unity 6000.6 / Aseprite Importer 6.0.0: one-shot tags import as non-looping clips, the documented custom pivot lands on the foot point (default Bottom Center is 1 px low). #8's pivot question is answered for `.aseprite`.

11. Doc drift: AGENTS.md says ~220 tests / ~1 min (now 340 / ~100 s). There are two roadmaps
    (docs/UPGRADE_ROADMAP.md and wiki Roadmap.md).
12. Tiled export: no `tiledversion`, no tile `probability`, and wangset `"tile": -1` (blank terrain icons).
13. `.aseprite` 83 ms at 12 fps drifts about 0.4% against the JSON fps (unavoidable; document it).
14. Unity handling of one-shot tags is unverified.
15. Map export refuses any unresolved cell. → Offer "export with empties".

## What a game dev would love

Clean pixel output (exactly 16 colours, binary alpha); pivots stable across all 8 directions;
seamless loops; a good `.aseprite` writer (tags, durations, pivot slice, indexed); a real atlas
packer (trim, dedupe, page limit, map pages sharing UVs); correct Tiled basics; one palette per
character plus project palettes; full UI / CLI / MCP automation.

## Seamless textures: what's needed

1. Tile sizes 8–64 and custom, plus painted 256–2048. Pixel mode is locked to the project palette.
2. Real wrapping plus a measured seam score with pass/fail.
3. Wrap preview: 3×3 and 8×8, offset-by-half view, grid toggle, nearest zoom.
4. Variants that tile with each other; one atlas; Tiled `probability` per variant.
5. Terrain feed: two textures → corner-16 / blob-47 transition set in the tileset workspace.
6. Optional normal/height/roughness maps that tile with the colour map.
7. Output: PNG atlas (margin, spacing, extrude), `.tsj` with variants, animated water/lava with a
   temporal loop check, Godot `TileSet .tres`, Unity import hints (Point, no compression, PPU).
8. Style lock (project palette, references, style check); human approval before joining a tileset.
9. UI / CLI / MCP parity, plus a receipt and freshness check like the other exports.
