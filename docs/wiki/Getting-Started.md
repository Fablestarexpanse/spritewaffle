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
2. In **Anchor**, use **Choose and import image…** for your own art, or describe what you want
   under **Generate with ComfyUI**. Review the preview and choose **Approve anchor**.
3. **Facings**: Generate facings (S is the anchor; E, N, W, then the diagonals from the nearest
   cardinal). Re-roll any that drift or didn't turn (warnings say which), then Approve.
4. In **Animations**, open **Generate animations**, pick facings and actions, and queue them. Each clip is rendered with
   H3 video, the frames are picked (12 and 24 frame sets), pixelized with one palette, QA'd and
   exported. W/NW/SW can be mirrored from E/NE/SE without rendering. Use **Edit timeline** on a clip to adjust its frames.
5. **Export**: one `.aseprite` (a tag per animation) plus atlas pages + TexturePacker JSON, in
   `jobs/<character>/<job_id>/06_export/`.

**Queue** in the header shows what's running. If a task fails, open **Queue → Failed** to see the
error and retry. Every re-roll keeps the previous take in **Earlier takes**.

Next: [Guide: what do you want to make?](Guide.md) walks through every other kind of asset.

## Without the UI

Run `spritewaffle --help` for CLI commands or `spritewaffle mcp` to start the stdio agent server.
See [CLI and MCP](Interfaces.md) for workflow entry points. Approval stays a human decision.
