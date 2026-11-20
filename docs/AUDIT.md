# SpriteWaffle audit — 2026-11-20

Scope: code layout, CLI, web UI, MCP, packaging, docs, missing features. State at audit: ~3,900
lines of package code, 100 tests passing, everything verified with real runs.

## Bugs found

| # | Where | Problem | Fix |
|---|---|---|---|
| B1 | `comfy/templates.py`, `core/profile.py`, CLI/UI/MCP defaults | `templates/`, `profiles/`, `jobs/` resolve against the **current directory**: run SpriteWaffle from anywhere but the repo root and it can't find its templates (MCP needed a `--root` workaround) | one `paths.py`: project root from `SPRITEWAFFLE_HOME`, else the repo the package lives in |
| B2 | web UI | jobs carry a profile but the UI never sends it: every UI-run stage silently uses the **default** profile | server uses the job's profile; UI can choose it |
| B3 | CLI | errors surface as Python tracebacks | known errors print one readable line, exit code 1 |

## Code structure

| # | Finding | Action |
|---|---|---|
| C1 | `cli.py`: 25 flat commands, one-line parser soup, half without help, stale "Phase 1" docstring | regroup by workflow, help text on every command, `--version` |
| C2 | video reading duplicated (generate, stages, motion) | `frames.video.read_frames` |
| C3 | 04_pixel writing duplicated (`stages.pixel`, `stages.flow_transfer`) | one `_write_pixel_sets` |
| C4 | approval checks duplicated; `stack.stage` imports private `generate._require_approved` | public `generate.require_approved` |
| C5 | profile commands: only `new` | `profile list|show|new` |

## Web UI

| # | Finding | Action |
|---|---|---|
| U1 | no ComfyUI / worker status anywhere; a dead ComfyUI only shows as failed tasks | status bar with live ComfyUI + worker state |
| U2 | anchor form lacks asset type, hero style reference, seed, profile (MCP has them) | full anchor form |
| U3 | no downloads: exported .aseprite/PNG/GIF aren't reachable from the page | Export panel: file links + "Export character" |
| U4 | `alert()` for errors | inline toasts |
| U5 | prop jobs show facings/actions; characters show nothing about the workflow order | step bar (Anchor → Facings → Actions → Export); props get Anchor → Stack → Export |
| U6 | queue: no retry for failed tasks, no clearing finished ones | retry + clear finished |
| U7 | jobs list unsorted, raw timestamp ids, no thumbnails | newest first, anchor thumbnail, asset type |
| U8 | one action at a time: 8 facings x N actions is 8N clicks | batch animate (choose facings x actions) |
| U9 | motion library invisible in the UI | library panel: list, approve, add from an action |

## Missing features a real user needs

| # | Feature | Why |
|---|---|---|
| F1 | README | there is no install / quick-start / workflow guide at all |
| F2 | `spritewaffle doctor` | one command that checks ComfyUI, templates, models, worker lock, folders |
| F3 | mirror actions (E->W, NE->NW, SE->SW) in code | kickoff rule: mirroring is code, not prompts; halves render time for symmetric characters |
| F4 | batch animate (CLI/MCP/UI) | see U8 |
| F5 | archive a job | jobs only grow; archive moves to `jobs/_archive/` (reversible) |

## Not changing

- Dependency set (pinned, `pip check` clean). The one test warning is inside starlette's test client.
- Test-approved demo assets (knight, goblin, mannequin, chest) stay as they are for Ronan to review.
