# Studio guide

[Wiki home](Home.md) · [Asset workflows](Workflows.md) · [CLI and MCP](Interfaces.md)

Use this guide for setup, navigation, project settings, and editing. Asset-specific production
steps are in [Workflows](Workflows.md).

## Requirements

- Python 3.11+ for SpriteWaffle. On Linux and macOS, use `.venv/bin/` for the commands
  below. The packaged workflow was tested on Windows.
- Optional local generation was tested on Windows 11 with an NVIDIA GPU and 24 GB VRAM.
- ComfyUI 0.45+ at `http://127.0.0.1:8188` (or set `SPRITEWAFFLE_COMFY`) with the MiniMax H3 /
  H3 Image models (~94 GB). **Model list, folders, download links, custom nodes:
  [`docs/COMFYUI_SETUP.md`](../../docs/COMFYUI_SETUP.md).**
- The ComfyUI workflows: [`comfyui/workflows/`](../../comfyui/workflows/) (drag onto the ComfyUI canvas)
  and [`templates/`](../../templates/README.md) (the API copies SpriteWaffle sends).
- Frame processing (pixelize, QA, export, mirror, flow transfer, sprite stacking) works without
  ComfyUI.

## Install

```powershell
git clone https://github.com/Fablestarexpanse/spritewaffle.git
cd spritewaffle
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt   # exact tested versions
.venv\Scripts\python -m pip install -e ".[dev]" --no-deps
.venv\Scripts\spritewaffle doctor
```

`doctor` checks Python, folders, workflow templates, the local ComfyUI setup, the queue
worker, and the motion library. For generation, resolve ComfyUI failures before queuing
a render. Imported artwork, editing, and export can run while ComfyUI is offline.

## Start

```powershell
.venv\Scripts\spritewaffle ui
```

Open <http://127.0.0.1:8765>. Use **Queue** to see active or failed work. On narrow screens,
**Status** shows the ComfyUI and worker details. The app runs its own queue worker.
On Windows, double-click `Launch_SpriteWaffle.bat` after
installing into the repository's `.venv` to start the server and open the browser.

