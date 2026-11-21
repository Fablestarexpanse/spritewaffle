NEXT: (2026-11-21, handoff to GPT/local agents) All work committed + pushed; tests 221 pass. Start with AGENTS.md and docs/wiki/Home.md. Open items: docs/wiki/Roadmap.md (directional >8 views + depth/normal generation, style sets, motion library, effects polish, UI P3).

# SpriteWaffle decisions log

NEXT: (2026-11-21) Built + real-run: variants, sprite stack viewer/GIFs, effects section, animals (turnaround sheet), effects on characters + throws. Open (docs/BACKLOG.md): TRELLIS 2 real-3D stacks (pine showed the carve's limits), paper-doll: item jobs + fit built (red_cape/c1 on knight -> p2_002_red_cape2; no layer extraction, Ronan); base_body type + item export built (human/body2 + red cape, all 8 views clean); open: N trim detail on the knight, NW ornament, ground-flat auras, slash preset, QA-fail auto re-roll. Test jobs to review/archive: angletest/*, cat/tabby, knight/caped, knight/gold_armor, knight/gold_ref, pine/p1, lightning, magic_circle, shield_spin, slash, smoke_puff.

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
- 2026-11-20 Cell / sprite size settings (backlog #10, #12). Job header "Sizes…": edit a profile (cell size, sprite height, palette size, outline, camera angle, directions, mirroring, fps per action), see which jobs use it, save, or save a copy and switch this job to it, then "Re-process this job's clips" (no rendering). The built-in default can't be overwritten, only copied. GameProfile now refuses sizes that can't work (height > cell - 2, palette outside 2-256, fps outside 1-60). Fixed in passing: choosing "default" in the job's Profile picker sent null, which update_inputs ignored, so a job could never go back to the default. Fit warnings: a clip too wide to centre the feet, or too tall for the cell (top cut off — this was silent before; found in goblin cast spell, 2 px, and in most painted hare/orc jumps, 26-79 px of a 256 px cell, which QA had failed as "touches cell border" so they were never exported) now name the profile cell size that fits, per frame set (12f/24f can differ). Real run: copy of goblin/cmp_ai -> Sizes… -> copy of default with a 72 px cell -> re-process 2 clips: cast spell no longer cut off (paste y 6), QA pass; its 24f set still 4 px off centre and the warning names 80 px. Test job archived, test profile removed.
- 2026-11-20 Painted hare + orc re-sized so nothing is cut off (Ronan: "Move forward" on "Fix hare and orc"). Measured on scratch copies laid out at a 128 cell: the hare needs a 96 px profile cell (384 px at x4) for every clip; the orc needs 112 only for its E/W axe attacks (swing 313 px wide), 96 for everything else. Chose one shared profile painted96 (cell 96, sprite height 48): at 112 the orc atlas would be ~18000 px tall. Backup first: jobs/_backup/2026-11-20_pre_cell96 (469 MB). Re-processed from frames (240 tasks, no renders). Result: QA hare 30 -> 40/40 pass, orc 27 -> 40/40 pass, no clipped placements; orc E/W attack 12f/24f feet 16-19 px off centre with the fit warning (112 px). Hare character export now has all 40 animations (last export had 3), one pivot [192, 383]; showcase rebuilt (136 frames, 15.6 s), jump grid shows whole hares. Found: the atlas PNG is 4608x15360, past Unity's 8192 limit -> backlog #16 (pages/trim); the .aseprite is fine. profiles/*.json are now git-ignored (personal game profiles stay local).
- 2026-11-20 Atlas pages (backlog #16, audit "missing": atlas max size, trim, mirror dedupe). export/atlas.py: frames trimmed to their pixels (offset kept so the cell-space pivot holds), identical frames stored once, shelf-packed tallest-first into pages <= max_size (default 4096; UI 2048/4096/8192; --max-size). mirror="flip" leaves W/NW/SW out when they are pixel-exact flips of E/NE/SE (checked, never assumed) and lists them with flip_x_of. Output: <char>_atlas_N.png + a TexturePacker JSON-hash per page (frames, animations, pivot, related_multi_packs) + <char>_atlas.json (ours: pages, per-animation fps/loop/pivot/frames_atlas). The old single-sheet <char>_atlas.png is removed on re-export. Real run: hare (40 painted animations, 384 px cells) 4608x15360 (70.8 Mpx, past Unity's 8192) -> one 4091x2183 page (8.9 Mpx), with flip 4085x1777 (9 animations flipped); all 480 frames rebuild from the pages with identical alpha and visible pixels (37 differ only in RGB under alpha 0, which trimming drops). Knight: one 1031x52 page; walk_W detected as an exact mirror. Both left exported in the default pack mode.
- 2026-11-20 Job list sorting (backlog #7). Sidebar: sort (recent / name / least done / most done), filter by type and style (built from the jobs present), "Needs me" (approval gates waiting — anchor, facings, prop views — or a clip that failed QA; clip "review" is not a gate, so it is ignored: counting it flagged nearly every job), group by character (collapsible, with counts). Choices remembered per browser (localStorage, wrapped in try/catch). The list now redraws only when what it shows changes (audit: a poll re-render moved jobs under the cursor) — checked: same DOM node after a 5 s poll. Real check: 22 jobs; name sort, painted filter (hare, orc, ranger), Needs me (6 jobs waiting on anchor/facings/ortho approval), 9 character groups; phone width wraps cleanly. Filters left at defaults.
- 2026-11-20 Game angles (backlog #5), anchors. Same knight description + seed under profiles with projection topdown_34 / iso_2to1. v1 (only STYLE said "for a top-down 3/4 game" / "2:1 isometric game"): eye-level camera, the knight turned three-quarters right — the front anchor came out as an SE-like view, not top-down. v2 (+ camera sentence): slightly higher, still turned. v3 (dropped the trigger words "3/4" and "isometric"; "top-down RPG" / "tactics game seen from above"): seed 21 front-facing with a raised camera, seed 7 clearly from above but turned diagonally (2/4 front). v4 (+ "only the camera is raised: chest and face point straight down the screen toward us, both shoulders equally visible"): 6/6 front-facing with a clearly raised camera on seeds 3/7/21; top-down ~45 deg reads steeper than iso ~30 deg. builder.CAMERA holds the sentences (anchor only — always the front view); facings, transitions and clips say "same camera angle as Picture 1".
- 2026-11-20 Game angles, facings + clips. With the v4 anchors (seed 21), 8 facings under a raised camera: (a) side-view facing words -> N fine, E/W an eye-level profile, every diagonal a copy of its reference; (b) screen-direction words ("toward the lower-right corner") -> nothing rotated; (c) side-view words + "still seen from the same high camera above, looking down on the top of the head" -> N and E/W turn (E keeps more height), diagonals still copies, iso W copied S. Conclusion: H3 Image edit turns a raised-camera character in 90 degree steps, not 45. Kept (c) as VIEW_RAISED. Walk clips (S, E rendered; W mirrored) under both cameras: QA pass, not frozen, the camera stays raised through the clip. Recommendation for top-down/iso: 4 directions, W mirrored from E — the facings step now warns when a raised-camera profile asks for 8.
  New check, all projections: generate.turned_from = mean RGB difference of facing vs the picture it was drawn from (sprites cropped + scaled to 64x96). Copies score 7-13, real turns 22-86 across hare, orc, knight p2_001/p2_002; threshold 15 -> "X looks like a copy of Y: it didn't turn; re-roll it". It also catches an old one: knight/p2_002 NW is a near-copy of N (7.3; visually confirmed). Drift (colour histogram) could not see this.
  Fixed: Facings tab only enabled Approve at 8/8, so a 4-direction profile could never be approved; the job payload now has `directions`, the tab counts 4/4 and greys unused diagonals. Real run: angletest/top on a 4-direction top-down profile -> S, E, N, W all turned (72-84), Approve enabled. Test jobs angletest/side|top|iso kept for Ronan to look at; profiles test_topdown_34 (now 4 directions) and test_iso_2to1 are local.
- 2026-11-20 Character variants (backlog #9/#3: "edit model to make changes", "adding items, clothing"). core/variant.py: "Make a variant…" (job header, needs approved facings) -> new job <base>_<slug> linked by inputs.base_job + edit. Anchor = base anchor edited with the change (facing_multiref, one picture). Facings = each BASE facing edited with the change in words (one picture), so poses line up with the base; generate.facings routes variants there; the queue's anchor stage re-rolls the edited anchor. Measured: v1 gave the edited front anchor as Picture 2 -> all 7 facings came out as that front view (the "changed vs base" metric could not see it: 45-73); v2 one picture -> every facing kept its base pose with the cape and shield correctly placed from each side (back views: cape behind, shield on the correct arm). Variant facings now also run turned_from against the variant's own anchor (front-view copies < 15 -> warning). Real run: knight/p2_002 + "add a long green cape and a round wooden shield on the left arm" -> knight/caped, anchor exact (same face/pose/colours), facings vs front 42-60, no warnings.
- 2026-11-20 Sprite stacks (Ronan: "no easy way to select it", "spin the final object on my own", "gif of it", "gif showing the stacks stacking then spinning"). Sprite stack tab: in-browser viewer drawing the real slices (drag to turn, spin + speed, tilt = camera angle, layer spacing, zoom, replay build-up; settings remembered); stack/gifs.py: spin GIF and build-up GIF (slices land one by one, ~2.4 s whatever the height, hold, one full turn), using the viewer's tilt/spacing/zoom; API /stack_gif. Findable: home page "New sprite stack" + "New character", type shown as "prop — sprite stack". Real run on chest/s1 (32 slices): viewer spins and replays (canvas half filled mid-build, full after), both GIFs made from the UI (build 64 frames 5.2 s at tilt 0.6).
  Research for the animation section written to docs/RESEARCH_ANIMATION.md (effects on black + additive/brightness alpha, Wan-Alpha RGBA video (not installed), SAM 3 video tracking for thrown objects (installed), quadruped presets, TRELLIS 2 / Pixal3D image-to-3D for real-3D stacks (installed)).
- 2026-11-20 Organic sprite stack test (Ronan: "try something organic like a tall pine tree"). pine/p1 (prop): anchor "dark green needles" came out near-black -> re-rolled with "rich mid-green needles with lighter green highlights" (seed 11) -> readable tiers. 4 ortho views consistent (top = radial star of branches). Stack 48 requested -> 47 slices, 33x33, 12766 voxels. Result: works mechanically, but the outline carve makes a solid cone coloured from the views: the tiered, overhanging branches become speckle, and the lowest drooping branches make the bottom slices a wide disc. Reads best at layer spacing 2 / tilt 0.6 (tall pine, trunk visible); squat at spacing 1, a blob straight down. Evidence for the TRELLIS 2 / Pixal3D path (real 3D keeps overhangs and gaps). GIFs at spacing 2 sent to Ronan.
- 2026-11-20 Effects section (Ronan: "Effects section first"). Prototype first: H3 Image still + H3 i2v on pure black. Found: the i2v "frames" param is a frame count (passing 2.0 gave 5 frames); with 48 frames, background stays black (border p99.9 = 0) and effects read well: fireball swirls (loop), explosion goes spark -> burst -> smoke -> empty (one-shot, after adding a "start small" framing — the 45%-height rule had made the spark a full explosion), healing sparkles twinkle. Dark smoke can't be separated from black (additive hides it, brightness alpha makes it clear) -> a green-background option for smoky effects. core/effect.py: render (still + clip, takes kept) on GPU; process on CPU: luma key (soft for smooth styles, un-premultiplied; hard for pixel art) or green key, frame pick (one-shot = first..last visible frame; loop = skip the first 1/6, best-matching window of at least 24 source frames — a 12-frame window on the magic circle looked static), one scale so the largest frame fits `size`, pixelize (palette N) or smooth; export strip, frames, square flipbook sheet, .aseprite (repeat 1 for one-shots), preview GIF, JSON. prompts/effects.py presets: fireball, explosion, magic circle, healing, slash, lightning (lightning reworded after it drew an icon-like bolt -> now thin forked strikes). UI: Effect tab (presets, settings, render / re-process, previews, files); home "New effect". Real runs through the app: lightning (after rewording: forked strikes flickering, 12 frames 36x70), magic circle (12 frames 64x63, loop over 28 source frames, runes turning). Offline: fireball/explosion/healing pixel + painted fireball.
- 2026-11-21 Four-legged animals (Ronan: "a cat doing something"; "All of it"). New asset type `animal` with its own presets (idle, walk = diagonal-pair gait, run = gallop, pounce, sit, sleep, jump); builder.actions_for(type). Measured: the gait words work (cat walks on four legs in S and E). Facings: H3 Image edit would not turn the cat away from its three-quarter anchor — all 7 facings copies (turned_from 6-13, caught by the check); animal body-orientation words ("the whole body in profile from nose to tail") changed nothing. A turnaround sheet drawn in one go (5 views in a row: front, side right, back, 3/4 front right, 3/4 back right) turns correctly and keeps the design; the anchor step for animals now draws that sheet and cuts it with SAM 3 (sheet_import) -> anchor + facings, W/SW/NW mirrored; generate.facings for animals asks for a sheet re-roll instead. Real run cat/tabby (seed 21): all 8 directions right; walk S/E/W rendered; E/W failed QA at a 64 px cell (side-on cat with tail 77 px wide) -> profile animal96 (cell 96, height 48) -> all pass.
  Fixed on the way: (1) a clip's loop flag came from a fixed list (idle/walk/run/march) and ignored the action's own spec (edited / AI / animal presets like sleep) — select() now reads action_report spec.cyclic. (2) A sprite wider than the whole cell (cut off at the sides) raised no warning — it now says how much is cut and which cell fits.
- 2026-11-21 Effects on characters + throws (Ronan: "All of it"). core/attach.py: one effect per animation (facing+action): effect job, start frame, point, front/behind, spawn or projectile (speed px/frame toward the facing). Export: per-clip and character JSON events (frame, point, layer, kind, velocity, effect fps) + the effect's export folder copied to 06_export/character/effects/; combined preview GIF (canvas grows for the effect / projectile path). UI: the animation window's Effect section (frame scrubber, click to set the point). Throws: actions can now end anywhere (spec end=free -> I2V, no last frame) — measured: "throw shield" with FL2VA ended with the shield back on the arm from frame 6; with end=free the knight holds it in frames 0-3, releases at 4, stands without it after. Spinning shield as an effect: H3 drew it on black despite the green wording, once as a green card on a black frame -> effect.detect_bg reads the clip's border (black / green / black+green, keys accordingly; refuses anything else); still_green wording for objects. Real runs: knight/caped throw shield E + shield_spin projectile from frame 4 at (50,40), 5 px/frame -> shield spins away right; magic circle behind knight idle S as an aura (then removed again from Ronan's knight); attach editor clicked through in the browser; export-character of knight/caped carries the event and the shield files. Other effects: slash preset came out as a crescent turning into a crosshair flash (usable as an impact, not a slash); smoke puff on green kept its greys (grows into a ring, disperses).
- 2026-11-21 Sprite stacks from real 3D (TRELLIS.2, installed locally). Pruned the bundled "Pixal3D & TRELLIS.2" template to the vertex-colour branch (TRELLIS.2 only: Pixal3D needs MoGe, not installed, and ComfyUI validates every reachable node even behind a switch) -> templates/trellis_mesh (+ editor copy, models in COMFYUI_SETUP). Measured: (1) fed the flat pixel-art pine anchor, TRELLIS built a flat card (depth +-0.0008) -> the anchor is first redrawn as a lit 3D render (H3 Image edit, 3/4 from above) -> full volume. (2) glTF vertex colours are linear; read as sRGB the pine came out near-black -> converted. (3) stack/mesh3d.py: numpy GLB reader, area-weighted surface sampling to a grid `height` voxels tall, outside flood fill, interior colour from the voxel above, palette fit (or the job/profile palette). (4) TRELLIS OOM'd (22.7 GB held after H3 Image) -> ComfyClient.free() before it, and upsample 1536 -> 1024 (a stack needs ~48 voxels). The auto-retry recovered the OOM'd run on its own. Default stack method is now "3d"; "carve" stays as an option. Real run: pine 48 slices 36x36 (branch tiers, slim trunk, silhouette changes with angle — vs the carve's speckled cone), chest 32 slices 34x29 (lock on the front, lid arch seen from the sides). 3D model ~1.5 min per prop.
- 2026-11-21 Item from a picture (Ronan: "show it an image of a generated item and it add it, like new armor"). Measured with a generated golden breastplate on knight/p2_002: (1) item picture as Picture 2 of the anchor edit -> the output was just the armor, no knight; (2) base facing + item picture -> E huge armor with a tiny knight, N armor only; (3) the item in words -> added correctly. So: writer.describe_item (Qwen3-VL 4B, one sentence, 5.6 s) -> variant.item_edit ("wearing this" -> "wearing a golden breastplate featuring a central red gemstone, ...") -> the normal variant route; the picture is kept (01_anchor/item.png) and shown on the Anchor tab. Back views put the gem on the back even when told front details are hidden -> back facings get variant.item_core ("a golden breastplate") -> plain gold back plates. Real run through the UI: knight/gold_armor, all 8 facings correct, no warnings. Bug found: a patch wrote `` as a backspace (0x08) into item_core's regex -> fixed, scanned the repo (none left), memory updated.
- 2026-11-21 Item picture as a real reference (Ronan: "use armor as reference but your edit terminology for prompt might be wrong"). H3 Image edit's own enhancer (templates/facing_multiref.json node 39) expects a Subject caption: "X in <Picture N> is <Subject N>." definitions, then "The target image shows…" with one relationship per Subject (fully / partially preserved, attribute transfer), then the changed details. Measured on knight/p2_002, seed 7: (a) Subject caption, raw 1024px armor picture as <Picture 2> -> E correct, S and N "armor huge, tiny knight inside" (the item picture read as the canvas); (b) same caption + the armor shrunk to ~35% on a light grey card + a <Subject 3> "flat green background, framing and camera of <Picture 1>, fully preserved" + "its grey backdrop and its size in <Picture 2> are not used" -> S knight at normal scale wearing the exact breastplate (gem, shoulder guards), N plain gold back plate, no gem. The reference keeps the item's real design; the words-only route (previous entry) only keeps what the 30-word description says. Variants with an item now use (b).
  Real run through variant.create/anchor/facings (seed 7): knight/p2_002 + scratchpad armor -> knight/gold_ref, all 8 facings wear the referenced breastplate in the base pose, back views plain gold, 0 warnings. Base jobs without a stored description get one from writer.describe(image=anchor) (stored as inputs.character_description): the caption needs the character named in words.
- 2026-11-21 Equipment layers, step 1 (paper-doll; Ronan: armor "modelled to the player's base model", "show back and front of clothing"). core/layer.py: item layer = the variant's pixels that differ from the base, per facing, written by variant.facings to 02_facings/layers/<f>.png (transparent, same canvas). Works because variants keep the base pose/position (bboxes within 2 px). Measured on knight/gold_ref (breastplate) and knight/caped (cape + shield), all 8 facings: RGB max-channel > 60 lost a band of the dark cape over the dark belt in back views -> CIELAB delta E > 25 keeps the whole cape and the armor (18 and below pick up tunic redraw noise); specks < 400 px dropped; enclosed holes filled. "Body moved" check = % of base body the variant no longer covers: real 0.01-0.82 %, base shifted 4 px 1.83 % -> warn at 1.5 %. Known: a few blue fringe pixels at the armor's side edge (E); front views of a cape give only its visible edges (correct: that is all of it you see). Not done yet: layers for animation frames, per-slot export, base body without the tunic.
- 2026-11-21 Ronan's ruling on equipment: items are their own jobs, generated separately and kept as originals (icon/drop sprite). Each item has a FRONT and a BACK picture (back made from the front with the edit model). "Fit on character" puts the item onto any base character (different races/bodies are just different bases) -> worn variant in 8 facings + per-facing layers; the item job remembers every fit.
- 2026-11-21 Item jobs built (asset type "item", core/item.py). Anchor = item front (anchor_still, "shown on its own and not worn ... as if worn by an invisible body"); Facings = its back (H3 edit of the front); "Make a variant…" on a character lists approved items -> item.fit -> variant with item front as <Picture 2> for S/SE/E/W/SW, item back for NE/NW, words for N; item job records inputs.fits. Measured, red cape (jobs/red_cape/c1) on knight/p2_002:
  * back view: "draw the same item seen from behind" -> copy of the front (open front, clasp; turned_from 5.2, caught by the copy check); "turn it around 180 degrees ... the back is one closed outer surface" -> closed backs 16-21 on 4 rolls (seed 7 still showed the clasp twice). Kept the second.
  * fit with the back picture at N: the knight's belt was drawn across the cape, 5 of 5 rolls; two extra sentences ("worn over everything ... never on top", "nothing added across it") did not fix it and made NW worse -> reverted. Words at N: whole cape, 0 of 2 with a belt -> N uses words. NE/NW with the back picture: 3 of 4 clean (seed 7 NW has the belt: re-roll).
  * Known: N by words drops the trim detail (item_core cuts after "with"); the knight's huge helmet hides the shoulders, so this base is a hard case for capes.
- 2026-11-21 Ronan: "We don't need to extract it back off player." Equipment layers (core/layer.py, variant minus base) removed: the item job is the original, the fitted variant is the worn result. Old jobs/*/02_facings/layers folders are leftovers and unused.
- 2026-11-21 Plain base body + item export (Ronan: "Both then push").
  * Asset type base_body: a character (same actions) drawn plain to fit items on. Measured: one facing at a time from a plain-body anchor only turned the head (7 of 7 flagged as copies, human/body1) -> base bodies use the animals' turnaround sheet (generate._turnaround, SAM 3 cut, W/SW/NW mirrored). "Wearing only plain undergarments" on the sheet -> bare mannequin bodies (2 of 2); named garments (builder.BASE_BODY_WEAR: grey sleeveless undershirt, grey knee shorts, brown cloth shoes) -> drawn (2 of 2). Real run human/body2 (seed 8): all 8 views turned, 27 s. Red cape fitted -> human/body2_red_cape: cape in all 8 views incl. a full back at N, 0 warnings (NW has a small ornament on the back).
  * Item export (Export tab on item jobs): 06_export/item/<name>_front.png, _back.png (pixel art at the profile sprite height, one palette for both; smooth styles scaled) + <name>_item.json (sizes, colours, fits). red_cape: 34x48 each.
- 2026-11-21 Can the local VLM (Qwen3-VL 4B, prompt_writer) check fitted-item mistakes? (Ronan; questions must be generic: only the item name, from item_core of the item description, changes.) Labelled real outputs from today, 41 questions, ~3 s each:
  * "anything (belt, strap, band, buckle) drawn on top of {item}?" 9/13: caught 3 of 6 belts-over-cape, 1 false alarm in 7.
  * "is the character wearing {item}?" 6/10: often ignores "answer yes or no" and writes a markdown report.
  * "front-only detail (clasp, gem...) visible on the back of {item}?" 4/6: said "no" every time, caught 0 of 2.
  * "which way does the body face?" 8/11: called failed turns (only the head turned) "left"/"right"; mixed up left/right on the knight's E. The pixel copy check (turned_from) caught 7 of 7 of those.
  * A strict "one word only" system prompt returned empty text; a plain "Answer yes or no." works.
  Verdict: not reliable enough to gate or auto re-roll. Not built.
- 2026-11-21 Ronan: no automatic mistake checker for fitted items (colour check / bigger VLM declined): "let human look over it, they can always re-run". Review + Re-roll is the check.
- 2026-11-21 UI/layout/workflow audit (Ronan asked): docs/AUDIT_UI_2026-11-21.md. P1: job header overflows (Make a variant…/Archive off-screen at 1440 px), 'Re-generate all' on animal/base-body facings always fails, New form overflows the sidebar, equipment flow not discoverable. Nothing fixed yet.
- 2026-11-21 UI audit fixes (P1 #1-4, P2 #5-12) done, checked in the browser at 1440/800 px; queue became a drawer (the fixed 340 px column was what pushed Make a variant/Archive off-screen). Open: test-job cleanup, P3 polish.
- 2026-11-21 Directional sprite readiness (Myth-style billboards) requested: plan in docs/PLAN_DIRECTIONAL.md, waiting for Ronan's calls on R1 border default, R2 mirror_policy default, R4 >8-view generation. Jobs archive choice (14 vs 18) also still open.
- 2026-11-21 Ronan approved docs/PLAN_DIRECTIONAL.md as proposed: R1 2px border only on the new align output (pixel stage keeps 1px); R2 missing mirror_policy = 'legacy' (today's behaviour) for all assets, 'none' selectable; R4 generation stays 4/8 views, manifest/viewer take any N. Archived the 18 listed test/superseded jobs (reversible: jobs/_archive).
- 2026-11-21 Directional readiness built. Measured: replay_downscale matches stored frames' lit pixels (worst 0.9% over 250 frames incl. mirrored, knight/cat/hare); manifest migration of 21 real jobs ~10 s first time (foot points measured once, cached). Turntable: requestAnimationFrame stops when the page is hidden, so controls and image loads redraw directly.
- 2026-11-21 Handoff prep: docs/wiki/ (8 pages; GitHub's own wiki is disabled on the repo, so the wiki lives in docs/), AGENTS.md for GPT/local agents, unused imports removed, stale backlog/audit statuses updated. Only branch is main (nothing to clean).
