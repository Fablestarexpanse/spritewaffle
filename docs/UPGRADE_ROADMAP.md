# Studio upgrade roadmap

Baseline: `f694ddf`, 2026-11-21. The [existing wiki roadmap](wiki/Roadmap.md) tracks generation-specific experiments and defects. This document tracks the broader studio work.

| Area | Baseline | Work and acceptance |
| --- | --- | --- |
| Audit | Local FastAPI, CLI, and MCP share job operations. Core processing and format tests use synthetic fixtures and fake generation. Doctor validated the installed ComfyUI templates. | Use the existing suite and isolated job folders to verify each change. Record real inference and engine tests separately. |
| Appearance | A single HTML app with automatic device light/dark CSS, job filters, image viewer, and a queue drawer. | Delivered the first increment. Five presets, system matching, browser settings, preview surfaces, and job navigation passed Chromium at 1440, 800, and 390 px. Saved layouts and resizable panels remain open. |
| Brand assets | Official Concept #5 media kit supplied. | App header, welcome, About, favicon, and README use supplied artwork. The wheel includes the Windows icon. A Windows checkout launcher opens the local app. Desktop shortcut and installer integration remain open. |
| Production reliability | Queue recovery and QA exist. Action and character exports have separate writers. | Character, action, item, and effect bundles have local freshness receipts. Action processing tracks imported and generated clips, mirrors, optical-flow inputs, and palettes. Palette-only rebuilds retain the source selection. Tracked alignment guards character exports and keeps auxiliary maps, pivots, and effect points registered to the colour frames. |
| Animation and editing | Frame extraction, selection, pixel processing, takes, and animated preview exist. | The timeline supports timing, onion skins, ranges, tags, and pose markers. The comparison supports local reprocessing, whole-pixel offsets, and alignment to a reference foot. Saved edits are reversible and flow into QA or export metadata as appropriate. |
| Project style | Job palettes, game profiles, camera defaults and overrides, and directional manifests exist. | Delivered style defaults, palettes, read-only consistency checks, and portable reference collections. One selected library image can guide an anchor and is recorded in its provenance. Multi-image generation and family palette rules remain open. |
| World assets | Props, effects, and asset-specific workflows exist. | Tilesets import a validated PNG grid, retain transparent slots, and support per-tile collision and corner terrain rules. The local map preview reports unmatched combinations. Add tile animation and a persisted map asset next. |
| Advanced production | Item fits are flattened. Sprite stacks and an optional 3D template exist. Manifest map slots and arbitrary view metadata exist. | Prove layered equipment, higher-angle generation, and depth/normal generation independently using representative assets. |
| Engine integration | PNG, atlas, JSON, GIF, and Aseprite writers exist. | Validate import and playback in real Unity and Godot fixtures. Add Tiled and LDtk format checks when terrain metadata lands. |

Known baseline gaps include the missing H3 turntable template, incomplete higher-angle and auxiliary-map generation, and the UI issues tracked in the [UI audit](AUDIT_UI_2026-11-21.md) and [wiki roadmap](wiki/Roadmap.md).

The native tileset writer uses the documented Tiled JSON fields for image grids, local tile IDs,
and tile collision object layers. It uses the existing Pillow runtime and adds no Tiled dependency.
The writer includes a corner terrain set and puts corner assignments in Tiled's eight-entry Wang
order. Preview resolution uses the same saved rules and requires an exact corner match. Animated
tiles and editor import testing with an installed Tiled executable remain open.
[Tiled JSON format](https://doc.mapeditor.org/en/latest/reference/json-map-format/)
