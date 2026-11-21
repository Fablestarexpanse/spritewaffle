# Getting started

## Install

1. Python 3.11, Git, and a running **ComfyUI** (default `http://127.0.0.1:8188`) with the models
   and nodes in [docs/COMFYUI_SETUP.md](../COMFYUI_SETUP.md).
2. In the repo: `python -m venv .venv`, then
   `.venv\Scripts\python -m pip install -r requirements-lock.txt` (exact tested versions) and
   `.venv\Scripts\python -m pip install -e ".[dev]" --no-deps` (use `.venv/bin/` off Windows).
3. Check the setup: `spritewaffle doctor` (ComfyUI reachable, templates valid, models present).
4. Start the app: `spritewaffle ui`, then open <http://127.0.0.1:8765>.

An agent can do all of this from [AGENT_INSTALL.md](../../AGENT_INSTALL.md). Nothing assumes a
particular machine. Paths come from `SPRITEWAFFLE_HOME` / `SPRITEWAFFLE_JOBS`, or default to the repo.

## First character

1. **New → character**, name it (e.g. `knight`).
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

- CLI: `spritewaffle --help` (every stage is a command; `spritewaffle queue …` for background work).
- MCP: `spritewaffle mcp` (stdio). Tools: generate, animate, animate_all, status, approve,
  export_character, stack, camera_profile, mirror_policy, manifest, manifest_migrate.
  Approval stays a human decision.
