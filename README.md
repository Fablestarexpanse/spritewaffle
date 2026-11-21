# SpriteWaffle

Local tool that turns AI-generated images and video into game-ready pixel-art sprites:
**character → 8 facings → animations → one `.aseprite` for Unity**, and **prop → sprite stack**.
Generation runs on your own ComfyUI (MiniMax H3 video + H3 Image); everything else — chroma key,
frame picking, pixelizing, QA, export — is built in. Nothing goes to the cloud.

**No AI agent needed.** The web UI and CLI do everything; the MCP server for agents is optional.

**Let an agent install it:** paste this to Claude Code, Codex, Cursor or similar:

> Install SpriteWaffle by following `AGENT_INSTALL.md` in https://github.com/Fablestarexpanse/spritewaffle. Ask me before downloading models.

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

Open <http://127.0.0.1:8765>. The header shows ComfyUI, the worker and the queue; the app runs
its own queue worker, so nothing else needs to be running.

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
   Aseprite Importer makes one clip each, plus an Animator Controller) and an atlas PNG + JSON.
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

### Prop (sprite stacking)

New → type `prop` → anchor (a straight **front** view) → approve → **Sprite stack** →
*Generate views + build*. You get a slice strip + JSON for stacking engines, a turntable GIF and an
8-angle rotation sheet. Rigid objects only: hollows come out solid, the left side mirrors the right.

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
`approve`, `export_character` and `stack`. For Claude Code:

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
| `another worker holds …` | only one worker per jobs folder; close the other UI/worker (a dead one's lock is taken over automatically) |
| Clip came out frozen | handled: re-rendered without the last frame automatically (the action shows a note) |
| TARA fails with *USE_FLASH_ATTENTION* | use the `comfy kitchen` attention backend (already set in the template) |

Design decisions and measurements: [`DECISIONS.md`](DECISIONS.md). Audit: [`docs/AUDIT.md`](docs/AUDIT.md).

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Every test runs in its own temporary jobs folder.
