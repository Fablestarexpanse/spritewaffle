# Fresh-eyes audit (2026-11-20)

An agent that had never seen the project audited it as an indie 2D dev (Unity + Aseprite, UI-minded),
working read-only: docs, the running UI at desktop and phone width, the CLI, and the exported files of
existing jobs. Findings marked **verified** were checked against the code afterwards.

Verdict: usable as a concept-to-first-pass generator for one pixel-art hero; not yet a pipeline to
ship from (per-clip palettes, per-clip pivot, unbounded atlas, stale exports not flagged).

## Bugs

| # | Sev | Where | Finding | Status |
|---|---|---|---|---|
| 1 | major | `ui/static/index.html` `loadJob` | Anchor description and import path carry over to the next job opened; "Generate anchor" then renders the wrong character | **fixed** 2026-11-20 |
| 2 | major | `cli.py` `_job` | Mistyped `--job` creates a junk job (any command), shows up in the UI list | **fixed** 2026-11-20 |
| 3 | major | `core/stages.py` `pixel` | Each facing/action quantized to its own palette; knight E/N/S share 0 colours; character export merges to 48 > profile 16 | **fixed** 2026-11-20: one job palette (from all stills, or a file) |
| 4 | major | `export/sheet.py` `feet_pivot` | Pivot per animation from union bbox (idle 31 vs walk 32 px); only in JSON, not in the .aseprite | **fixed** 2026-11-20: feet on the centre line, pivot slice in the .aseprite |
| 5 | major | `ui/server.py` queue list | Newest 60 tasks only: running task and older failures can be hidden; filter is client-side | **fixed** 2026-11-20 |
| 6 | major | Export tab | "done" / step 4/4 while newer clips exist; no stale/incomplete state | plausible |
| 7 | major | `export/aseprite.py` `_tags_chunk` | Tag repeat always 0 (infinite): attack/jump loop in Unity | **fixed** 2026-11-20 (Unity not yet checked) |
| 8 | minor | Anchor/Facings/clip re-roll | Overwrites approved (even user-imported) art without confirm or history | plausible |
| 9 | minor | `core/generate.py` | Raw dict in the asymmetric-anchor warning; mirror stays on for asymmetric characters | warning text **fixed** 2026-11-20 (now says to untick mirroring); mirror default unchanged |
| 10 | minor | `profile list/show`, `doctor` | "default" listed but `profile show default` fails | **fixed** 2026-11-20 |
| 11 | minor | README MCP command | literal tab in `C:\path\to` (`\t` escape) | **fixed** 2026-11-20 |
| 12 | minor | README | `style` / `writer` examples omit `--job` | **fixed** 2026-11-20 |
| 13 | minor | phone width | Queue panel opens below the page, invisible; tab bar clips Export | observed by auditor |
| 14 | polish | various | Job page flashes old job ~1 s; list re-render steals clicks; mixed path separators; prop Export/Anchor show character copy; .aseprite buried under ~90 per-clip files; no alt text; drift thresholds unexplained | observed by auditor |

## Missing for a real pipeline (auditor's list)

- Atlas max size + multiple pages, trim, mirror dedupe (full knight set 768×2560; painted 3072×10240).
- One character-wide pivot, written into the .aseprite (slice); optional hit/hurt boxes; animation events.
- Locked palette from a file (.gpl / .hex / Lospec).
- Engine-standard metadata (Aseprite/TexturePacker JSON, Unity, Godot SpriteFrames) and an export-to-folder target.
- Frame-level editing (drop/duplicate frame, retime, loop point).
- Batch across a cast (apply actions / export all).
- Configurable naming; 4-direction option in the New form.

## Docs gaps

Profiles not explained in the README; "needs ~94 GB + 24 GB GPU before anything generates" too buried;
no-GPU quick start (`run clip.mp4`) not its own section; no Unity import guide (importer, Point filter,
no compression, Max Size); status words (review/pass/done/approved) and drift/QA numbers not explained.

## Auditor's top 5

1. Fix the form carry-over and `_job` auto-create.
2. One palette per job (locked after first approved clip or from .gpl) + one feet pivot in the .aseprite.
3. Honest export: stale/incomplete states, repeat=1 for non-loop tags, confirm/history before overwriting approved art.
4. Atlas packing with max size, trim, mirror dedupe; export-to-folder; Unity import guide.
5. Queue UX: running pinned, server-side filter, grouped per animation, cancel-all per job, mobile overlay.
