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
| World assets | Props, effects, and asset-specific workflows exist. | Named maps support terrain and manual tile placement and export to a self-contained ZIP. Tiled 1.12.2 imported and rendered a representative map. Object-state metadata and modular buildings are next. |
| Advanced production | Item fits are flattened. Sprite stacks and an optional 3D template exist. Manifest map slots and arbitrary view metadata exist. | Prove layered equipment, higher-angle generation, and depth/normal generation independently using representative assets. |
| Engine integration | PNG, atlas, JSON, GIF, and Aseprite writers exist. | Tiled import and rasterization verified for a single orthogonal tile layer. Validate engine-specific imports in Unity and Godot. LDtk remains open. |

Known baseline gaps include the missing H3 turntable template, incomplete higher-angle and auxiliary-map generation, and the UI issues tracked in the [UI audit](AUDIT_UI_2026-11-21.md) and [wiki roadmap](wiki/Roadmap.md).

The native tileset writer uses the documented Tiled JSON fields for image grids, local tile IDs,
and tile collision object layers. It uses the existing Pillow runtime and adds no Tiled dependency.
The writer includes a corner terrain set and puts corner assignments in Tiled's eight-entry Wang
order. Preview resolution uses the same saved rules and requires an exact corner match. Animated
tiles store the local tile ID and duration in milliseconds in Tiled's animation array.
Tiled 1.12.2 imported the TMJ and TSJ, re-exported them to TMX and TSX, and rasterized the map.
The test checked global tile IDs, a transparent cell, collision, animation timing, and Wang rules.
[Tiled JSON format](https://doc.mapeditor.org/en/latest/reference/json-map-format/)

The map ZIP puts an orthogonal TMJ, its TSJ and PNG, and the native map and tileset JSON
files together. The Tiled layer stores 0 for empty cells and offsets local tile IDs by the
external tileset's first global ID of 1. The native layer retains local IDs and the authored
corner grid. Missing transitions block export and leave any previous ZIP in place.
[Tiled global tile IDs](https://doc.mapeditor.org/en/stable/reference/global-tile-ids/)
