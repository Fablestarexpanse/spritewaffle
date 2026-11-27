# Roadmap (open items, updated 2026-11-26)

The one list of open work ([docs/UPGRADE_ROADMAP.md](../UPGRADE_ROADMAP.md) is a record of the studio upgrade).

Everything else in [docs/BACKLOG.md](../BACKLOG.md) and the audits is done. Suggested order:

1. **Directional test prep** (when the Myth-style test starts): generate more than 8 views
   (prompts worded by yaw degrees, nearest generated view as reference); depth/normal map
   generation from masters via `manifest.replay_downscale`.
2. **Style sets** (backlog #13): the local library, palette inheritance, and style checks
   are available. Anchor generation accepts one saved image. Multi-image guidance and family
   palette rules remain open.
   Terrain and tiles that match a character's style and palette are still open (#8, items done).
3. **Motion library** (#2, #11): more driving clips (idle, run, attack, jump); flow vs TARA per
   action; optional mannequin conversion of added clips.
4. **Effects:** auras lying flat on the ground (squash), a slash preset.
5. **QA-fail auto re-roll** (optional, off by default; Ronan prefers human review).
6. **Sprite stacks:** spikes at thin tips; colours follow the render unless a palette is set.
7. **UI polish (audit P3):** done 2026-11-26 (imported-anchor placeholder, folded "used by" list,
   Style/Prompts hidden on finished items).
8. **Equipment:** N view of a fitted item drops fine trim (words route). Layers work (cloak over vest,
   2026-11-26: fit on the fitted body); a video clip of a back view can lose what the top layer hides,
   fixed per job with one outfit sentence in the action text. A builder default for that is unmeasured.

## Tiles, textures and engines (2026-11-26)

Done: seamless textures, corner and blob transitions, collision shapes and tile properties, Godot
export, the game-developer audit's P1 and P2 lists (docs/AUDIT_GAMEDEV_2026-11-26.md). Open:

1. ~~Tiled `probability` per texture variant~~: done 2026-11-26 (tile **Weight**). SpriteWaffle's own map
   painter still places the first matching tile; weighted mixing there is open.
2. **Edge-only terrain sets**, more than one layer per map, maps larger than 32 × 32.
3. **Normal / height maps** for textures that tile with the colour map.
4. **DiT-aware seamless generation** for H3 (ComfyUI-AdvancedTiling or Universal-Seamless-Tiles;
   needs Ronan's approval to install).
5. **Target engine** setting picking an export preset (Godot files are always written now).
6. **Engine checks:** done 2026-11-26 (Tiled read shaped collision; LDtk 1.5.3 opened the new map.ldtk).
   Open: LDtk entities for map objects, non-square tiles in LDtk.
   (Unity `.aseprite` one-shot tags and pivots: checked 2026-11-26.)

## Studio (from the upgrade roadmap)

- Saved layouts and resizable panels.
- Desktop shortcut and installer integration.
- Multi-image generation and family palette rules.
