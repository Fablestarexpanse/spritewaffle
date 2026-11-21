# AGENTS.md: brief for coding agents (GPT, Codex, local models, Claude)

SpriteWaffle turns AI images/video (local ComfyUI: MiniMax H3, SAM 3, TRELLIS.2, Qwen3-VL 4B)
into game-ready sprites. The owner is Ronan. Start with the wiki: [docs/wiki/Home.md](docs/wiki/Home.md).

## Before you change anything

1. Read line 1 of [DECISIONS.md](DECISIONS.md) (`NEXT:`: where work stands) and skim the
   entries for the area you touch. Most "odd" choices there were measured; don't undo them
   without a new measurement.
2. Read [docs/wiki/Development.md](docs/wiki/Development.md) (conventions, how to add things) and
   [docs/wiki/Prompting-Lessons.md](docs/wiki/Prompting-Lessons.md) before editing prompts.
3. Run the tests first so you know the baseline: `.venv\Scripts\python -m pytest -q`
   (about 220 tests, about 1 min, no GPU). Check the exit code, not piped output.

## Hard rules

- **Additive and backward-compatible.** Existing jobs in `jobs/` must keep loading; give new
  fields defaults. Don't change existing outputs unless asked.
- **Local only.** No new third-party services; ComfyUI is the only external dependency. No
  heavy defaults (LoRAs, new big models) without a proven improvement.
- **Humans approve** anchors and facings; never approve on your own judgement.
- **Measure, then decide.** Prompt or threshold changes need a real run; log the numbers
  in DECISIONS.md with the date.
- **Write files as UTF-8 explicitly** (Windows defaults to cp1252). Be careful with regex
  escapes in generated code.
- **Frames:** read colour frames with `frames.video.colour_frames` (`000.png…`); `_depth` /
  `_normal` maps can sit next to them.
- **Commits:** say what changed, why, and what now refuses that didn't before. Don't commit
  `jobs/`, `profiles/*.json`, `samples/`, `graft/` (gitignored).
- Keep the UI, HTTP API and MCP in step: a feature a user can do should be reachable from all three.

## Map

`spritewaffle/core` (jobs, generation, stages, queue, variants/items, camera/angles/manifest),
`prompts` (prompt text: rules baked in), `pixel` (pixelizer), `frames`, `export`, `stack`,
`ui` (FastAPI + one HTML file, no build), `cli.py`, `mcp_server.py`. Details:
[docs/wiki/Architecture.md](docs/wiki/Architecture.md). Open work: [docs/wiki/Roadmap.md](docs/wiki/Roadmap.md).

## Running

`spritewaffle doctor` (setup check), `spritewaffle ui` (app + worker on :8765),
`spritewaffle mcp` (agent tools), `spritewaffle --help` (every stage as a command). Without
ComfyUI everything after generation still works; the tests need neither.
