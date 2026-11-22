# SpriteWaffle

Local tool that turns AI-generated images and video into game-ready pixel-art sprites:
**character → 8 facings → animations → one `.aseprite` for Unity**, and **prop → sprite stack**.
Generation runs on your own ComfyUI (MiniMax H3 video + H3 Image); everything else — chroma key,
frame picking, pixelizing, QA, export — is built in. Nothing goes to the cloud.

**No AI agent needed.** The web UI and CLI do everything; the MCP server for agents is optional.

**Docs:** the [wiki](docs/wiki/Home.md) (workflows, architecture, prompting lessons, development, roadmap); coding agents start with [AGENTS.md](AGENTS.md).

**Let an agent install it:** paste this to Claude Code, Codex, Cursor or similar:

> Install SpriteWaffle by following `AGENT_INSTALL.md` in https://github.com/Fablestarexpanse/spritewaffle. Ask me before downloading models.

## License — free to create and sell games, art, and assets

**SpriteWaffle is free to use for personal and commercial creative work.** You may create and sell games, standalone sprite sheets, asset packs, artwork, animations, art commissions, and other original creative outputs made with SpriteWaffle. **No SpriteWaffle royalty or revenue share is required.**

The SpriteWaffle software is distributed under the [MIT License with Commons Clause v1.0](LICENSE.md): you may use, inspect, modify, and redistribute the software under its terms, but you may **not resell or repackage SpriteWaffle as a paid tool, or sell substantially the same software functionality as a paid hosted service**, without separate written permission.

**The software restrictions do not prohibit selling creative outputs made with the tool.** SpriteWaffle does not claim ownership of your generated artwork. However, third-party models, reference images, imported assets, and other dependencies may impose separate terms. See the [licensing guide](docs/LICENSING.md). The combined MIT + Commons Clause terms are **source-available, not OSI-approved open source**.

## Requirements

- Python 3.11+, an NVIDIA GPU for ComfyUI (tested: Windows 11, 24 GB VRAM; less VRAM untested).
  Linux/macOS: same steps with `.venv/bin/` (untested).
- ComfyUI 0.45+ at `http://127.0.0.1:8188` (or set `SPRITEWAFFLE_COMFY`) with the MiniMax H3 /
  H3 Image models (~94 GB). **Model list, folders, download links, custom nodes:
  [`docs/COMFYUI_SETUP.md`](docs/COMFYUI_SETUP.md).**
- The ComfyUI workflows: [`comfyui/workflows/`](comfyui/workflows/) (drag onto the ComfyUI canvas)
  and [`templates/`](templates/README.md) (the API copies SpriteWaffle sends).
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

`doctor` checks Python, folders, every template (nodes **and** model files present on your
ComfyUI), the queue worker and the motion library. Fix anything marked `[FAIL]` first.

## Start

```powershell
.venv\Scripts\spritewaffle ui
```

Open <http://127.0.0.1:8765>. The header shows ComfyUI, the worker and the queue (click it to open
the queue panel; it opens by itself when a task fails); the app runs its own queue worker, so
nothing else needs to be running.

