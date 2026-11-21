# SpriteWaffle wiki

SpriteWaffle turns AI images and video into game-ready sprites, all locally. It uses ComfyUI
(MiniMax H3 image edit and video, SAM 3, TRELLIS.2, Qwen3-VL 4B) for generation, and its own code
for everything after: keying, frame picking, pixel art, QA, atlases, `.aseprite`, manifests.

| Page | What's in it |
|---|---|
| [Getting started](Getting-Started.md) | Install, first character end to end |
| [Workflows](Workflows.md) | Characters, variants, equipment (items + base bodies), animals, effects, props / sprite stacks, styles, sizes |
| [Directional sprites](Directional-Sprites.md) | Manifest, view angles, camera profile, mirror policy, foot points, depth/normal slots, turntable |
| [Architecture](Architecture.md) | Module map, job folder layout, queue, templates, data flow |
| [Prompting lessons](Prompting-Lessons.md) | What was measured to work (and not) with H3 and the local models |
| [Development](Development.md) | Tests, conventions, how to add a stage / asset type / template, rules for agents |
| [Troubleshooting](Troubleshooting.md) | Common problems and fixes |
| [Roadmap](Roadmap.md) | What's open, in order |

Reference documents elsewhere in the repo:

- [README](../../README.md): the user guide (install, every workflow, CLI, MCP).
- [AGENTS.md](../../AGENTS.md): the short brief for coding agents (GPT, local models, Claude).
- [AGENT_INSTALL.md](../../AGENT_INSTALL.md): "give this to your agent to install".
- [docs/COMFYUI_SETUP.md](../COMFYUI_SETUP.md): ComfyUI models and custom nodes.
- [docs/MANIFEST.md](../MANIFEST.md): manifest schema and every directional call.
- [DECISIONS.md](../../DECISIONS.md): the dated log of every decision and measurement (why things are the way they are).
- [CHANGELOG.md](../../CHANGELOG.md), [docs/BACKLOG.md](../BACKLOG.md), the audits in `docs/AUDIT*.md`.

The project is licensed under [LICENSE.md](../../LICENSE.md); see [docs/LICENSING.md](../LICENSING.md).
