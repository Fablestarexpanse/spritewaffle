# Architecture

The character exporter keeps an internal receipt next to the character bundle under
`06_export/`. It records the selected frame set, QA policy, resolved FPS, and SHA-256
fingerprints for the relevant inputs and resulting files. The UI, CLI, and MCP use the
same read-only check. Generation and preprocessing have their own inputs, so a change
to a raw clip is outside this receipt until the processed frames or selection change.

Action exports reuse the receipt format and bundle lock. Each facing and action has a
receipt for PNG and one for Aseprite beside its export directory. PNG includes the
strip, previews, JSON, and individual exported frames. Aseprite also fingerprints
the index data and palette when the frames are indexed. Saved QA is read from existing
reports. The presentation derives per-frame findings from the measured fields and retains
the original pass/fail verdict for export.

The timeline keeps a versioned JSON sidecar under
`edits/animations/<facing>/<action>/<set>/`. Replacements live beside it as immutable,
content-addressed PNGs. The sidecar records the original frame fingerprint. If the processed
image changes, the saved replacement is kept and stops applying. A duration override follows
the numbered slot. The action and character writers fingerprint these effective inputs.
QA records the replacement hashes it checked, and character export uses that record when
applying its usual pass filter. The manifest refreshes on timeline saves.

Each frame keeps an ordered list of replacement hashes and the source fingerprint each
version was saved against. The active pointer in an older sidecar supplies its first known
version. Restoring the source clears the active pointer and retains history. Activating
an earlier version verifies the file hash and cell size, then records its use against the
current source. Only the active artwork and saved duration affect QA, manifests, and
exports. Onion skins use the effective frame URLs in the browser preview.

Sequence edits add an ordered list of stable IDs. Originals use their source filenames
and copies have their own IDs with pointers to the numbered source. Order undo and redo
restore sequence snapshots, while timing and artwork edits stay with their IDs. QA
records the effective order alongside replacement hashes. The exporters remap effect
events to the original slots and resolve palette indices through the same source mapping.
Re-exporting a shorter action removes surplus PNG frames that still match the previous
export receipt. A file modified outside SpriteWaffle is kept.

One Python package (`spritewaffle/`), local only. ComfyUI is the only external service; it is
driven through exported API-format workflow templates. Everything after generation is
SpriteWaffle's own code.

## Module map

| Package | Modules | Role |
|---|---|---|
| `comfy/` | `client.py`, `templates.py` | Talk to ComfyUI: upload, queue, wait, download; inject values into templates via `<slot>.map.json` |
| `core/` | `job.py` | A job folder + `job.json` (inputs, stages, provenance), locked writes |
| | `generate.py` | Anchor, facings, actions (H3 image/video); `_run` is the one place every still generation passes through |
| | `stages.py` | Extract → select → pixelize → QA → export; mirror, flow transfer, align |
| | `queue.py` | File-backed queue (`jobs/_queue/*.json`), GPU/CPU pools, retry once on GPU failure, manifest refresh after stages |
| | `variant.py`, `item.py` | One-change variants; equipment items + fitting |
| | `effect.py`, `attach.py` | Effects; effect events on character animations |
| | `profile.py`, `camera.py`, `angles.py`, `manifest.py` | Game profiles (sizes); camera profile; view angles; per-asset manifest |
| | `job_palette.py`, `takes.py`, `motion.py`, `sheet_import.py`, `prompt_view.py` | Palette, earlier takes, motion library, sheet cutting (SAM 3), prompt previews |
| `prompts/` | `builder.py`, `styles.py`, `writer.py`, `effects.py` | Prompt text (rules baked in), art styles, the Qwen3-VL prompt writer |
| `frames/` | `video.py`, `picker.py`, `analysis.py`, `layout.py`, `contact.py`, `flowtransfer.py` | Frame I/O, picking 12/24 frame sets, canvas layout + foot points, contact sheets |
| `pixel/` | `pipeline.py`, `grid.py`, `palette.py`, `quantize.py`, `cleanup.py`, `chroma.py`, `smooth.py`, `color.py` | Pixelizer: key, grid detect, palette (Oklab), hysteresis, cleanup; smooth styles |
| `qa/` | `checks.py` | Per-clip QA report |
| `export/` | `character.py`, `atlas.py`, `aseprite.py`, `sheet.py`, `showcase.py` | `.aseprite` writer, atlas pages + TexturePacker JSON, showcase GIF |
| `stack/` | `stage.py`, `carve.py`, `mesh3d.py`, `gifs.py` | Sprite stacks (TRELLIS.2 or carve) |
| `ui/` | `server.py`, `static/index.html` | FastAPI app + single-page UI (no build step) |
| | `cli.py`, `mcp_server.py`, `doctor.py`, `paths.py` | CLI, MCP server, setup check, where files live |

## Job folder

```
jobs/<character>/<job_id>/
  job.json                 inputs, stage statuses, provenance (every prompt, seed, template)
  manifest.json            directional manifest (docs/MANIFEST.md)
  01_anchor/               anchor.png (+ item.png / item_ref.png for fits, sheet/ for turnarounds)
  02_facings/              S.png … SW.png (2048 px masters), facings_report.json
  03_actions/<f>/<a>/      clip, extracted/, selected_12f|24f/ (high-res masters), selection_report.json
  04_pixel/<f>/<a>/<n>f/   frames/000.png…, placements.json, footpoints.json, frames_aligned/ (optional)
  05_qa/…                  report.json per set
  06_export/               character/ (aseprite + atlas), item/, stack/, showcase/
  takes/                   every replaced render ("earlier takes")
jobs/project.json          project id + camera profile (optional)
jobs/_queue/               queue tasks
jobs/_archive/             archived jobs (move back to restore)
```

## Templates

`templates/<slot>.json` is a ComfyUI API-format workflow; `<slot>.map.json` names its inputs
(prompt, ref_images, seed, frames…). Slots: `anchor_still`, `facing_multiref` (H3 image edit,
1–3 pictures), `h3_action_fl2va` / `h3_action_i2v` (video), `transition_pose`, `bridge_frame`,
`h3_tara_transfer`, `sam3_mask`, `trellis_mesh`, `prompt_writer` (Qwen3-VL text).
`spritewaffle comfy check` validates them against the live ComfyUI.

## Data flow (a character)

anchor (text → image) → facings (image edit, one reference picture each) → per facing × action:
transition pose → H3 video (FL2VA, falls back to I2V on a frozen clip) → extract frames → pick
12/24 (start, key beats, in-betweens, loop seam) → pixelize the union as one batch (one grid,
one palette) → preserve-canvas layout (one placement per set, feet on the pivot) → QA → export.
W/NW/SW can be flipped from E/NE/SE instead of rendered.
