# Asset manifest (schema_version 1)

Every job (asset) can have `jobs/<character>/<job_id>/manifest.json`. It describes the asset for a
directional-sprite engine: every frame's view angle, foot point, colour / depth / normal / master
files and the downscale that made it, plus the camera profile and mirror policy.

The manifest is **derived** from the files the job already has (`core/manifest.py → build`), so
it never disagrees with them. The queue rewrites it after anchor, facings, sheet, pixelize, mirror,
flow, transfer, export and align. A timeline save refreshes it as well. `read` returns the stored file with defaults for any missing
field, or builds one for an asset that has none, so old assets always load.

## Angles

`yaw_degrees` is 0 when the character faces the camera, and increases **clockwise seen from
above**. With the camera in the south looking north:

| label | S | SW | W | NW | N | NE | E | SE |
|---|---|---|---|---|---|---|---|---|
| yaw | 0 | 45 | 90 | 135 | 180 | 225 | 270 | 315 |

"E" is the side view facing screen right. Any `view_count` is allowed (4, 8, 16, 32…):
view `i` has yaw `i × 360 / view_count`. Compass labels are for display only (`label` is the
degrees, e.g. `22.5°`, when no compass name fits). Generation currently produces 4 or 8 views;
items have 2 (front 0°, back 180°); effects and props 1.

A flipped view shows yaw `(360 − yaw) mod 360` (W ↔ E, SW ↔ SE; S and N map to themselves).

## Top level

| field | type | meaning |
|---|---|---|
| `schema_version` | int | 1. A newer version than the installed SpriteWaffle is refused. |
| `asset_id` | str | `<character>/<job_id>` |
| `project_id` | str | the project (jobs folder) id from `<jobs>/project.json`, default the folder name |
| `asset_type` | str | character, base_body, item, animal, creature, effect, prop |
| `style`, `profile` | str | art style; game profile name |
| `camera` | object | snapshot of the effective camera profile (below), with `source`: `implied` / `project` / `asset` |
| `mirror_policy` | str | `legacy` (default) / `none` / `mirror_left_from_right` / `custom` |
| `mirror_map` | object\|null | custom only: `{"<view_index>": <source view_index>}` |
| `view_count` | int | views in the set |
| `canvas` | [w, h] | one cell size for every frame of the asset |
| `align_feet` | bool | true after Align feet. Untouched frames use their aligned copies when available. |
| `base_job` | str\|null | a variant's base job (fitted item, one-change variant) |
| `views` | list | one per view: `view_index`, `yaw_degrees`, `label`, `facing_image` (the still, or null), `mirrored`, `source_view_index` |
| `animations` | list | one per action × frame set: `action`, `frame_set` (`12f`/`24f`), `fps`, `loop`, `views` (indices present), `frames` |

## Frame entries (`animations[].frames[]`)

| field | type | meaning |
|---|---|---|
| `view_index`, `view_count`, `yaw_degrees` | int, int, float | the view this frame belongs to |
| `frame` | int | index within the effective animation sequence |
| `frame_id` | optional str | stable ID in a reordered or duplicated frame set, such as `001.png` or `copy-1` |
| `source_frame` | optional str | numbered processed filename behind a frame in an edited sequence |
| `camera_elevation_degrees` | float | from the camera profile |
| `mirrored` | bool | made by flipping another view's frame |
| `source_view_index` | int\|null | the view it was flipped from |
| `foot_point` | [x, y]\|null | where the character touches the ground, in cell px: x = centre of the lowest opaque band, y = bottom edge of the lowest opaque row (a pixel boundary) |
| `color` | path | the effective frame. This can be a processed frame, its aligned copy, or a saved replacement. |
| `color_unaligned` | path\|null | the original frame when `color` is the aligned copy |
| `color_source` | optional path | the processed or aligned image behind an active timeline replacement |
| `duration_ms` | optional int | saved timeline duration for this frame |
| `depth`, `normal` | path\|null | reserved slots: `<frame>_depth.png`, `<frame>_normal.png`. Replaced frames omit their old maps. |
| `master` | path\|null | the high-res source, `03_actions/<facing>/<action>/selected_<n>f/<k>_src<i>.png`; a mirrored frame points at its source view's master |
| `downscale` | object | how the processed frame was made from `master` (below), so it can be replayed |

Paths are relative to the job folder. Old frames that predate a field get its default
(`mirrored: false`, `foot_point / depth / normal / master / downscale: null`).

### `downscale`

