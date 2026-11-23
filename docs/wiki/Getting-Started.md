# Getting started

## Install

1. Install Python 3.11 or later and Git. For generation, set up **ComfyUI** with the models
   and nodes in [the ComfyUI guide](../COMFYUI_SETUP.md). The editor and exporters also work with imported assets.
2. In the repo: `python -m venv .venv`, then
   `.venv\Scripts\python -m pip install -r requirements-lock.txt` (exact tested versions) and
   `.venv\Scripts\python -m pip install -e ".[dev]" --no-deps` (use `.venv/bin/` off Windows).
3. Check the setup: `spritewaffle doctor` (ComfyUI reachable, templates valid, models present).
4. Start the app: `spritewaffle ui`, then open <http://127.0.0.1:8765>.

An agent can do all of this from [AGENT_INSTALL.md](../../AGENT_INSTALL.md). Nothing assumes a
particular machine. Paths come from `SPRITEWAFFLE_HOME` / `SPRITEWAFFLE_JOBS`, or default to the repo.

## First character

1. Choose **New asset → Character** and give it a name such as `knight`.
2. **Anchor**: describe it ("small knight, silver helmet with a red plume, blue tunic"), Generate,
   re-roll until it's right, **Approve**. Everything else is built from this picture.
3. **Facings**: Generate facings (S is the anchor; E, N, W, then the diagonals from the nearest
   cardinal). Re-roll any that drift or didn't turn (warnings say which), then Approve.
4. **Animations**: pick facings × actions (idle, walk…), Queue. Each clip is rendered with
   H3 video, the frames are picked (12 and 24 frame sets), pixelized with one palette, QA'd and
   exported. W/NW/SW can be mirrored from E/NE/SE (no render).
5. **Export**: one `.aseprite` (a tag per animation) plus atlas pages + TexturePacker JSON, in
   `jobs/<character>/<job_id>/06_export/`.

The queue (header pill) shows what's running; it opens by itself when a task fails. Every
re-roll keeps the previous take ("earlier takes" → Use this).

## Without the UI

Run `spritewaffle --help` for CLI commands or `spritewaffle mcp` to start the stdio agent server.
See [CLI and MCP](Interfaces.md) for workflow entry points. Approval stays a human decision.