Use **New asset** from any job, or select the SpriteWaffle logo to return home. **Jobs**
opens the job browser. Press **/** to focus job search. Stage tabs lead the workflow,
and **Job settings** holds asset-specific configuration and archive.

Open **Appearance** for Midnight, Slate, Forest, Light, OLED, or the system theme. You can
change the accent color, interface scale, spacing, transitions, and the background behind
transparent previews. These choices are stored in this browser for this local address.
**Appearance → About** shows the installed version, official badge, and software license link.

Open **Project → Style guide** to set an art style and game profile for new jobs. Add the
target engine and any art direction notes you want to carry with each asset. In **New asset**,
leave either field on **Project default** to inherit it, or select an explicit override.
Open **Job settings → Saved style guide** to see the project choices at creation. The same guide
appears in that asset's manifest. Art direction and target engine are recorded as guidance.
Project settings live in the jobs folder. The CLI uses `spritewaffle project-style`
with optional `--set FILE` or `--clear`. HTTP uses `/api/project/style` and MCP uses `project_style`.

Open **Project → Master palette** to enter up to 256 `#RRGGBB` colours, one per line.
New jobs save a copy for pixel-art processing. A fixed game profile palette takes priority,
followed by a job palette you import or rebuild in **Animations**. Use **Use saved project
palette** to clear that job override. Choose **Apply** to reprocess affected clips from their
existing frames. To import palette files, use `spritewaffle project-palette --import FILE`.
The HTTP API uses `/api/project/palette` and MCP uses `project_palette` and `palette`.

Open **Job settings → Check project style** to compare its art style and game profile with the
current project defaults. The check flags colours outside the master palette in the job's
selected palette and recorded pixel-art clip palettes. A subset of the project palette is
valid. A missing or unreadable processing record is shown as **Needs review**. The report
uses saved processing records, so check manual frame edits separately. Findings are advisory.

The same report is available through `spritewaffle style-check --job hero/job`,
HTTP `GET /api/jobs/{character}/{job}/style-check`, and MCP `style_check`.

Open **Project → Reference library** to build a visual reference library. Add a PNG, JPEG,
or WebP still up to 16 MiB and 16,777,216 pixels. Set a collection and add notes, then use the
collection filter to find the image again. Click its thumbnail to view the full original.
Use **Archive** to hide an entry and **Show archived** to restore it. Original copies and
thumbnails live in the jobs folder's `_references` directory. Move the whole jobs folder
to keep the library portable. References are for visual guidance.

On **Anchor**, choose one image under **Style reference → Project references** and describe
the asset you want to generate. Click the reference thumbnail to inspect the original.
SpriteWaffle records the reference ID in the job and manifest. Item anchors use only the image's
colour cues. Other supported assets send the image and description to the image-edit workflow.
The generated anchor opens for human review. If you archive a selected reference, restore it
or choose another before generating. Animals and base bodies use their turnaround-sheet workflow.

Use `spritewaffle project-references list`, `add`, `edit`, `archive`, `restore`, or `path`
at the command line. The HTTP API uses `/api/project/references`. MCP provides
`project_references` for managing entries and `project_reference_image` for previews.
For generation, use `spritewaffle anchor --job hero/new --describe "a teal courier" --project-reference ID`
or pass `project_reference_id` to MCP `generate` or the HTTP anchor stage arguments.
To follow the style several references share (a **style set**), pick one under Style reference and up
to two more under **Also match**; or use `--style-set ID,ID[,ID]` / `project_reference_ids`. With
three painted references a new character kept the painted look without copying any of them.

Under **Export**, use **Check freshness** to compare the latest character bundle with its
processed frames, palette, QA inputs, timing, maps, and attachments. It also checks that
exported files still match the receipt. Re-export an older bundle once to start tracking it.
This check is also available through `spritewaffle export-character-status --job hero/job`,
HTTP `GET /api/jobs/{character}/{job}/export_character`, and MCP `character_export_status`.
If you exported with a CLI profile override, use the same `--profile` when checking in the CLI.
If aligned frames are stale, use **Re-align feet** and export again. The check tracks the original
processed frames and maps, the camera's canvas border, and the aligned copies. Rebuilding also
updates the character pivot and moves effect spawn points with the aligned frame. The CLI command is
`spritewaffle align-feet --job hero/job`. MCP exposes `align_feet` for the same rebuild.

Use **Check freshness** on an item's **Export** tab or on an **Effect** tab to check that
bundle. Item checks cover front and back views, approval, sprite-file settings, and the fit
list. Effect checks cover the saved clip, saved processing settings, and the latest completed
bundle. Render-only prompt edits do not change the exported frames. Re-export an older item
or use **Re-process frames** on an older effect once to establish its receipt.

The CLI commands are `export-item-status --job CHARACTER/JOB` and
`export-effect-status --job CHARACTER/JOB`. The HTTP API uses `GET /api/jobs/{character}/{job}/export_item`
and `GET /api/jobs/{character}/{job}/export_effect`. MCP exposes `item_export_status` and
`effect_export_status`.

In **Animations**, choose **Details** on a clip to review its saved QA report. Expand **frames with findings**
to inspect individual processed frames. QA numbers frames from zero and keeps the source
filenames so a missing frame cannot shift a finding to another image.
Use **Check action exports** to see freshness for PNG and Aseprite separately.
After processing an action, the check tracks its saved clip, selected source frames, and effective
palette. If one changes, use **Re-process frames** before exporting the action or character again.
A changed saved clip is decoded and processed locally. **Re-export action** queues export from the
existing processed frames. Palette-only rebuilds keep manually selected frames. Mirrored actions
follow their source facing. Optical-flow actions track their approved facing and library guide.
Older actions gain processing records when reprocessed.
The CLI equivalents are
`qa-review` and `export-action-status`. Both accept `--job`, `--facing`, and `--action`.
MCP exposes QA findings in `status`, export freshness in `action_export_status`,
and export from processed frames in `export_action`.

### Animation timeline

In **Animations**, choose **Edit timeline** on a clip. Choose the frame set, then scrub
or play it with its saved timing. **Save duration** overrides one frame in milliseconds.
**Reset duration** restores its profile timing. **Replace frame** takes a single PNG at the
same cell size. **Restore source** brings back the processed image and keeps the saved timing.
A replacement becomes inactive if its processed source changes.

Open **Replacement history** to preview and reuse an earlier upload or pixel edit. **Restore source**
keeps the saved versions. An earlier version can be explicitly applied to a changed source
if the PNG still fits the cell. Existing active replacements appear as the first version.
Older PNG files whose frame assignments were cleared remain under
`edits/animations/<facing>/<action>/<set>/replacements` in the job folder. They can be
imported again with **Replace frame**.

Turn on **Onion skin** to compare the previous and next frames while paused. The overlays
wrap on loops and stop at the ends of one-shot clips. The toggle is saved in this browser.

Use **Duplicate**, **Move earlier**, and **Move later** to change the sequence.
A copy starts with the selected frame's timing, artwork, and replacement history. It can
then be edited independently. **Insert blank after** adds a transparent frame after the
selection. QA flags it until it contains visible pixels. To add artwork, choose a single PNG at the same cell
size and select **Insert PNG after**. The imported PNG becomes the new frame's source and
can have its own timing and replacement history.

**Remove frame** hides the selected frame and keeps at least one frame in the sequence.
**Undo order** and **Redo order** apply to insertion, removal, duplication, and moves.
Timing and artwork edits stay with their frame IDs. An effect attached to a removed frame
is omitted from export until that frame returns. If an inserted PNG goes missing, changes
on disk, or no longer fits a resized cell, restore the file or remove its entry before
running QA or exporting.

Open **Playback settings** to choose **Use source**, **Loop**, or **Play once**. To
play a smaller section, enable **Limit playback range**, choose its first and last frames,
and save. The timeline still lets you scrub and edit the full sequence. The range belongs
to the selected frame set. Its endpoints follow the chosen frame IDs through reordering.
If an endpoint disappears or moves across the other, choose a valid range, clear it, or
undo the order change before running QA or exporting that clip.

Open **Animation tags** to name sections of a frame set. Choose **New tag**, enter a name,
select its first and last frames, and choose whether it loops. Tags may overlap. Select
an existing tag to change it, preview it, or remove it. **Preview tag** plays that range
with its own timing and loop setting. The main playback settings stay as saved.

Tag endpoints follow their frame IDs through sequence edits. If an endpoint disappears or
crosses the other, repair or remove the tag before running QA or exporting the clip. QA
checks the seam of each looping tag. Aseprite keeps the original animation tag and adds
named entries such as `walk_S [Recovery]`. Action and character JSON include `tags` with
inclusive, zero-based `start` and `end` positions relative to the clip.

Open **Pose markers** on a selected frame to label beats such as Contact, Passing,
Anticipation, Impact, Recovery, Idle, Key pose, or Loop transition. Save one or more labels
for that frame, then use **Previous marker** and **Next marker** to jump among marked frames.
Markers follow frame IDs within the selected frame set. Copies start unmarked. Undoing
removal restores the original frame's markers.

The action JSON and each character animation record include `pose_markers` with the
zero-based `frame` position, stable `frame_id`, and `markers`. The asset manifest lists
marker identifiers on each marked frame. Re-export after changing markers to refresh the JSON.

Choose **Edit pixels** on the selected frame or copy. Pencil, Eraser, and Pick color work
on the effective image. Choose an RGBA color or use a swatch from the job palette. Zoom
in to use the pixel grid. With the canvas focused, move with the arrow keys and apply the
tool with Enter or Space. **Fill** recolors pixels connected above, below, left, or right
that have the same RGBA value as the clicked pixel.

Use **Select** to drag a rectangle. With the keyboard, press Enter to set the first corner,
move with the arrow keys, and press Enter again to set the opposite corner. Escape cancels
an unfinished rectangle. Pencil, Eraser, and Fill stay inside the selection until you
choose **Deselect**. **Erase selected pixels** makes the rectangle transparent in one step.
**Undo edit** and **Redo edit** apply to artwork changes inside the open draft.

**Save pixel edit** stores a replacement version, preserving the processed PNG. Selections
are temporary. If the underlying frame changes while you edit, reopen the editor to start
from the current image.

Choose **Reposition frame** to shift the artwork by whole pixels. Positive horizontal
offsets move right, and positive vertical offsets move down. **Align to reference foot**
measures the foot point in another frame from the same set, including its saved edits.
It aligns vertically by default. Choose **Horizontal and vertical** to also move to the
nearest whole pixel horizontally. The comparison shows both foot points and refuses
offsets that would clip visible pixels. Apply the result as a replacement to keep its
previous artwork available in history.

Choose **Reprocess frame** to compare the current artwork with a fresh pass from the retained
master PNG. The comparison uses the saved cell and placement, and the recorded palette and
grid or painted-art scale. Choose **Edges only** under **Green spill cleanup** to preserve
green in the interior. **Highlight changes** marks the exact pixels that differ.
**Apply as replacement** saves a version in replacement history. If the inputs change during
review, choose **Compare again** before applying it.

Single-frame reprocessing needs the retained selected master and its processing record.
For mirrored or flow clips, use the existing clip reprocessing command. For inserted frames,
use the pixel editor or PNG replacement. A pixel-art pass uses the recorded palette and grid
with the selected frame alone, so its colour choices can differ from batch processing across frames.

Run **QA** after changing artwork or playback, then re-export the action or character.
Action sheets, previews, Aseprite files, and the SpriteWaffle character atlas metadata carry
the edited frames and timing. Aseprite uses RGBA for replacements. Character export keeps any
existing aligned copies for untouched frames. A replacement uses the saved pixel position
and its old depth and normal maps are omitted. GIF preview timing uses 10 ms ticks.
For a saved playback range, GIF and APNG show that section and the Aseprite animation tag
covers it. JSON metadata records inclusive, zero-based `playback_range` positions within
the clip. Strips, atlas frames, and Aseprite cels retain the full sequence. Existing one-shot
clips keep their preview export behavior until a playback override is saved.

Use `spritewaffle timeline --job hero/job --facing S --action walk` to read a timeline.
To edit, add `--frame 001.png` and one of `--duration 160`, `--reset-duration`,
`--replace repair.png`, `--restore`, `--use-version 1`, `--duplicate`, `--move-to 0`,
`--insert artwork.png`, `--insert-blank`, or `--remove`. Copies use IDs such as `copy-1`
and inserted frames use IDs such as `insert-1`. Move positions count from zero. Use `--undo-order` and
`--redo-order` to change the sequence history. MCP exposes
`animation_timeline` and `edit_timeline_frame`. The HTTP route is
`GET` or `POST /api/jobs/{character}/{job}/timeline`. Use operation `activate` with a
one-based `version` to reuse history. The order operations are `duplicate`, `move`
with a zero-based `position`, `undo`, and `redo`.
Use `insert` with the anchor `frame` and `png` (HTTP base64) or `png_path` (MCP).
`insert_blank` uses the same anchor. `remove` accepts the frame to hide.

For playback, pass `--playback once --range-start 001.png --range-end 004.png`.
Pass `--playback source` without endpoints to restore the source setting and the full clip.
HTTP and MCP accept `operation` set to `playback` and a `playback` object with `mode`
(`source`, `loop`, or `once`) and both optional `start_frame` and `end_frame` IDs.

Use `--save-tag tag.json` with `name`, `start_frame`, `end_frame`, and a boolean `loop`.
Include the existing `id` to edit a tag. `--remove-tag ID` removes it. HTTP and MCP use
`save_tag` with a `tag` object and optional `tag_id`, or `remove_tag` with `tag_id`.

Use `--frame 001.png --pose contact --pose key` to set that frame's markers. Use
`--clear-poses` on the same frame to clear them. HTTP and MCP accept `operation` set to
`pose` with a `frame` ID and a `pose_markers` list. An empty list clears the markers.

For pixel edits, use `--frame 001.png --pixels` to get the current `fingerprint`, cell dimensions,
job palette, and base64-encoded row-major `rgba` bytes. Use `--paint patch.json` on the same frame
with a JSON object containing `fingerprint` and `pixels`. Each `pixels` entry contains six integers
`[x, y, r, g, b, a]` for one changed pixel. Coordinates start at zero in the top-left corner, and
channels range from 0 to 255. HTTP reads the snapshot from `GET /api/jobs/{character}/{job}/timeline/pixels`
with the same query parameters and a `frame` ID. POST the patch to the timeline with `operation: "paint"`
and `frame`. MCP exposes `timeline_pixels` with optional `include_pixels` and `edit_timeline_frame`
with the same `paint` operation.

For reprocessing, choose a frame and run `--preview-reprocess --despill edge`. Use the returned
`fingerprint` with `--apply-reprocess FINGERPRINT --despill edge`. HTTP reads the comparison at
`GET /api/jobs/{character}/{job}/timeline/reprocess` with the same query parameters plus `frame`
and `despill`. POST `operation: "reprocess"` with `frame`, `fingerprint`, and `despill`. MCP exposes
`preview_frame_reprocess` and the same `reprocess` edit. Set `include_png` to include the two
base64 PNGs and their change mask in the MCP comparison response.

For repositioning, use `--preview-reposition --dx 2 --dy -1` or
`--preview-reposition --reference 001.png --axes vertical`. Apply the result with
`--apply-reposition FINGERPRINT` and the same options. HTTP exposes a `/timeline/reposition`
comparison with `frame` and either `dx` and `dy` or `reference` and `axes`. POST `operation`
set to `reposition` with the fingerprint and the same inputs. MCP exposes
`preview_frame_reposition` and the corresponding timeline edit.

## Files

```
jobs/<character>/<job_id>/
  job.json          inputs, stage status, provenance (model, seed, prompt per output)
  01_anchor/  02_facings/  02_ortho/  03_actions/<facing>/<action>/
  04_pixel/   05_qa/       06_export/  (character/, stack/, <facing>/<action>/<12f|24f>/)
jobs/_queue/        background tasks        jobs/_library/motions/   motion library
jobs/_archive/      archived jobs (move one back to restore it)
profiles/           game profiles (cell size, sprite height, palette, fps per action, ...)
templates/          ComfyUI workflows (API format) + parameter maps
comfyui/workflows/  the same workflows in editor format
```

`SPRITEWAFFLE_HOME` moves the whole project root; `SPRITEWAFFLE_JOBS` just the jobs folder.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header says *ComfyUI offline* | start ComfyUI; frame processing still works |
| `doctor`: *model missing: …* | that model isn't in ComfyUI's model folders, or the template map points at a different file name |
| A task failed | Queue panel → the error is on the task → **Retry** |
| New job types or buttons missing after an update | restart `spritewaffle ui`: the server doesn't reload itself |
| `another worker holds …` | only one worker per jobs folder; close the other UI/worker (a dead one's lock is taken over automatically) |
| Clip came out frozen | handled: re-rendered without the last frame automatically (the action shows a note) |
| TARA fails with *USE_FLASH_ATTENTION* | use the `comfy kitchen` attention backend (already set in the template) |

Design decisions and measurements: [`DECISIONS.md`](../../DECISIONS.md). Audits: [`docs/AUDIT.md`](../../docs/AUDIT.md), [`docs/AUDIT_UI_2026-11-21.md`](../../docs/AUDIT_UI_2026-11-21.md).

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Every test runs in its own temporary jobs folder.
