# CLI and MCP

[Wiki home](Home.md) · [Studio guide](Studio-Guide.md) · [Asset workflows](Workflows.md)

Use `spritewaffle --help` to list the 51 top-level commands and
`spritewaffle <command> --help` for options. Jobs use `CHARACTER/JOB` under
`SPRITEWAFFLE_JOBS`. Add `--debug` before the command for a traceback.

## Workflow entry points

| Workflow | CLI | MCP |
| --- | --- | --- |
| Jobs and preferences | `studio jobs`, `studio job`, `studio create-job`, `studio update-job`, `archive` | `status`, `studio` |
| Anchor, sheet import, facings, and actions | `anchor`, `sheet-import`, `facings`, `action`, `animate`, `approve` | `generate`, `animate`, `animate_all`, `approve`, `studio` with `run-stage` |
| Edit a view's prompt before a re-roll | `prompt --file 02_facings/NE.png --set …` | `prompt` |
| Assembly, repair, and QA | `run`, `extract`, `select`, `pixelize`, `qa`, `qa-review`, `timeline`, `align-feet`, `maps` | `animation_timeline`, `timeline_pixels`, `edit_timeline_frame`, `preview_frame_reprocess`, `preview_frame_reposition`, `align_feet`, `lighting_maps`, `studio` with `run-stage` |
| Project style, palette, and reference images | `project-style`, `project-palette`, `project-references`, `palette`, `style-check` | `project_style`, `project_palette`, `project_references`, `project_reference_image`, `palette`, `style_check` |
| Camera, mirrors, and manifests | `studio job-camera`, `studio set-job-camera`, `studio project-camera`, `studio set-project-camera`, `studio set-mirror-policy`, `manifest` | `camera_profile`, `mirror_policy`, `manifest`, `manifest_migrate` |
| Export and freshness | `export`, `export-character`, `studio export-item`, `showcase`, the four `export-…-status` commands | `export_action`, `export_character`, `showcase`, `action_export_status`, `character_export_status`, `effect_export_status`, `item_export_status` |
| Seamless textures and terrain transitions | `texture`, `transition` | `texture`, `transition` |
| Terrain, map objects, and templates | `tileset`, `tilemap` | `tileset`, `tilemap` |
| Props, effects, motion, and queue | `stack`, `motion`, `queue`, `studio` | `stack`, `studio` |

For asset-specific parameter examples, see [Asset workflows](Workflows.md). Queue
submissions need a worker to run. Run `spritewaffle worker --once` to drain queued
work, or keep the browser server open with its worker. Human approval remains
required for anchors and facings.

```powershell
spritewaffle anchor --job knight/k1 --describe "small knight, red plume, blue tunic"
spritewaffle approve anchor --job knight/k1
spritewaffle facings --job knight/k1
spritewaffle approve facings --job knight/k1
spritewaffle animate --job knight/k1 --actions idle,walk
spritewaffle worker --once
spritewaffle export-character --job knight/k1
```

Import existing art with `spritewaffle anchor --job knight/k1 --image path/to/image.png`.
For byte uploads, the shared `run-stage` operation takes `stage: "anchor"` and
`args.image_data` with the base64-encoded still image. The local app keeps the source for retries.

## Shared studio operations

The `studio` command and MCP tool use the same local handlers as the browser and
do not need a running browser server. CLI request bodies use `--file request.json`.
Use `--job CHARACTER/JOB` for job operations, `--param NAME=VALUE` for other path
parameters, and `--query NAME=VALUE` for filters. MCP accepts the equivalent
`character`, `job_id`, `body`, `parameters`, and `query` arguments and wraps the reply
in `result`. Use `studio --help` or the MCP `studio` operation `operations` to see
the supported names and, in MCP, the HTTP methods and paths.

| Area | Operations |
| --- | --- |
| Jobs | `jobs`, `job`, `create-job`, `update-job`, `archive-job`, `run-stage`, `restore-take` |
| Prompt and profile settings | `read-prompts`, `save-prompt-notes`, `profiles`, `save-profile` |
| Asset production | `create-variant`, `stack-gifs`, `configure-effect`, `attach-effect`, `export-item` |
| Camera and mirror policy | `project-camera`, `set-project-camera`, `job-camera`, `set-job-camera`, `set-mirror-policy` |
| Motion library | `motions`, `add-motion`, `approve-motion` |
| Queue | `queue`, `cancel-task`, `retry-task`, `clear-finished` |

```powershell
spritewaffle studio job --job knight/k1
spritewaffle studio update-job --job knight/k1 --file settings.json
spritewaffle studio export-item --job lantern/v1
spritewaffle studio queue --query status=failed
spritewaffle studio retry-task --param tid=TASK_ID
```

For example, `settings.json` can contain `{"prompt_writer":"template"}`.
The browser's [local OpenAPI schema](http://127.0.0.1:8765/docs) describes the
endpoint arguments when the app is running. Appearance, keyboard shortcuts,
canvas gestures, and viewport state belong to the browser. Use headless commands
or tools for the saved data and production operations behind them.

## MCP setup

`spritewaffle mcp` runs a local stdio server. For Claude Code, register the installed executable.

```powershell
claude mcp add spritewaffle -- "C:\path\to\spritewaffle\.venv\Scripts\spritewaffle.exe" mcp
```

The real stdio handshake discovered 32 tools. [Agent installation](../../AGENT_INSTALL.md)
and the [SpriteWaffle skill](../../skill/spritewaffle/SKILL.md) cover installation and workflow.
