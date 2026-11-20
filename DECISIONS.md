# SpriteWaffle decisions log

NEXT: Phase 2 step 1 done (anchor + 8 facings). Awaiting Ronan: diagonal default nearest vs multi. Then step 2: transition pose, H3 action, bridge frames.

- 2026-11-20 Repo lives at `F:\Tools\Sprite tool` (Ronan: "local"), private GitHub repo.
- 2026-11-20 No H3 sample clip exists yet. Phase 1 e2e runs on a synthetic chroma-green clip
  (`tests/synth.py`); a real H3 clip gets generated via ComfyUI before acceptance.
- 2026-11-20 Deps: numpy, Pillow, opencv-python-headless, websockets; pytest dev. No scikit-learn
  (k-means in Oklab is a few lines of numpy). Profiles are JSON (no PyYAML).
- 2026-11-20 Grid detection: per-pixel colour edges between two *opaque* pixels only (keyed
  silhouette wanders ±1px and put peaks off-grid), local-peak + adaptive threshold (4× median diff),
  size = argmax of (best-phase share − 1/s) (fraction×s favoured multiples), confidence = best phase
  / mean other phases. Measured: real grids s=3..16 with noise 6/blur 1.2 score ≥14; smooth
  non-pixel art ≤3.9 → threshold 6. Not confident → fallback size from profile sprite height.
- 2026-11-20 Orphan cleanup only merges a lone pixel when its colour is close (Oklab < 0.1) to the
  surround, so deliberate 1px details (eyes) survive.
- 2026-11-20 Downscale voting: mode of 4-bit colour bins over the cell interior (outer ring skipped
  when size≥4), then mean of pixels within 20 RGB of the mode colour (bins can split one colour).
- 2026-11-20 .aseprite: own writer (header, color profile, old+new palette, 1 layer, zlib cels, tags; indexed reserves index 0 for transparency). Round-trip verified only with our own reader → still to verify with Unity's 2D Aseprite Importer (Unity MCP available).
- 2026-11-20 Sprite stacking (rigid props/vehicles: orthographic views → slices) — Ronan flagged it
  as worth having (ref: https://x.com/pebaryan/status/2123721685933433343). Stays parked per the
  kickoff; candidate for a phase after 3.
- 2026-11-20 Frozen detector measures frame diff inside the foreground bbox (threshold 1.5);
  whole-canvas diff flagged an in-place walk as frozen (0.575).
- 2026-11-20 Loop-point search uses the largest set count as minimum length so 12f and 24f share
  one range (12 → 24f set came out 13 frames).
- 2026-11-20 Palette size is a maximum: centroids closer than 0.04 Oklab merge (16 → 7 on the
  6-colour synthetic sprite).
- 2026-11-20 Phase 1 e2e green on synthetic clip (`spritewaffle run`). NOT yet accepted: needs a
  real H3 clip (generate via ComfyUI; templates not exported yet) and .aseprite check in Unity.
- 2026-11-20 First real H3 clip: anchor = H3 Image t2i 2048² (17.7 s), clip = H3 I2V 800², 56 f
  @24 fps, 20 steps, no turbo LoRA (66 s). Knight stayed pinned and marched in place. Grid not
  detectable on video → fallback to sprite_height 48 (pixel size 6). QA pass on 12f and 24f.
- 2026-11-20 H3 tints dark outline/shadow pixels green deep inside the sprite (e.g. (8,102,45),
  ≥9 px from the edge) → green entered the palette with edge-only despill. Added profile
  `despill: edge|all`; default stays `edge` (rule 11). `all` fixes the knight but would grey out
  deliberately green parts — default is Ronan's call.
- 2026-11-20 Ronan: despill default = `all` (profile + PixelParams). Characters with deliberate
  green parts set `despill: "edge"` in their profile. chroma.key() itself keeps edge-only default.
- 2026-11-20 .aseprite verified in Unity 6000.6.7f1 + 2D Aseprite Importer 6.0.0 (BriarBound,
  temp folder, removed after): 12f → 12 sprites + looping clip `walk_S` (~1.0 s), 24f → 24 sprites,
  same clip length; Point filter; per-sprite pivots resolve to one canvas foot line; console clean.
  Phase 1 acceptance items all met.
- 2026-11-20 Phase 2 step 1 (generation stages). facing_multiref = bundled H3 Image Edit template,
  prompt enhancer off, anchor in slot 1 + 2 optional ref LoadImages (unused optional slots are
  pruned from the API graph, not fed stale images).
- 2026-11-20 Measured: feeding a *generated* still back as a reference makes H3 Image Edit return a
  speckled-noise green background (keying then grabs it: height ratio 2–3×). Fix: every generated
  or imported still is keyed and re-composited on exact #00FF00 before save/reuse (rule 3).
- 2026-11-20 CONFLICT with kickoff rule 4 (diagonals from anchor + cardinals): with extra reference
  pictures H3 Image Edit copies the reference pose — SE came out as pure E, NE ≈ N. Using only the
  nearest cardinal (S/anchor for SE/SW, N for NE/NW) gives true three-quarter views (drift 0.14–0.21).
  Implemented `--diagonals nearest|multi`, default nearest pending Ronan's ruling.
- 2026-11-20 Knight run (jobs/knight/p2_002): 8 facings, all drift ≤0.21 colour, height within 2%,
  no mirroring needed. Anchor flagged asymmetric (plume) → mirrored facings would flip it.
