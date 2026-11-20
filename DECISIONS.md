# SpriteWaffle decisions log

NEXT: Mannequin-driven TARA keeps identity (drift 0.35 at 768) but is borderline. Ronan to choose: wire TARA in as an experimental motion-library stage, or park.

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
  Implemented `--diagonals nearest|multi`. Ronan 2026-11-20: default = nearest (ruling, overrides rule 4).
- 2026-11-20 Knight run (jobs/knight/p2_002): 8 facings, all drift ≤0.21 colour, height within 2%,
  no mirroring needed. Anchor flagged asymmetric (plume) → mirrored facings would flip it.
- 2026-11-20 Phase 2 step 2 (actions). Templates: h3_action_fl2va = i2v graph + LoadImage on
  MiniMaxH3ImageToVideo.last_frame; transition_pose / bridge_frame = facing edit graph as own slots.
  H3 video prompts follow the H3 guide structure (alignment line + integrated_multimodal_description /
  overall_soundscape / non_diegetic_music) with a short literal body (rule 6).
- 2026-11-20 Knight E walk (jobs/knight/p2_002): transition pose = clear first step; FL2VA with the
  transition as first AND last frame was NOT frozen (mean diff 8.36) → no I2V fallback needed;
  56 frames, QA pass 12f/24f, seam 0.068, height CV 0.016.
- 2026-11-20 Bridge frames: H3 Image Edit with two poses copies Picture 2 (same pose-copying as
  multi-ref diagonals). Default bridge = 1 s FL2VA clip A→B, middle frame kept (a true in-between,
  measured on idle→transition). Image-edit bridge kept as --method image.
- 2026-11-20 Phase 2 step 3 (job queue): tasks = JSON files in jobs/_queue/, one worker (lock
  file; --force takes over a stale one; 'running' tasks re-queued on start), pools gpu=1 / cpu=2,
  `after` chains (failed/cancelled dependency → dependents fail as blocked). job.json writes are
  serialized per job + atomic replace (6 threads × 80 writes: none lost). Queue tasks always pass
  facing/action explicitly — job.json "inputs" is only a CLI convenience and races under the queue.
- 2026-11-20 Real queue run on knight: 14 tasks (N walk + S idle full pipelines, E walk re-process).
  GPU strictly serial (N 2m09s, then S idle 4m00s); CPU chains ran during GPU renders; all QA pass.
  S idle FL2VA (facing as first+last frame, no transition) NOT frozen (diff 4.36).
- 2026-11-20 Phase 2 step 4 (web UI): `spritewaffle ui` = FastAPI on 127.0.0.1:8765 + one static
  page; runs the queue Worker in-process (takes over the worker lock). JSON-only POSTs, files served
  only from inside jobs/. Job page: anchor (generate/import/approve), 8 facings with drift +
  per-facing re-roll + approve, actions (transition, 12f/24f GIF + QA errors/warnings/re-roll
  target, source contact sheet, re-roll clip / re-process). Re-rolling a stage resets its approval.
- 2026-11-20 Verified in the browser pane on knight/p2_002: re-process E walk (4 CPU tasks, 9 s) and
  re-roll SW facing (GPU, 27 s, drift 0.141 → 0.106), then approve — all from the page.
  Bug found + fixed: Windows time_ns ties made same-millisecond tasks list out of order → queue seq
  is now strictly increasing.
- 2026-11-20 Phase 3 step 1: MCP server (`spritewaffle mcp --root <repo>`, stdio) with tools
  generate (anchor|facings), animate (action pipeline), status (wait + images), approve (relay the
  human's yes only). Agent skill in skill/spritewaffle/SKILL.md. Asset-type presets (character,
  creature, prop) and hero style_ref (approved hero anchor -> edit template).
- 2026-11-20 Deps: mcp 1.9.4 needs a pinned set — starlette 0.41.3 (fastapi 0.115.5), pydantic
  2.10.6, sse-starlette 2.1.3; `pip check` clean. FastMCP 1.9 can't read string annotations, so
  mcp_server.py has no `from __future__ import annotations`.
- 2026-11-20 Worker lock: stale holder (dead pid) is now taken over automatically (Windows check via
  OpenProcess/GetExitCodeProcess — os.kill(pid, 0) would terminate the process on Windows).
- 2026-11-20 Gotcha found in the real run: a long-running worker (web UI) keeps running the code it
  was started with — a task queued via MCP was rendered by the UI's stale worker and silently
  ignored style_ref. Restart `spritewaffle ui` / `worker` after updating SpriteWaffle.