Open **Settings** for Midnight, Slate, Forest, Light, OLED, or the system theme. You can
change the accent color, interface scale, spacing, transitions, and the background behind
transparent previews. These choices are stored in this browser for this local address.
Use **Jobs** to collapse or show the job browser. Press **/** to open it and focus search.

Under **Export**, use **Check freshness** to compare the latest character bundle with its
processed frames, palette, QA inputs, timing, maps, and attachments. It also checks that
exported files still match the receipt. Re-export an older bundle once to start tracking it.
This check is also available through `spritewaffle export-character-status --job hero/job`,
HTTP `GET /api/jobs/{character}/{job}/export_character`, and MCP `character_export_status`.
If you exported with a CLI profile override, use the same `--profile` when checking in the CLI.

In **Animations**, open a facing to review its saved QA report. Expand **frames with findings**
to inspect individual processed frames. QA numbers frames from zero and keeps the source
filenames so a missing frame cannot shift a finding to another image.
Use **Check action exports** to see freshness for PNG and Aseprite separately.
**Re-export action** queues export from the existing processed frames. The CLI equivalents are
`qa-review` and `export-action-status`. Both accept `--job`, `--facing`, and `--action`.
MCP exposes QA findings in `status`, export freshness in `action_export_status`,
and export from processed frames in `export_action`.

### Animation timeline

In **Animations**, open a facing and choose **Timeline**. Choose the frame set, then scrub
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

## Workflows

### Character (or creature)

1. **New** → name, type `character`, profile.
2. **Anchor** — describe it and generate, or import an image. Approve it when it's right:
   everything else is built from this one image. For a cast, make one *hero* first and pick it as
   the **style reference** for the others.
3. **Facings** — generates the other 7 directions. The drift number compares each with the anchor
   (green fine, amber borderline, red re-roll). Approve.
4. **Animations** — tick facings × actions and queue them. W / NW / SW are mirrored from
   E / NE / SE (no render, exact pixels) unless you untick mirroring; idle/walk/run loop.
   Click any result for QA details, re-render / re-process, or adding its clip to the motion library.
5. **Export** — *Export character* writes one `.aseprite` with a tag per animation (Unity's 2D
   Aseprite Importer makes one clip each, plus an Animator Controller) and atlas pages for other
   engines: trimmed frames packed into PNGs no bigger than the page limit (default 4096), each with
   a TexturePacker JSON (Phaser, PixiJS, Godot importers) plus one SpriteWaffle JSON with fps, loop
   and pivot per animation. *Engine flips W/NW/SW* leaves exact mirrors out of the atlas.
   Every file is downloadable from the same tab.

### Palette and pivot (pixel art)

- **One palette per character.** The first pixelize builds it from the anchor + every facing (so
  colours seen only from the back are included) and every clip uses it. Animations → **Palette**
  shows it; *Rebuild from facings*, or load your own `.gpl` (Aseprite / GIMP / Lospec), `.hex` or
  `.png`. Clips made with an older palette are listed; *Apply* re-pixelizes them from their frames
  (no rendering). CLI: `spritewaffle palette --job <job> [--file pal.gpl | --rebuild] [--apply]`.
  A loaded palette is matched by nearest colour, so it has to suit the character.
- **One pivot per character.** Each clip is placed so the feet sit on the cell's centre line, one
  pixel above the bottom, whatever the weapon or cape does. Every animation then shares the pivot
  `(cell/2, cell-1)`, written as a `pivot` slice in the `.aseprite` and as `pivot` / `pivot_norm`
  in the JSON. An action too wide for the cell is shifted just enough to fit; its QA report says
  so and its pivot records where the feet are (a bigger profile cell avoids it).

### Unity import

With the 2D Aseprite Importer package, select the `.aseprite` and set:
Filter Mode **Point**, Compression **None**, Max Size **at least the atlas size**, Pixels Per Unit =
your profile's cell size, Pivot **Custom** at the JSON's `pivot_norm` (for a 64 px cell,
`(0.5, 0.0156)`), Pivot Space **Canvas**. Each tag becomes a clip; one-shot actions (attack,
jump, …) are tagged to play once. (Unity behaviour of the play-once tags is not yet checked in an editor.)

### Your own character (image or character sheet)

- **One image:** Anchor tab → *import an existing image* (or `spritewaffle anchor --job <job> --image <path>`).
- **A character sheet** (several views side by side, any background, e.g. a model sheet on parchment):
  Anchor tab → *Import a character sheet*, or

  ```powershell
  spritewaffle sheet-import "C:\path\sheet.png" --job hare/courier --views S,SE,E,N --subject "hare character" --style painted
  ```

  SAM 3 (on your ComfyUI) cuts every figure off its background; `--views` names each figure's
  facing left to right, S becomes the anchor, missing W/SW/NW are mirrored, and the rest are
  generated on the Facings tab (`spritewaffle facings --only NE,NW`). Your drawings are used as-is,
  so the animation keeps your art.

### Art styles

Each job has a style (header **Style**, or `spritewaffle style --job <job> <style>`): **Pixel art** (default),
**Hand-painted**, **Anime cel**, **Comic ink**. The style changes the prompt wording and the
processing: pixel art goes through the pixelizer (grid, shared palette); the others are keyed,
despilled and scaled smoothly with soft edges at 4x the profile size (a 64 px profile cell becomes
256 px) and export as full-colour `.aseprite` / PNG. Switch, then generate a new anchor. Mirroring
works in every style; flow transfer and sprite stacking are pixel art only. New styles are one
entry in `spritewaffle/prompts/styles.py`.

### AI prompt writer (optional)

Header **Prompts → AI** (or `spritewaffle writer --job <job> ai`): a small local model (Qwen3-VL 4B, run
by ComfyUI) looks at your character and writes its description and per-action motion text, so a
goblin swings *its club* and new actions like `cast spell` work. Every reply is checked and falls
back to the fixed template wording; the rules (green background, framing, in-place motion) are
never left to the model. `spritewaffle prompts --job <job> --action walk` shows template vs AI text
without rendering.

### Effects (spells, fire, explosions, impacts)

Home → **New effect** (type `effect`). Pick a preset (fireball, explosion, magic circle, healing,
slash, lightning) or write your own first frame and motion; choose loops / once, the background,
size, frames and fps; **Render effect**. H3 draws the first frame, then a clip; the background
becomes transparency:
- **black** (glowing effects): alpha from brightness. Works with normal alpha blending and, since
  empty areas stay black, with an additive material too.
- **green** (effects with dark parts, like smoke or dust): keyed like a character. Dark smoke on
  black can't be separated from the background.

Loops skip the clip's first frames and use the window (at least 1 s) whose ends match best;
one-shots keep everything from the first to the last visible frame. Exports: strip PNG, frames,
square flipbook sheet, `.aseprite` (one-shots play once), preview GIF, JSON (fps, loop, blend).
**Re-process frames** changes size / frames / colours without rendering again.

### Variants: one change, or an item from a picture

On a character with approved facings: **Make a variant…** → describe the change ("add a long green
cape") *or* give an item picture (armor, weapon, hat) and say how it's used ("wearing this",
"holding this in the right hand"). The picture goes to H3 Image edit as a second reference (shrunk
onto a grey card, `01_anchor/item_ref.png`), so the item keeps its real design; the variant's anchor
and every facing are the base's own images with the item fitted on, so poses line up. Back views show
only the back of the item (no chest gem on the back).

### Directional sprites: manifest, camera profile, turntable

Every asset keeps a manifest (`manifest.json`): each frame's view angle in degrees (any number of
views), foot point, colour / depth / normal / high-res master files and how it was downscaled,
ready for engines that blend between angles and light sprites with maps. **Camera…** sets the
project's camera profile (or one asset's), **Mirror policy** on Facings/Animations decides which
views are flipped, **Align feet** pins every frame's foot point, and **Turntable…** spins through
the views (read-only) to spot angle-to-angle drift. Existing assets: `spritewaffle manifest`.
Details and every call: [docs/MANIFEST.md](docs/MANIFEST.md).

### Equipment items (paper doll)

New → type `item` (armor, cape, weapon). The anchor is the item on its own, front view; Facings
draws its back. Approve both, then open any character → **Make a variant…** → pick the item and say
how it's used ("wearing this"). The worn variant gets all 8 facings; the item
job keeps its original front/back and lists every character it was fitted on. Different races or
bodies are just different base characters.

For a clean body to fit items on: New → type `base body`. It's drawn as a turnaround sheet in plain
grey undershirt and shorts (all 8 views at once, like animals) and animates like any character. An
item's **Export** tab saves its front and back as game sprites (`06_export/item/`).

### Animals (four-legged)

New → type `animal`. The anchor step draws one **turnaround sheet** (front, side, back and two
three-quarter views in a row) and cuts it apart, so all 8 directions exist at once (W/SW/NW
mirrored). Actions use four-legged wording: walk (diagonal pairs), run (gallop), pounce, sit,
sleep. A side-on animal is wider than tall: use a bigger cell (Sizes…, e.g. 96 px for a 48 px
sprite); a clip that doesn't fit says which cell would.

### Spells, auras, thrown objects (effect + character)

Make the effect first (Effects above), then open the character's animation (click it on the
Animations tab) → **Effect**: pick the effect job, scrub to the frame, click where it starts,
choose *in front* / *behind* and *stays* (burst, aura) or *flies* (projectile, at N px per frame
toward the facing), **Attach + preview**. The two stay separate sprites, as games use them: the
export JSON gets an event (frame, point, layer, velocity) and the effect's files are copied into
`06_export/character/effects/`.

For a throw, write the action in **Prompts… → Actions** (e.g. "throws the shield forward…") and
set **Ends: anywhere** so the clip doesn't end with the object back in the hand; then attach the
thrown object (an effect, e.g. a spinning shield) as a projectile at the release frame.

### Prop (sprite stacking)

New → **New sprite stack** (type `prop`) → anchor (a straight front view) → approve → **Sprite
stack** → *Make 3D model + build*. Method **3D model** (default): the anchor is redrawn as a lit
3D render and TRELLIS.2 (on your ComfyUI) builds a real 3D model, which is cut into slices:
overhangs, gaps and uneven sides survive (a pine keeps its branch tiers). Method **outline carve**:
front/back/side/top outlines intersected; fine for boxy props, but hollows come out solid and the
left side mirrors the right. The viewer spins the result (tilt, layer spacing, zoom); exports: slice
strip + JSON for stacking engines, rotation sheet, spin and build-up GIFs, and `model.glb`.

### An existing clip → pixel art

```powershell
.venv\Scripts\spritewaffle run clip.mp4 --character knight --action walk --facing S
```

### Motion library (experimental)

Reuse one approved driving clip (a plain grey mannequin works best) across the whole cast:
**Animations → Source**. *flow* moves the character's own pixels (exact colours, no render,
can't turn the character); *TARA* re-renders with H3 (follows the motion better, colours can
drift — each transfer reports an identity-drift score).

## Command line

`spritewaffle -h` lists every command grouped by workflow; `spritewaffle <command> -h` explains
one. Jobs are named `<character>/<job_id>`. Errors print one line; add `--debug` for a traceback.

```powershell
spritewaffle anchor  --job knight/k1 --describe "small knight, red plume, blue tunic"
spritewaffle approve anchor --job knight/k1
spritewaffle facings --job knight/k1
spritewaffle approve facings --job knight/k1
spritewaffle animate --job knight/k1 --actions idle,walk      # queues; W/NW/SW mirrored
spritewaffle worker --once                                    # or keep the UI open
spritewaffle export-character --job knight/k1
```

## Agents (MCP)

`spritewaffle mcp` is an MCP server on stdio with `generate`, `animate`, `animate_all`, `status`,
`approve`, `export_character` and `stack`, plus the directional-sprite calls `camera_profile`,
`mirror_policy`, `manifest` and `manifest_migrate` ([docs/MANIFEST.md](docs/MANIFEST.md)). For Claude Code:

```powershell
claude mcp add spritewaffle -- "C:\path\to\spritewaffle\.venv\Scripts\spritewaffle.exe" mcp
```

The agent skill in [`skill/spritewaffle/SKILL.md`](skill/spritewaffle/SKILL.md) teaches the
workflow; approval always stays with the human.

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

Design decisions and measurements: [`DECISIONS.md`](DECISIONS.md). Audits: [`docs/AUDIT.md`](docs/AUDIT.md), [`docs/AUDIT_UI_2026-11-21.md`](docs/AUDIT_UI_2026-11-21.md).

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Every test runs in its own temporary jobs folder.
