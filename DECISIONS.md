# SpriteWaffle decisions log

NEXT: Repo complete for a fresh install (setup doc, editor workflows, lock, agent install guide). Open: SAM 3 masks for non-green driving clips; Ronan to review the test-approved assets; hare other directions/actions if wanted.

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
- 2026-11-20 Ronan: wire TARA in as EXPERIMENTAL. Motion library = jobs/_library/motions/<name>/
  (clip.mp4 + motion.json, review -> approved; `spritewaffle motion add|approve|list`). Stage
  `transfer` (GPU; CLI `transfer`, `queue pipeline --motion`, MCP animate(motion=), UI source
  selector): approved facing = Picture 1, approved library clip = Video 1, 768², 8 steps, frames =
  largest 17n+5 within the clip; then the normal select→pixelize→QA→export. Every transfer reports
  identity_drift vs the facing and warns above 0.35 (same line as facing re-rolls).
- 2026-11-20 First library motion: walk_S_mannequin (from jobs/mannequin/m1). Real run on the goblin
  (jobs/goblin/20261120_115505, S walk): pipeline done end to end, QA pass 12f/24f, identity drift
  mean 0.37 / max 0.44 → warning raised as designed. Pixelized result reads as the goblin marching,
  skin darker/browner than the anchor. Anchor/facings/motion approvals in this run were test
  approvals by Claude, not Ronan's review.
- 2026-11-20 Bug: one full-suite run had the queue's QA task fail intermittently (and the commit
  went in anyway — my `pytest | tail && git commit` chain checked tail's exit code, not pytest's;
  use `set -o pipefail` / PIPESTATUS). Cause: on Windows os.replace onto a file another thread has
  open raises PermissionError; the worker's task-status update raced the scheduler's poll of the
  same task JSON. Fix: core/fsutil.py retries atomic writes and reads (50 × 20 ms); job.json and
  queue task files use it. Measured with the stress test: 182 PermissionErrors without retries, 0 with.
- 2026-11-20 Pixel-exact motion transfer (frames/flowtransfer.py, stage `flow`, CPU): the approved
  facing is pixelized once, then DIS optical flow (each driving frame -> frame 0, inside the chroma
  mask; extended outward from the subject) moves the facing's own pixels (nearest lookup). Output
  goes straight to the 04_pixel layout; selection runs on the driving clip; QA/export unchanged.
  SAM 3 not used: chroma-key masks suffice for green clips (non-green driving clips unsupported).
  Synthetic: silhouette IoU 1.000 every frame, colours exact (95% where legs cross).
- 2026-11-20 Two fixes from the real goblin run: (1) still-image grid detection locked onto a 29 px
  grid -> 19 px sprite vs 48 px H3 animations; flow now sizes the target from the profile's
  sprite_height_px like video actions (got 47 px). (2) using the driver's silhouette as the output
  mask clipped the goblin's club/ears to the mannequin outline; opacity now follows the target's own
  silhouette (regression test added).
  Result: goblin S walk from walk_S_mannequin, 7 s, QA pass 12f/24f, 16 colours all from the
  goblin's palette, green skin kept (TARA: brown, drift 0.37). Weak spots: feet smear on frames
  where legs cross; rigid props only follow the nearest body part.
- 2026-11-20 Character export (export/character.py; CLI export-character, MCP export_character):
  every QA-passed facing x action of a job in ONE .aseprite, a tag per action_facing, per-frame
  durations from each action's fps, merged exact palette (indexed; RGBA above 255 colours), plus an
  atlas PNG (row per animation) + JSON (rects, fps, loop, pivot, skipped). QA failures are skipped
  and listed. Knight (walk_E, walk_N, idle_S): 48 colours, indexed. Verified in Unity 6000.6 +
  Aseprite Importer 6.0.0: 36 sprites, clips idle_S 1.5 s / walk_E / walk_N ~1.0 s, all looping,
  an Animator Controller with one state per animation, no console warnings (test folder removed).
- 2026-11-20 Sprite stacking built (Ronan: "build sprite stacking"; was parked). spritewaffle/stack:
  `ortho` (GPU) = front is the approved prop anchor, back/right/top from image edits with explicit
  orientation text (right side: front points LEFT; top: front at the BOTTOM). `stack` (CPU) =
  pixelize the 4 views as ONE batch (shared palette + pixel size = front height / stack height),
  visual hull of front/right/top silhouettes (array maths, no mesh/renderer — rule "2D only" kept),
  voxel colour from the first view that sees it (top > front > back > right > left=mirrored right;
  hidden voxels get a fallback colour that never shows). Exports: slices strip bottom->top + JSON,
  16-step turntable GIF, 8-angle rotations sheet + JSON (for engines without a stacking runtime).
  Synthetic two-box car: occupancy exact from 3x-scaled views, face colours correct.
  Real run: treasure chest (jobs/chest/s1): 23 slices of 25x24, 10,559 voxels; 8 rotations read as
  one rigid chest (lock front, side at 45°, plain back). Anchor approval was a test approval.