`method` (`pixelize`, `smooth`, `flow`, `mirror`), `grid` (`size`, `ox`, `oy`, `resample`),
`scale` (smooth styles), `palette` (hex list), `cell`, `placement` (`scale`, `crop`, `paste`,
`pivot`), `outline`, `despill`, `target_height`, `alpha_threshold`. A mirrored frame records
`{"method": "mirror", "flip": true, "source": <the source frame's record>, "placement", "cell"}`:
the source's finished cell, flipped, then laid out again.

`core/manifest.replay_downscale(image, record, alpha_from=master, quantize=False)` runs the same
steps on any image the master's size, so a depth or normal map made from the master lands on the
colour frame's pixels. Measured on knight, cat and hare (250 frames, mirrored ones included): the
replayed opaque pixels match the stored frames (worst 0.9 %).

## Camera profile

One per project in `<jobs>/project.json` (`{"schema_version": 1, "id": "...", "camera": {...}}`),
overridable per asset in `job.json → inputs.camera` (only the differing fields).

| field | default | meaning |
|---|---|---|
| `camera_elevation_degrees` | from projection (side 0, topdown_34 45, iso_2to1 30) | camera height above the horizon |
| `framing` | 0.45 | character height ÷ generated frame height |
| `character_scale` | game profile sprite height | character height in px at final size (used by the pixel stage when set and it fits the cell) |
| `light_yaw`, `light_elevation` | from the game profile's light word (top_left → 45°, 50°) | where the light comes from |
| `background_mode` | green | what generation keys out (generation itself always draws green) |
| `canvas_border_px` | 2 | transparent border kept by Align feet |
| `style_notes` | "" | appended to every generation prompt |

With no project or asset profile, prompts are byte-for-byte what they were. When one is set, every
still generation gets one extra sentence, and only for what the game profile doesn't already
say: a different elevation, a different framing, style notes. Each generation's provenance records
the camera snapshot.

## Mirror policy

| policy | facings | animations |
|---|---|---|
| `legacy` (default, also for assets without the field) | as before: flipped only when a facing drifts and its partner didn't | the run's "Mirror W / NW / SW" checkbox |
| `none` | never flipped | never flipped |
| `mirror_left_from_right` | S, N and the right-facing half rendered; W, NW, SW flipped from E, NE, SE | the same; a missing source is rendered too |
| `custom` | per `mirror_map` | per `mirror_map` |

Asymmetric characters (shield arm, eyepatch, emblem, a bag on one side) should use `none`.

## Align feet (optional)

The `align` stage moves each frame (whole pixels, no resampling) so its foot point sits on the set's
median foot point, keeping `canvas_border_px`. It writes `frames_aligned/` next to `frames/`; the
originals stay. It sets `align_feet`, after which the manifest and the character export use the
aligned frames. A frame that can't move all the way without crossing the border is reported.

## Export

The character export (`.aseprite` + atlas) reads colour frames only (`000.png`…), never a map.
When any frame has a `_depth` or `_normal` map, the export also writes `<name>_atlas_depth_<i>.png` /
`<name>_atlas_normal_<i>.png`. These have exactly the colour pages' layout (same rectangles and
trims), and the atlas JSON lists them under `map_pages`. Without maps, the output is unchanged.
Re-pixelizing a clip clears its `frames/` folder, maps included, because they would no longer line up.

## Calls

| | UI | HTTP | MCP | CLI |
|---|---|---|---|---|
| read manifest | Turntable… | `GET /api/jobs/{c}/{j}/manifest` | `manifest(character, job_id, rebuild=False)` | |
| rebuild one | | `POST /api/jobs/{c}/{j}/manifest/rebuild` | `manifest(..., rebuild=True)` | `spritewaffle manifest --job c/j --rebuild` |
| migrate all | | | `manifest_migrate(rebuild=False, limit=0)` | `spritewaffle manifest [--rebuild]` |
| project camera | Camera… → Save for the whole project | `GET/POST /api/project/camera` `{"camera": {...}\|null}` | `camera_profile(action="get"\|"set", camera={...})` | |
| asset camera | Camera… → Save for this asset only | `GET/POST /api/jobs/{c}/{j}/camera` `{"camera": {...}\|null}` | `camera_profile(action, camera, character, job_id)` | |
| mirror policy | Facings / Animations → Mirror policy | `POST /api/jobs/{c}/{j}/mirror_policy` `{"policy", "mirror_map"}` | `mirror_policy(character, job_id, policy, mirror_map)` | |
| align feet | Animations → Align feet | `POST /api/jobs/{c}/{j}/run` `{"stage": "align"}` | | |
| turntable | Facings / Animations → Turntable… (read-only) | | | |