- 2026-11-20 Real stdio MCP run: goblin creature with style_ref=knight/p2_002 → anchor in review,
  provenance records style_ref. Effect of style_ref vs prompt-only is modest on this pair (both
  already share the chunky style); not proven useful yet.
- 2026-11-20 OPEN: "H3 TARA" (motion library, Phase 3) — no node class matching "tara" on the live
  ComfyUI (2777 nodes). Needs Ronan: what TARA is / where it comes from.
- 2026-11-20 TARA researched (Ronan didn't know it). TARA = "Temporally Aligned Reference
  Attention", a COMMUNITY motion-transfer method for MiniMax H3 by Alissonerdx (not an official
  MiniMax release): driving video stays a native <Video 1> reference in H3 Reference-to-Video and a
  temporal attention bias makes each output frame follow the matching source frame; reference
  pictures supply the identity. Experimental, not peer reviewed; no statement about pixel art /
  stylized content. Model card: https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI
  Local status: node BFSMiniMaxH3NativeTemporal (ComfyUI-BFSNodes) INSTALLED, ref2va UNET installed,
  VideoHelperSuite installed. MISSING: LoRA minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors
  (126 MB) and the example workflow minimax_h3_motion_transfer_tara_workflow_native_nodes_v1.0.json
  (299 kB); the recommended DMD ref2va 8-step turbo LoRA is not installed (a 4-step ref2v turbo is).
  License of the TARA LoRA: "BFS Motion Transfer Community License 1.0" — personal and commercial
  use allowed; no reselling the weights, no hosting them as an API/SaaS; attribution only above
  US$1M revenue. My "tara" search missed it because the class name says NativeTemporal.
  Fit for SpriteWaffle: a motion library = a few approved driving clips (walk, run, attack) reused
  across the whole cast, so timing matches between characters. Unproven on pixel art.
- 2026-11-20 Ronan OK'd the TARA download. Installed: F:\Stability Matrix\Models\Lora\MiniMax H3\
  minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors (126,417,912 B; valid safetensors, 416 BF16
  tensors, metadata has native_temporal_attention); ComfyUI lists it. Example workflow kept as data in
  samples/downloads/tara/ (gitignored). Validation on this install: SetNode/GetNode are KJNodes
  frontend-only (expected, not real errors); real gaps = `minimax/` path prefixes on CLIP + 2 VAEs,
  DMD ref2va 8-step turbo LoRA missing (have 4-step ref2v turbo), SolAttnPatch node missing,
  second-pass upscaler models + LMS LoRA missing (pass not needed for sprites -> bypass).
- 2026-11-20 TARA test (templates/h3_tara_transfer.json, flat 23-node graph: ref2va + SigmaShift 12/3
  + 4-step ref2v turbo (stand-in for missing DMD 8-step) + TARA LoRA + BFSMiniMaxH3NativeTemporal,
  MiniMaxH3ReferenceToVideo with goblin anchor as Picture 1 and knight front march as Video 1).
  Windows: attention_backend 'flash partitions' fails (no flash SDPA in this torch build), 'flex'
  needs triton; 'comfy kitchen (experimental)' WORKS on the 4090.
  Results (56 frames): 4 steps/544² 24 s, timing corr 0.81 vs guide, goblin kept but green skin
  -> brown and soft pixels; 8 steps/544² 35 s, corr 0.68, same; 8 steps/768² 62 s, corr 0.61 and
  the output is the KNIGHT (driving-clip identity replaced the reference).
  Verdict: timing transfer works; identity binding is not reliable enough for sprites -> TARA NOT
  wired into the pipeline. Template kept (validates) for further experiments. Untested idea: an
  identity-neutral driving clip (plain grey mannequin) so there is no competing identity to leak.
- 2026-11-20 TARA with an identity-neutral driving clip (Ronan: "try mannequin"). Mannequin =
  jobs/mannequin/m1 (plain grey featureless chibi figure, anchor seed 9; S walk FL2VA seed 11, 56 f,
  not frozen; it half-turns sideways in frames 3–7, 32–34, 44–47 — a library clip would need a
  re-roll). Goblin via TARA, colour drift vs goblin anchor (facing-drift metric) / timing corr:
    knight-driven    4 st 544²: 0.46 / 0.81     mannequin-driven 4 st 544²: 0.39 / 0.75
    knight-driven    8 st 768²: 0.62 / 0.61 (became the knight)
    mannequin-driven 8 st 768²: 0.35 / 0.57 (goblin kept, olive skin back, crispest of all)
  Verdict: a neutral driving clip removes the identity takeover; best result sits on the facing
  re-roll line (0.35) and timing is weaker at 768². Promising, not proven: still not wired in.
