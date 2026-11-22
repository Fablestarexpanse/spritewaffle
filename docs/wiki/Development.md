# Development

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

About 220 tests, about 1 minute, no GPU or ComfyUI needed: generation is faked (`FakeComfy` /
`StubClient` in the tests), frames come from `tests/synth.py`. When gating a commit on the tests,
use the exit code, not `pytest | tail` (the pipe hides failures).

The pixel editor's geometry and fill tests also run with `node --test tests/pixel_editor.test.cjs`.

## Conventions

- **Additive, backward-compatible.** Old jobs must keep loading; new fields get defaults
  (see `manifest.read`). New behaviour is opt-in unless Ronan decides otherwise.
- **Measure, then decide.** A prompt or threshold change comes with a real run; the number goes
  in [DECISIONS.md](../../DECISIONS.md) (dated) and in the code comment next to the value.
- **Commit messages** say what changed, why, and what the tool now refuses that it didn't before.
- **`DECISIONS.md` line 1 is the `NEXT:` breadcrumb.** Keep it current when stopping mid-task.
- **Files:** write text as UTF-8 explicitly (the Windows default is cp1252). Be careful putting
  regexes into files through scripts: a `\b` once became a backspace character.
- **No heavy defaults** (LoRAs, big new models) unless they're a proven improvement.
- **No project-specific content in shared tooling.**
- Frame folders hold colour frames `000.png…` and maybe `000_depth.png` / `000_normal.png`. Read
  colour frames with `frames.video.colour_frames`, never `*.png`.
- **Human approval** gates anchor and facings; agents (MCP) relay a human's yes, never their own.

## Adding things

- **An asset type:** `prompts/builder.ASSET_TYPES` (subject, pose, actions); `STEPS` / `TYPES` in
  `ui/static/index.html`; route special generation in `generate.anchor` / `generate.facings`
  (see `item`, `base_body`, `animal`); default view count in `manifest.view_count`.
- **A stage:** a function in `core/stages.py` (or its own module), registered in
  `queue._stages()` (gpu or cpu dict) and `STAGE_NAMES`. Add it to `MANIFEST_STAGES` if it
  changes frames.
- **A ComfyUI template:** export the workflow in API format to `templates/<slot>.json`, write
  `<slot>.map.json`, run `spritewaffle comfy check`, and add the models to
  `docs/COMFYUI_SETUP.md`.
- **A UI feature:** `ui/server.py` endpoint and `index.html` (plain JS, no build). Mirror it as
  an MCP tool in `mcp_server.py` when an agent should be able to do it. Check in the browser at
  1440 and 800 px wide.

## Run it

`spritewaffle ui` (app + worker), `spritewaffle worker` (worker only), `spritewaffle mcp`
(agents). Only one worker per jobs folder (a lock file; a dead worker's lock is taken over).