- 2026-11-20 Sprite stacking wired into the queue (ortho = gpu, stack = cpu, submit_stack_pipeline),
  MCP (`stack` tool; status lists stack files and returns the rotation sheet as an image) and the web
  UI (Sprite stack section: 4 views, turntable, rotations, generate/rebuild with slice count).
  Verified from the browser pane on the chest: rebuild at 32 slices -> 34×34 px, 27,706 voxels, 3 s.
- 2026-11-20 Encoding bug: Python patch scripts on Windows read/write with cp1252 by default; one
  inserted a lone 0xB7 into index.html (invalid UTF-8 → broken '·' in TARA/flow badges). Repaired at
  byte level; a test now requires every source file to be valid UTF-8. Always pass encoding="utf-8".
- 2026-11-20 Audit (docs/AUDIT.md, Ronan: "audit ... clean up ... make it professional"). Code pass:
  paths.py (templates/profiles/jobs no longer depend on the current directory; SPRITEWAFFLE_HOME /
  SPRITEWAFFLE_JOBS override); CLI rewritten (grouped overview, help on every command and option,
  one-line errors + --debug, --version 0.2.0, profile list/show, doctor, animate, mirror, archive,
  queue retry/clear; stages use the job's profile unless --profile); dedupe (video.read_frames,
  Job.require_approved, one 04_pixel writer); mirror stage (W/NW/SW from E/NE/SE in code) and batch
  animate that mirrors when the partner is in the batch. Tests now get their own jobs folder
  (conftest) — the old e2e test had silently written jobs/dude into the real jobs folder.
- 2026-11-20 Audit pass 2 (UI): web app rebuilt — header with live ComfyUI/worker/queue status,
  searchable job list (newest first, cropped thumbnails, step progress), job header with profile
  selector + archive, step tabs (character: Anchor/Facings/Animations/Export; prop:
  Anchor/Sprite stack/Export), batch animate with a compass facing picker, compact result grids with
  a detail dialog (QA, re-render, re-process, add to motion library), Export tab with export-character
  and download links, queue drawer (filters, retry, cancel, clear), motion library dialog, toasts
  instead of alert(). Server: /api/status, settings, archive, export_character, motions, queue
  retry/clear, cropped images. Verified in the browser at 1440 px and 390 px; README added.
- 2026-11-20 AI prompt writer (Ronan: try qwen3vl_4b). templates/prompt_writer = CLIPLoader
  (qwen3vl_4b_bf16, type flux3) -> TextGenerateV2 -> PreviewAny; client.run_text. Per job
  inputs.prompt_writer = template|ai (default template). AI writes: anchor description from a short
  idea (strict), a canonical visual description read off the anchor, and per character + action
  motion/transition/sound (cached on the job so all facings share it; known actions keep their loop
  flag; new action names allowed). Every reply checked (JSON / plain sentence, word limits, banned
  phrases: camera, isometric, moving forward/across, turning, background); failed twice -> template.
  Measured gotchas: braces in the system prompt -> empty output (0/5 -> 6/6 without); an unpruned
  image node fed ComfyUI's example.png ("yellow outfit, pink club"); descriptions >~27 words in the
  action request -> empty output at every seed/budget (keep subject + held-items clauses); the 2048²
  green canvas hid the prop (club read as axe/staff) -> crop + enlarge the sprite first; text-only
  expansion is weak (robot dog -> humanoid robot), so it must keep every key word or it falls back.
  Side-by-side on the goblin (S): template walk vs AI walk both QA pass, AI walk swings the club in
  rhythm (modest gain); AI "cast spell" (impossible with templates) renders a club-raise + gem sparkle
  effect, QA pass. ~2 s per AI spec after the model is loaded.
- 2026-11-20 Art styles (Ronan: "gen in these styles and switch between them, maybe others later"):
  prompts/styles.py registry — pixel (pixelizer), painted / anime / comic (post "smooth": key +
  despill + specks + ONE scale per clip to profile height x4, premultiplied-alpha resize for soft
  edges without green fringe, cell x4, RGBA export, no palette check). Per job inputs.style; stages
  set the active style (context var) before building prompts; all "pixel-art" wording in the
  builder now comes from the style. Flow transfer and sprite stacking refuse non-pixel styles.
  Real run: one ranger description + seed 21 in all four styles -> four clearly different looks of
  the same character; painted S walk through the full pipeline: not frozen, scale 0.44, 256 px
  cells, QA pass 12f/24f (height CV 0.016), RGBA export.
