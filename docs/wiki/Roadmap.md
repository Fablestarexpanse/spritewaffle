# Roadmap (open items, updated 2026-11-26)

The one list of open work ([docs/UPGRADE_ROADMAP.md](../UPGRADE_ROADMAP.md) is a record of the studio upgrade).

Everything else in [docs/BACKLOG.md](../BACKLOG.md) and the audits is done. Suggested order:

1. ~~Directional test prep~~: 16/24/32 views from a 3D model built 2026-11-27 (Facings -> More views from a
   3D model; body plans person / animal / monster, extra words per job; props use sprite stacks). Depth/normal
   maps done (Lighting maps). Open: engine checks of both.
2. **Style sets** (backlog #13): the local library, palette inheritance, and style checks
   are available. Anchors take one saved image or, since 2026-11-27, a style set of 2-3 (Also match). Family
   palette rule done 2026-11-27 (a variant keeps its base's colours exactly).
   Terrain and tiles that match a character's style and palette are still open (#8, items done).
3. **Motion library** (#2, #11): 2026-11-27 idle, run, attack (front-facing) and jump mannequin clips added
   (in review), each with a recommended transfer (flow for idle; TARA for run, attack, jump). Open: other
   facings, mannequin conversion of added clips.
4. ~~Effects: flat auras, slash~~: done 2026-11-26 (Lies flat on the ground, aura preset, slash reworded).
5. **QA-fail auto re-roll** (optional, off by default; Ronan prefers human review).
6. ~~Sprite stacks: spikes at thin tips~~: 2026-11-27 one-voxel strands trimmed (pine prongs 8.5 -> 6.7 a frame;
   the rest is rotation aliasing of any stack renderer). Colours follow the render unless a palette is set.
7. **UI polish (audit P3):** done 2026-11-26 (imported-anchor placeholder, folded "used by" list,
   Style/Prompts hidden on finished items).
8. ~~Equipment~~: done 2026-11-27. N view keeps trim, hood and length; clips of a layered fit name the
   clothes under the top layer by default (0/3 -> 3/3). Single fits get no line (unmeasured).

## Tiles, textures and engines (2026-11-26)

Done: seamless textures, corner and blob transitions, collision shapes and tile properties, Godot
export, the game-developer audit's P1 and P2 lists (docs/AUDIT_GAMEDEV_2026-11-26.md). Open:

1. ~~Tiled `probability` per texture variant~~: done 2026-11-26 (tile **Weight**, and **mix variants** in
   SpriteWaffle's own map painter).
2. ~~More than one layer per map~~: done 2026-11-26 (up to 4 extra tile layers; also edge sets, path
   generation and maps up to 64 × 64).
3. ~~Normal / height maps~~: done 2026-11-26 (estimated from colour; Lighting maps setting).
4. ~~DiT-aware seamless generation~~: measured 2026-11-27. Universal-Seamless-Tiles' latent roll lowers H3's raw
   seam score from 3.24 to 2.05 but never reaches seamless, and the code-side seaming already makes finished
   textures seamless, so it is not wired in. Its circular-VAE node fails on H3's VAE.
5. **Target engine** setting picking an export preset (Godot files are always written now). Waiting on a
   measured need: which settings a Unity or GameMaker project wants different (pot, extrude, mirror?).
6. **Engine checks:** done 2026-11-26 (Tiled read shaped collision; LDtk 1.5.3 opened the new map.ldtk).
   LDtk entities for map objects: done 2026-11-26. Non-square tiles in LDtk: not possible (LDtk's
   layers and tilesets have one square grid size); those maps export Tiled and SpriteWaffle JSON only.
   (Unity `.aseprite` one-shot tags and pivots: checked 2026-11-26.)

## Studio (from the upgrade roadmap)

- ~~Resizable panels~~: the job list's width is dragged, remembered and reset (2026-11-26).
- ~~Desktop shortcut~~: `spritewaffle shortcut` (2026-11-26). A packaged installer is open.
- ~~Multi-image generation~~ (style sets, 2026-11-27); family palette rule done (2026-11-27).
