# SpriteWaffle decisions log

NEXT: Phase 1 build in progress (see git log for done steps).

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