- 2026-11-20 Own character sheets (Ronan: "remake this rabbit animated ... give it my own image").
  New sam3_mask template (CheckpointLoaderSimple sam3.1_multiplex_fp16 -> CLIPTextEncode
  "<subject>:N" -> SAM3_Detect union mask -> SaveImage). core/sheet_import: SAM 3 mask -> N figures
  left to right -> ONE scale, centred, common foot line at 45% of a 2048² #00FF00 canvas -> anchor
  (S) + facings; W/SW/NW mirrored when the partner exists. Colour keying the parchment was tried
  first and refused: beige bandages/paws match parchment (holes punched, parchment kept between the
  legs); SAM 3 cut the hare sheet cleanly in 5.4 s.
  Real run: "Hare Courier Four-View Model Sheet" (S, SE, E, N) -> NE/NW generated -> painted-style
  walks S + E (H3) + W (mirror): QA pass on all six sets (height CV 0.008–0.012), not frozen,
  character export hare.aseprite (RGBA, 3 tags). Approvals in this run were test approvals.
- 2026-11-20 Showcase GIF (Ronan: export a GIF that shows off walking, turning angles and actions): export/showcase.py — turnaround through the facing stills (2 turns), then per action a compass grid with every facing playing at once (missing facings shown standing, dimmed), one scale and foot line, pixel art nearest / others Lanczos, 255-colour GIF. Export tab button + preview, `spritewaffle showcase`, API /showcase, MCP showcase. Hare: 40 frames / 7.6 s at 512²; knight: 64 frames / 9.6 s.
- 2026-11-20 Repo completeness (Ronan: "make sure the repo contains everything they need including comfyui workflows"; "a simple, give this to your agent to install option"; "will it still work without you?").
  Confirmed: no Claude/Anthropic call anywhere in spritewaffle/ (grep); UI + CLI run everything, MCP optional — README now says so.
  Added comfyui/workflows/ (editor-format copies of all 9 API templates, laid out with comfy-draftsman; templates/ stays the source of truth), docs/COMFYUI_SETUP.md (every model file the templates load: folder, measured size, official HF URL from ComfyUI's own template package; required set ~94 GB; TARA LoRA from Alissonerdx/Minimax-H3-ComfyUI, BFSNodes only for TARA), AGENT_INSTALL.md (paste-to-agent install; agent must ask before downloading models), requirements-lock.txt (pip freeze of the tested venv), SPRITEWAFFLE_COMFY env for the ComfyUI address (was hardcoded 127.0.0.1:8188 in four places). doctor's missing-model failures now point to the setup doc.
  Refuses now: tests/test_repo_complete.py fails if a template lacks an editor copy, a model isn't in the setup doc, a runtime dep isn't locked, or the README stops linking the guides.
- 2026-11-20 Install docs assume a stranger's computer (Ronan: "dont use my setup for install assume user isnt my computer"): README clones from GitHub instead of `cd F:\...`, MCP path is a placeholder, hardware stated as tested-on not required, Stability Matrix is one example of where models may live, AGENT_INSTALL tells the agent to assume nothing and notes the repo is private. Test refuses drive paths in the install docs. Clean clone + lock install + 131 tests verified on this machine; a machine with no models was not available to test.
- 2026-11-20 Quick fixes from the fresh-eyes audit (Ronan: "Quick bugs first"). UI: typed anchor description / import path / sheet path are kept across polls only within the same job (was: carried into the next job opened, so "Generate anchor" could render the previous character). CLI: only anchor, sheet-import and extract create a job; any other command with an unknown --job fails with "no such job" plus close matches (was: silently created an empty job). Export: tags carry Aseprite's repeat count, 1 for non-cyclic actions (attack, jump, ...), 0 = loop for idle/walk/run/march; reader exposes `repeats` (Unity behaviour with repeat=1 not yet checked in an editor). Queue API: filter on the server before the limit, running tasks first (was: newest 60 then filtered in the browser, hiding the running task and older failures). `profile show default` works; asymmetric-anchor warning is a sentence, not a dict; README MCP path tab and style/writer syntax fixed.
  Real run: chest->goblin->knight switch in the UI with unsaved text: text stays on chest across polls, other jobs show their own; `export-character --job knight/p2_02` -> "no such job ... did you mean knight/p2_002"; export of a copy of hare/courier: 30 tags, attack_* play once, rest loop.
- 2026-11-20 One palette + one pivot per character (Ronan: "Palette + pivot"; audit findings 3, 4).
  Palette: core/job_palette.py. Order: profile hex list > 04_pixel/palette.json (file or built) >
  built from anchor + all facing stills at the profile's sprite height > locked from the first clip
  (job with no stills). pixelize and flow use it; QA's colour cap is the job palette size; the
  character .aseprite keeps the job palette's order. `spritewaffle palette` (show / --file .gpl .hex
  .png / --rebuild / --unlock / --apply) and Animations -> Palette (swatches, stale clips, Apply);
  Queue.submit_reprocess re-runs pixelize/flow -> qa -> export, mirrors after their source.
  Real run (copy of knight/p2_002): built from 9 stills in 6.7 s; walk E / walk N / idle S shared
  0 colours before, 15-16 after; union 48 -> 16; visual check: same blue/plume red in all facings,
  detail kept. PICO-8 .gpl loaded + applied (12 tasks done): mechanically right, but skin maps to
  orange (nearest Oklab: ffccaa 0.069 vs ffa300 0.087 on the stills; video skin is warmer) — a
  loaded palette must suit the character; documented.
  Pivot: layout.preserve_canvas puts the feet (median over frames of the bottom-12% band's
  midpoint, airborne frames skipped) on the cell centre line instead of centring the union bbox;
  Placement.pivot recorded in placements.json; exports read it; .aseprite gets a "pivot" slice
  (chunk 0x2022, keys only where it changes); atlas JSON has a character-level pivot/pivot_norm when
  all agree. Too-wide actions are shifted only enough to fit, the pivot records the feet, and QA
  warns. Real run: knight copy -> all 4 animations [32, 63], one slice key; orc copy (painted, 40
  clips) -> 36 at [128, 255], attack S 117 (axe swing fills the cell), SE 127, SW 129.
  Seen, not fixed: in the orc's S attack clip the orc is drawn much larger than in idle and the axe
  is cut off at the top — a clip scale issue, present before this change.
