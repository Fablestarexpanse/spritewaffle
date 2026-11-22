# Studio upgrade roadmap

Baseline: `f694ddf`, 2026-11-21. The [existing wiki roadmap](wiki/Roadmap.md) tracks generation-specific experiments and defects. This document tracks the broader studio work.

| Area | Baseline | Work and acceptance |
| --- | --- | --- |
| Audit | Local FastAPI, CLI, and MCP share job operations. Core processing and format tests use synthetic fixtures and fake generation. Doctor validated the installed ComfyUI templates. | Use the existing suite and isolated job folders to verify each change. Record real inference and engine tests separately. |
| Appearance | A single HTML app with automatic device light/dark CSS, job filters, image viewer, and a queue drawer. | Delivered the first increment. Five presets, system matching, browser settings, preview surfaces, and job navigation passed Chromium at 1440, 800, and 390 px. Saved layouts and resizable panels remain open. |
| Brand assets | Official archive pending. | Blocked on the media kit. Validate the supplied badge, wordmark, and icons at their actual display sizes, then package only runtime variants. |
| Production reliability | Queue recovery and QA exist. Action and character exports have separate writers. | In progress. Character and action bundles have local freshness receipts. Animation details link saved QA findings to processed frames. Extend coverage to item and effect exports, then link upstream palette and source changes to the affected processing stages. |
| Animation and editing | Frame extraction, selection, pixel processing, takes, and animated preview exist. | The timeline supports timing, onion skins, ranges, tags, and pose markers. The comparison supports local reprocessing, whole-pixel offsets, and alignment to a reference foot. Saved edits are reversible and flow into QA or export metadata as appropriate. |
| Project style | Job palettes, game profiles, camera defaults and overrides, and directional manifests exist. | Delivered style defaults, saved job guides, and a portable reference library through the UI, CLI, HTTP, and MCP. Next add palette inheritance and style consistency checks. Connect saved reference collections to generation once there is a measured workflow. |
| World assets | Props, effects, and asset-specific workflows exist. | Build a small deterministic tileset authoring and export workflow before modular buildings and object states. |
| Advanced production | Item fits are flattened. Sprite stacks and an optional 3D template exist. Manifest map slots and arbitrary view metadata exist. | Prove layered equipment, higher-angle generation, and depth/normal generation independently using representative assets. |
| Engine integration | PNG, atlas, JSON, GIF, and Aseprite writers exist. | Validate import and playback in real Unity and Godot fixtures. Add Tiled and LDtk format checks when terrain metadata lands. |

Known baseline gaps include the missing H3 turntable template, incomplete higher-angle and auxiliary-map generation, and the UI issues tracked in the [UI audit](AUDIT_UI_2026-11-21.md) and [wiki roadmap](wiki/Roadmap.md).
