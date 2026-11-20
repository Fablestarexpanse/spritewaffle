# SpriteWaffle

Local tool that turns AI-generated images and video into game-ready pixel-art sprites:
**character → 8 facings → animations → one `.aseprite` for Unity**, and **prop → sprite stack**.
Generation runs on your own ComfyUI (MiniMax H3 video + H3 Image); everything else — chroma key,
frame picking, pixelizing, QA, export — is built in. Nothing goes to the cloud.

## Requirements

- Windows 11 (tested), Python 3.11+, an NVIDIA GPU for ComfyUI (tested on an RTX 4090).
- ComfyUI 0.45+ at `http://127.0.0.1:8188` with the MiniMax H3 / H3 Image models. The workflows
  SpriteWaffle sends live in [`templates/`](templates/README.md).
- Frame processing (pixelize, QA, export, mirror, flow transfer, sprite stacking) works without
  ComfyUI.

## Install

```powershell
cd "F:\Tools\Sprite tool"
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
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

Each job has a style (header **Style**, or `spritewaffle style <job> <style>`): **Pixel art** (default),
**Hand-painted**, **Anime cel**, **Comic ink**. The style changes the prompt wording and the
processing: pixel art goes through the pixelizer (grid, shared palette); the others are keyed,
despilled and scaled smoothly with soft edges at 4x the profile size (a 64 px profile cell becomes
256 px) and export as full-colour `.aseprite` / PNG. Switch, then generate a new anchor. Mirroring
works in every style; flow transfer and sprite stacking are pixel art only. New styles are one
entry in `spritewaffle/prompts/styles.py`.

### AI prompt writer (optional)

Header **Prompts → AI** (or `spritewaffle writer <job> ai`): a small local model (Qwen3-VL 4B, run
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
claude mcp add spritewaffle -- "F:\Tools\Sprite tool\.venv\Scripts\spritewaffle.exe" mcp
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
templates/          ComfyUI workflows + parameter maps
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