- 2026-11-20 Re-applied palette + pivot to all 8 pixel-art jobs (Ronan: "Yes, all pixel jobs"). Backup of their 04_pixel/05_qa/06_export first: jobs/_backup/2026-11-20_pre_palette_pivot (24 MB; copy back to undo). knight/h3_002 named a profile `knight_test` that no longer exists; same 64 px cell / 16 colours as the built-in default, so it was re-applied with `--profile default`. Result: 14 clips, all in their job palette, sizes and grids unchanged (h48, same widths); knight/p2_002 character export 48 -> 16 colours, one pivot [32, 63], showcase rebuilt. One regression found and fixed: goblin/cmp_ai "cast spell" S went QA pass -> fail ("sprite touches cell border") because the clamp for a too-wide action let it reach the cell edge; the clamp now keeps a 1 px margin -> pass, feet 4 px right of centre, with the QA warning. Painted jobs (hare, orc, ranger painted) were not touched: they have no palette and their old layout stays until re-processed.
- 2026-11-20 Fixes group from Ronan's notes (docs/BACKLOG.md A). (15) Enlarged images open in an in-page viewer (<dialog>: Esc, Close, click outside; clips play in it) instead of target=_blank, which left a bare image tab with no way back. (14) core/takes.py: before the anchor, a facing (incl. drift auto-mirror and sheet import) or an action's raw.mp4 is overwritten, the old file goes to takes/ with its provenance (seed, prompt); identical takes are not duplicated; "Use this" restores one (current one becomes a take), puts the stage back to review, and a restored clip is re-extracted -> select -> pixelize -> qa -> export through the queue. Restore writes a fresh mtime: with copy2 the old mtime made the UI keep the cached thumbnail (seen in the real run, fixed, tested). (6) /api/status lists running tasks; header pill: "Working: <character> · <stage> <action> <facing> · m:ss". (4) GPU tasks that fail with anything but bad input (ValueError, KeyError, FileNotFound, Permission) are re-queued once without their seed (new seed), same task id so dependents keep waiting; error notes the attempt. Real run: throwaway job takestest/t1 — a bad-arg anchor failed at once with no retry; anchors seed 11 then 12 -> seed 11 kept as a take; header showed "Working: takestest · anchor · 0:08"; restore via UI swapped the image and set anchor to review; job archived afterwards.
- 2026-11-20 Prompt access (backlog #1). Job header "Prompts…" opens a dialog: per anchor / facing / action the full prompt that will be sent ("Will send") and the one sent last time ("Last sent", from provenance). Editable: a note for all facings and per facing (builder.facing(note=...) inserts it before the framing rules), and each action's motion / transition / sound (job inputs action_overrides; resolve_action_spec: edited > AI cache > preset; partial edits merge with the preset; a new action name needs motion + transition). Fixed rules (#00FF00, framing, in place, style) are built around the text and can't be edited away. The dialog never runs the AI writer (shows "preset (AI text is written at render time)"). Overrides live on the job, so CLI/MCP renders use them too. Real run: throwaway job prompttest/p1 (monk), facing E with note "he holds a lit paper lantern in his front hand" -> rendered E holds a lit paper lantern on flat green; "Last sent" contains the note; walk motion edited and reset through the dialog. Job archived.
