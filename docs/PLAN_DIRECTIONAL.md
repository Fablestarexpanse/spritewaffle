# Plan: directional sprite readiness (Myth-style billboards)

Status: **built 2026-11-21** as approved (R1 border on align output only, R2 missing policy = legacy, R4 generation stays 4/8). Schema and calls: [MANIFEST.md](MANIFEST.md); changes: [../CHANGELOG.md](../CHANGELOG.md).

Goal: SpriteWaffle's data and output carry everything a later Myth-style test needs (many view
angles, crossfading between neighbours, per-frame depth/normal maps), without changing any
existing generation, UI flow or output. Engine-side blending and lighting are out of scope.

## What exists today (relevant)

| Area | Today | File |
|---|---|---|
| Asset | a *job*: `jobs/<character>/<job_id>/` with `job.json` (inputs, stages, provenance) | `core/job.py` |
| Project | the jobs folder (`SPRITEWAFFLE_JOBS`, default `<repo>/jobs`); no project file | `paths.py` |
| Sizes/camera | shared **GameProfile**: `projection` (side / topdown_34 / iso_2to1), `sprite_height_px`, `cell_size`, `light_dir` (a word), `directions` **4 or 8 only**, `mirror_allowed` | `core/profile.py` |
| Views | fixed compass labels S, SE, E, NE, N, NW, W, SW | `prompts/builder.py` |
| Final frames | `04_pixel/<facing>/<action>/<n>f/frames/000.png…`, one cell size, `placements.json` (one placement per set, `pivot` = feet point), `pixel_report.json` (grid, palette, method) | `core/stages.py`, `frames/layout.py` |
| High-res masters | **already kept**: `03_actions/<f>/<a>/selected_<n>f/<k>_src<i>.png` (frame k's source), facings at 2048 px in `02_facings/` | `frames/picker.py`, `core/stages.py` |
| Mirroring | per run (Animations "Mirror W/NW/SW" checkbox, facings auto-mirror on drift), recorded as `mode: mirror, source: E` | `core/stages.mirror_action`, `core/generate.facings` |
| Export | `.aseprite` + atlas pages + TexturePacker JSON + one SpriteWaffle JSON | `export/character.py`, `export/atlas.py` |
| API | FastAPI UI server + MCP server (FastMCP) over the same core | `ui/server.py`, `mcp_server.py` |

## Where each feature lives

**New modules** (pure functions, no UI code):

- `core/angles.py`: yaw math for any view count. `views(n)` gives view_index → yaw. Yaw is 0 when the character faces the camera and increases clockwise seen from above, so S=0, SW=45, W=90, NW=135, N=180, NE=225, E=270, SE=315. Also `label(yaw)` (display only), `mirror_of(yaw) = (360 − yaw) % 360`, and the legacy label ↔ yaw table.
- `core/camera.py`: **CameraProfile** dataclass with `camera_elevation_degrees`, `framing` (zoom fraction of frame height, today 0.45), `character_scale` (px at final size), `light_yaw`, `light_elevation`, `background_mode` (green / black / transparent), `canvas_border_px` (default 2), `style_notes`.
  - The project file is `<jobs>/project.json` (`{"schema_version", "id", "camera": {…}}`); `id` defaults to the folder name.
  - A per-asset override goes in `job.json` → `inputs.camera` (only the fields that differ).
  - `effective(job)` merges defaults ← GameProfile-implied values ← project ← asset override.
  - Defaults come from what the job's GameProfile already implies (side → 0°, topdown_34 → 45°, iso_2to1 → 30°; `sprite_height_px` → character_scale; `light_dir` word → yaw/elevation). That way an asset with no camera profile is described exactly as it was made.
- `core/manifest.py`: the per-asset manifest (schema below).
  - `build(job)` derives it from the files that exist; this is also the migration for old assets.
  - `read(job)` returns the stored manifest, or a built one with defaults; it never fails on old jobs.
  - `write(job)` saves it.
  - `replay_downscale(master, record)` re-runs a frame's recorded downscale on any image (this is what future depth/normal maps will use).
  - `foot_points(cells)` measures one per frame.

**Changes to existing files (additive only):**

| Feature | Where | What changes |
|---|---|---|
| 1 Angle metadata | `core/manifest.py`, `core/angles.py` | Each frame entry gets yaw, elevation, view_count, view_index, mirrored, source_view_index, computed from the facing label and the mirror records. Any `view_count` is accepted in the manifest and viewer. |
| 2 Camera profile | `core/camera.py`; `prompts/builder.py` gains **one optional sentence** | Prompts change only if a project or asset camera profile exists **and** sets an elevation the GameProfile doesn't already imply, or style notes. Otherwise prompts stay byte-identical (tested). The snapshot is stored in the manifest and in each stage's provenance. |
| 3 Foot point + canvas | `frames/layout.py` (`foot_point(rgba)`); `core/stages.py` new CPU stage **`align`** | The pixel stage also writes `footpoints.json` next to `placements.json` (a new file; frames untouched). `align` writes `frames_aligned/` with every frame's foot point moved to the set's median and the border enforced. The originals stay, and the manifest flags which one is canonical. |
| 4 Depth/normal slots | `core/manifest.py`, `export/character.py` | The manifest has `color` / `depth` / `normal` / `master` paths per frame. depth/normal are `null` unless `<frame>_depth.png` / `<frame>_normal.png` exist next to the colour frame. The exporter packs them into parallel atlas pages (`<name>_depth_0.png`, same layout) only when present; otherwise the output is unchanged. |
| 5 Masters | `core/manifest.py` | Links each frame to its existing `selected_<n>f` master (facings: `02_facings/<f>.png`). It records the downscale (method pixelize / smooth / mirror / flow, grid size + offset, resample, placement crop/scale/paste, palette, outline, despill, alpha threshold) from `pixel_report.json` + `placements.json` + the profile. Nothing is re-saved; masters are already kept. |
| 6 Mirror policy | `job.json` → `inputs.mirror_policy` (+ `mirror_map` for custom); `core/generate.facings` and `queue.submit_animate` read it | `mirror_left_from_right`: facings and animations render only yaw 0–180 and flip the rest (marked mirrored). `none`: never flip. `custom`: `mirror_map {view: source_view}`. UI: a select on the Facings and Animations tabs with the hint about asymmetric characters. |
| 7 Turntable | `ui/static/index.html` (dialog, canvas only) + `GET …/manifest` | Read-only. Views in yaw order, speed, scrub, snap vs crossfade (continuous yaw, blends the two nearest views), show/hide mirrored, foot-point overlay, any action/frame. It makes GET requests only. |
| API | `ui/server.py` | `GET/POST /api/project/camera`; `POST /api/jobs/{c}/{j}/camera` (override; `null` clears); `POST …/mirror_policy`; `GET …/manifest`; `POST …/manifest/rebuild`; `run` stage `align`. |
| MCP | `mcp_server.py` | `camera_profile(action=get\|set, fields, character?, job_id?)`, `mirror_policy(character, job_id, policy, mirror_map?)`, `manifest(character, job_id, rebuild=False)`, `manifest_migrate(limit?)`. |
| CLI | `cli.py` | `spritewaffle manifest [--all] [--rebuild] [--job c/j]`: the migration for thousands of jobs, streaming, one line per job. |
| Keeping it current | `core/queue.py` | After pixelize / mirror / align / export / approve finishes, rebuild that job's manifest (milliseconds; JSON only). |

## Manifest (schema_version 1), `jobs/<c>/<j>/manifest.json`

```json
{
  "schema_version": 1,
  "asset_id": "knight/p2_002", "project_id": "jobs",
  "asset_type": "character", "style": "pixel",
  "camera": {"source": "project|asset|implied", "camera_elevation_degrees": 0, "framing": 0.45,
             "character_scale": 48, "light_yaw": 315, "light_elevation": 45,
             "background_mode": "green", "canvas_border_px": 2, "style_notes": ""},
  "mirror_policy": "legacy|none|mirror_left_from_right|custom", "mirror_map": null,
  "view_count": 8, "canvas": [64, 64], "align_feet": false,
  "views": [{"view_index": 0, "yaw_degrees": 0, "label": "S", "facing_image": "02_facings/S.png",
             "mirrored": false, "source_view_index": null}],
  "animations": [{"action": "walk", "frame_set": "12f", "fps": 12, "loop": true,
    "frames": [{"view_index": 6, "frame": 0, "yaw_degrees": 270, "camera_elevation_degrees": 0,
                "view_count": 8, "mirrored": false, "source_view_index": null,
                "foot_point": [32, 62],
                "color": "04_pixel/E/walk/12f/frames/000.png", "depth": null, "normal": null,
                "master": "03_actions/E/walk/selected_12f/000_src00000.png",
                "downscale": {"method": "pixelize", "grid": 29, "offset": [3, 7], "resample": 1.0,
                              "placement": {"scale": 1.0, "crop": [], "paste": [], "pivot": []},
                              "palette": ["#…"], "outline": "none", "despill": "all"}}]}]
}
```

`docs/MANIFEST.md` will document every field, the yaw convention, and defaults for missing fields.

## Risks to existing behaviour, and how each is avoided

| # | Risk | Proposal |
|---|---|---|
| R1 | Spec default border is **2 px**; today's pixel stage uses a **1 px** margin. Changing it changes every new output. | The 2 px default applies to the new `align` output (and is stored in the camera profile). The existing pixel stage keeps 1 px. **Your call.** |
| R2 | Spec default `mirror_policy` is **"none"**, but today the Animations mirror checkbox is on by default and facings auto-mirror on drift. A "none" default would change current behaviour. | A missing field means **`legacy`** (today's behaviour, recorded in the manifest as what actually happened). New assets get `none` only if you say so. **Your call:** new jobs default to `none` (spec) or `legacy` (no change). |
| R3 | "Camera profile applied automatically to every generation" could change prompts for existing projects. | No project file means no change (byte-identical prompts, tested). The camera profile affects prompts only when it sets something the GameProfile doesn't already say. |
| R4 | **view_count > 8.** The data model, manifest and viewer will take any N. *Generating* 16/32 views needs new facing prompts worded by yaw degrees, plus refs from the nearest generated view. That's new generation behaviour, not "readiness". | Not in this task unless you want it: the manifest and viewer are ready, and generation stays at 4/8. **Your call.** |
| R5 | Spec file naming `<frame>_color.png`; today's colour frames are `000.png`. Renaming breaks existing loaders. | Keep `000.png` as the colour frame (the manifest's `color` field points to it). Depth/normal are reserved as `000_depth.png` / `000_normal.png` alongside. |
| R6 | Scale (thousands of assets). | Manifests are per job, built from that job's files only. The job-list API doesn't read them. Migration streams one job at a time and can be re-run (skips up-to-date unless `--rebuild`). |

## Tests to add

- Manifest read/write round trip; `read()` on a job with no manifest (migration) equals `build()`; schema_version present; old job.json without the new fields loads with defaults.
- Angles: views(4/8/16/32), label ↔ yaw for the 8 legacy labels, `mirror_of`.
- Mirroring: `mirror_left_from_right` renders only yaw 0–180 (fake Comfy call list) and flags the rest `mirrored`, `source_view_index` correct; `none` renders all; `custom` map honoured; frame pixels are exact flips.
- Foot point: measured on synthetic frames; `align` puts every frame's foot point on the same pixel and respects the border; originals untouched.
- Backward compatibility: every existing test still passes; prompts byte-identical without a camera profile; export output byte-identical when no depth/normal files exist; with a fake `000_depth.png` the exporter writes the depth page with the same layout.
- `replay_downscale(master)` reproduces the stored colour frame (pixel-exact for pixelize with a locked palette and grid).
- API + MCP: get/set camera profile, mirror policy, manifest read.

## Order of work (each step committed with a real run)

1. angles + manifest (read/build/migrate) + docs, CLI migrate over the existing 39 jobs.
2. Camera profile (project file, override, UI editor, API, MCP), snapshot in manifest.
3. Foot points + `align` stage + depth/normal slots in exporter.
4. Mirror policy (generation honours it) + UI select.
5. Turntable viewer.
6. Changelog (`CHANGELOG.md`, new), README MCP section.
