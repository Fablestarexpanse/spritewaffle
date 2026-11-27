"""SpriteWaffle MCP server (stdio): generate, animate, status, approve.

Tools only queue work; the queue worker runs inside this process unless another worker (the web
UI or `spritewaffle worker`) already holds the queue. Approval stays a human decision: the
approve tool is for relaying a yes the human gave after looking at the output.
"""

import io
import json
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage
from pydantic import StrictInt

from . import paths
from .core import generate as gen
from .core import job_palette, project, project_references as references
from .core.job import Job
from .core.profile import resolve
from .core.queue import Queue, Worker
from .prompts import builder, styles

ORDER = ("S", "E", "N", "W", "SE", "NE", "NW", "SW")


def build(base: str | Path | None = None) -> tuple[FastMCP, Queue]:
    base = (Path(base) if base else paths.jobs()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    q = Queue(base)
    mcp = FastMCP("spritewaffle", instructions=(
        "Turns a character description into game-ready pixel-art sprite sets via the local ComfyUI. "
        "Order: generate(stage='anchor') -> show the anchor to the human -> approve('anchor') only after "
        "they say yes -> generate(stage='facings') -> human approves -> approve('facings') -> animate(...) "
        "per facing/action. Use status(wait_seconds=...) to wait for queued work and include_images to see "
        "results. Hero asset first: make and approve one hero, then pass its job as style_ref for others."))

    def job_for(character: str, job_id: str) -> Job:
        root = (base / character / job_id).resolve()
        if base not in root.parents or not (root / "job.json").exists():
            raise ValueError(f"no job {character}/{job_id}")
        return Job(root)

    def thumb(p: Path, size: int = 512) -> Image:
        im = PILImage.open(p).convert("RGBA")
        im.thumbnail((size, size), PILImage.NEAREST)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return Image(data=buf.getvalue(), format="png")

    def open_tasks(job: Job | None = None) -> list[dict]:
        ts = q.list()
        if job:
            ts = [t for t in ts if Path(t["job"]).resolve() == job.root]
        return [t for t in ts if t["status"] in ("queued", "running")]

    @mcp.tool()
    async def studio(operation: str, character: str | None = None, job_id: str | None = None,
                     parameters: dict | None = None, body: dict | None = None, query: dict | None = None) -> dict:
        """Run a named local studio operation using the browser's validation.

        Pass operation='operations' to list supported operations, methods, and paths.
        Supply character and job_id together for a job operation. Other path parameters
        are named in the operation path. Writes take a JSON body. Calls never start a worker.
        """
        from .studio import OPERATIONS, invoke

        if operation == "operations":
            return {"result": {name: {"method": method, "path": path} for name, (method, path) in OPERATIONS.items()}}
        params = dict(parameters or {})
        if character is not None or job_id is not None:
            if not character or not job_id or params.keys() & {"char", "jid"}:
                raise ValueError("Supply character and job_id together or as explicit path parameters.")
            params.update(char=character, jid=job_id)
        return {"result": await invoke(base, operation, parameters=params, body=body, query=query)}

    @mcp.tool()
    def generate(character: str, stage: str = "anchor", description: str | None = None,
                 job_id: str | None = None, asset_type: str | None = None, style_ref: str | None = None,
                 image: str | None = None, seed: int | None = None, only: list[str] | None = None,
                 style: str | None = None, profile: str | None = None, project_reference_id: str | None = None,
                 project_reference_ids: list[str] | None = None) -> dict:
        """Queue a still-image stage.

        stage='anchor': creates the job when job_id is omitted. Needs `description` (or `image`, a path
        to import). asset_type: character | creature | prop | item. Omit it to keep the saved job type.
        style_ref: an approved hero as
        'character/job_id' (or an image path) to draw this asset in the hero's style.
        project_reference_id selects one active project library image instead of style_ref. Item anchors
        take only colour cues from either reference and draw the described object on its own.
        project_reference_ids: 2-3 project library images used together; the anchor takes the style
        they share (instead of one picture's), e.g. three characters drawn in the game's style.
        stage='facings': needs an approved anchor; `only` re-rolls specific facings, e.g. ['SW'].
        style (anchor and sheet): pixel, painted, anime, or comic. Omit style and profile to use the
        project defaults on new assets. Pass profile='' for built-in sizes.
        stage='sheet': import the human's own character sheet: image=<path>, only=<facing of each figure
        left to right, e.g. ['S','SE','E','N']>, description=<what to cut out, e.g. 'hare character'>.
        Returns the job and queued task ids; call status(...) to follow progress."""
        if stage not in ("anchor", "facings", "sheet"):
            raise ValueError("stage must be 'anchor', 'facings' or 'sheet'")
        existing = job_for(character, job_id) if job_id else None
        asset_type = gen.anchor_asset_type(existing, asset_type) if existing else asset_type or "character"
        if project_reference_id is not None:
            if stage != "anchor":
                raise ValueError("A project reference can only be selected for the anchor stage.")
            gen.anchor_reference(base, project_reference_id, description=description, asset_type=asset_type,
                                 image=image, style_ref=style_ref)
        if project_reference_ids:
            if stage != "anchor":
                raise ValueError("A style set can only be used for the anchor stage.")
            gen.style_set(base, project_reference_ids, description=description, asset_type=asset_type, image=image,
                          style_ref=style_ref, project_reference_id=project_reference_id)
        inputs = {}
        if stage != "facings" and style:
            inputs["style"] = styles.get(style)["name"]
        if stage != "facings" and profile is not None:
            resolve(profile)
            inputs["profile"] = profile or None
        if stage == "sheet":
            if not image or not only:
                raise ValueError("sheet: pass image=<sheet path> and only=<facing of each figure, left to right>")
            job = existing or Job.create(character, base=base, asset_type=asset_type, **inputs)
            args = {"image": image, "views": only, "subject": description or "character"}
        elif stage == "anchor":
            builder.asset(asset_type)
            job = existing or Job.create(character, base=base, asset_type=asset_type, **inputs)
            args = {"describe": description, "image": image, "seed": seed, "asset_type": asset_type,
                    "project_reference_id": project_reference_id,
                    **({"project_reference_ids": list(project_reference_ids)} if project_reference_ids else {})}
            if style_ref:
                ref = base / style_ref if "/" in style_ref and not Path(style_ref).exists() else Path(style_ref)
                args["style_ref"] = str(ref)
        else:
            if existing is None:
                raise ValueError("facings needs job_id")
            job = existing
            args = {"seed": seed, "only": only}
        if job_id and inputs:
            with job.mutate() as meta:
                meta["inputs"].update(inputs)
        t = q.submit(job.root, stage, {k: v for k, v in args.items() if v is not None},
                     profile=job.read_meta()["inputs"].get("profile"))
        return {"character": character, "job_id": job.root.name, "tasks": [t["id"]]}

    @mcp.tool()
    def animate(character: str, job_id: str, facing: str, action: str, seconds: float = 2.0,
                seed: int | None = None, reprocess_only: bool = False, motion: str | None = None,
                method: str = "tara") -> dict:
        """Queue an action for one facing: transition pose -> H3 clip -> frame selection -> pixelize ->
        QA -> export (PNG strip, .aseprite with tag, GIF). Needs approved facings.
        facing: S E N W SE NE NW SW. action: idle walk run attack jump.
        reprocess_only=True re-runs selection..export on the existing clip without a new render.
        motion=<approved library motion> (EXPERIMENTAL): transfer that clip's motion with TARA instead of
        rendering with H3; check identity_drift in status and fall back to H3 when it warns.
        method='flow' (with motion): pixel-exact transfer by optical flow, no render, identity exact,
        but it can only move the facing's existing pixels (no turns, no unseen parts)."""
        job = job_for(character, job_id)
        if facing not in ORDER:
            raise ValueError(f"facing must be one of {ORDER}")
        if action not in builder.ACTIONS and job.read_meta()["inputs"].get("prompt_writer") != "ai":
            builder.action_spec(action)                       # raises with the list of presets
        if not reprocess_only and job.read_meta()["stages"].get("facings", {}).get("status") != "approved":
            raise ValueError("facings are not approved yet; show them to the human first")
        if motion:
            from .core import motion as motion_lib
            m = motion_lib.get(motion, base)
            if m["status"] != "approved":
                raise ValueError(f"motion '{motion}' is not approved")
            args = {**({"seed": seed} if seed is not None else {})}
        else:
            args = {"seconds": seconds, **({"seed": seed} if seed is not None else {})}
        if method not in ("tara", "flow"):
            raise ValueError("method must be 'tara' or 'flow'")
        ts = q.submit_action_pipeline(job.root, facing, action, profile=job.read_meta()["inputs"].get("profile"),
                                      generate=not reprocess_only, motion=motion,
                                      method=method, **args)
        return {"character": character, "job_id": job_id, "tasks": [t["id"] for t in ts]}

    @mcp.tool()
    def export_character(character: str, job_id: str, frame_set: str = "12f", include_failed: bool = False,
                         max_size: int = 4096, mirror: str = "pack", pot: bool = False, extrude: int = 0) -> dict:
        """Bundle every QA-passed animation of a job into ONE .aseprite (a tag per facing x action, so
        Unity's Aseprite Importer makes one clip each) plus atlas pages. Defaults to a
        4096 px page limit and packed facings. Mirror 'flip' allows supported engine flips.
        Include_failed explicitly opts into frames with failed QA. pot: power-of-two pages; extrude:
        repeat sprite edges 0-4 px for bilinear filtering / mip maps. Returns files and skipped actions."""
        from .core.profile import resolve
        from .export import character as char_export
        job = job_for(character, job_id)
        prof = resolve(job.read_meta()["inputs"].get("profile"))
        out = char_export.export(job.root, job.stage_dir("06_export") / "character", character, prof.fps, frame_set,
                                 require_pass=not include_failed, max_size=max_size, mirror=mirror, profile=prof,
                                 pot=pot, extrude=extrude)
        job.set_stage("export:character", "done", **{k: out[k] for k in ("animations", "skipped", "mode", "colours")})
        return out

    @mcp.tool()
    def character_export_status(character: str, job_id: str) -> dict:
        """Check the latest character bundle for changed processing, alignment, or export files."""
        from .core.profile import resolve
        from .export import character as char_export
        job = job_for(character, job_id)
        profile = resolve(job.read_meta()["inputs"].get("profile"))
        return char_export.export_status(job.root, job.root / "06_export" / "character", profile.fps, profile=profile)

    @mcp.tool()
    def align_feet(character: str, job_id: str, facing: str | None = None, action: str | None = None) -> dict:
        """Queue a local rebuild of foot-aligned copies. Omit facing and action to align the whole job."""
        job = job_for(character, job_id)
        args = {key: value for key, value in (("facing", facing), ("action", action)) if value is not None}
        task = q.submit(job.root, "align", args, profile=job.read_meta()["inputs"].get("profile"))
        return {"tasks": [task["id"]]}

    @mcp.tool()
    def lighting_maps(character: str, job_id: str, facing: str | None = None, action: str | None = None) -> dict:
        """Queue depth + normal maps (Depth Anything V2 small on the GPU) for every pixelized clip, or
        one facing/action. Written next to each frame as NNN_depth.png / NNN_normal.png and listed in
        the manifest."""
        job = job_for(character, job_id)
        tasks = q.submit_maps(job.root, job.read_meta()["inputs"].get("profile"), facing, action)
        return {"tasks": [t["id"] for t in tasks]}

    @mcp.tool()
    def export_action(character: str, job_id: str, facing: str, action: str, format: str = "both") -> dict:
        """Export processed frames for one facing and action. Format is png, aseprite, or both."""
        from .core import stages
        from .core.profile import resolve
        job = job_for(character, job_id)
        return stages.export(job, resolve(job.read_meta()["inputs"].get("profile")), facing, action, format)

    @mcp.tool()
    def item_export_status(character: str, job_id: str) -> dict:
        """Check the last item export against its current views, profile settings, and files."""
        from .core import item
        job = job_for(character, job_id)
        return item.export_status(job, resolve(job.read_meta()["inputs"].get("profile")))

    @mcp.tool()
    def effect_export_status(character: str, job_id: str) -> dict:
        """Check the last effect export against its saved clip, processing settings, and files."""
        from .core import effect
        return effect.export_status(job_for(character, job_id))

    @mcp.tool()
    def action_export_status(character: str, job_id: str, facing: str, action: str) -> dict:
        """Check the PNG and Aseprite exports of one facing and action for changed or missing files."""
        from .core import stages
        from .core.profile import resolve
        job = job_for(character, job_id)
        return stages.export_status(job, resolve(job.read_meta()["inputs"].get("profile")), facing, action)

    @mcp.tool()
    def animation_timeline(character: str, job_id: str, facing: str, action: str, frame_set: str = "12f") -> dict:
        """Read the effective frames and timing of one processed animation."""
        from .core import timeline
        from .core.profile import resolve
        job = job_for(character, job_id)
        directory = timeline.directory(job.root, facing, action, frame_set)
        return timeline.describe(job.root, directory, resolve(job.read_meta()["inputs"].get("profile")).fps(action))

    @mcp.tool()
    def timeline_pixels(character: str, job_id: str, facing: str, action: str, frame: str,
                        frame_set: str = "12f", include_pixels: bool = False) -> dict:
        """Read the frame fingerprint, cell size, palette, and optionally base64 row-major RGBA bytes."""
        from .core import timeline
        job = job_for(character, job_id)
        directory = timeline.directory(job.root, facing, action, frame_set)
        return timeline.describe_pixels(job.root, directory, frame, include_pixels=include_pixels)

    @mcp.tool()
    def preview_frame_reprocess(character: str, job_id: str, facing: str, action: str, frame: str,
                                frame_set: str = "12f", despill: str = "profile", include_png: bool = False) -> dict:
        """Compare one retained frame locally. Optionally include the two images as base64 PNGs."""
        from .core import frame_repair, timeline

        job = job_for(character, job_id)
        directory = timeline.directory(job.root, facing, action, frame_set)
        return frame_repair.preview(job.root, directory, frame, despill=despill, include_png=include_png)

    @mcp.tool()
    def preview_frame_reposition(character: str, job_id: str, facing: str, action: str, frame: str,
                                 frame_set: str = "12f", dx: StrictInt = 0, dy: StrictInt = 0,
                                 reference: str | None = None, axes: str = "vertical", include_png: bool = False) -> dict:
        """Compare a whole-pixel shift or align to a different frame's foot point."""
        from .core import frame_repair, timeline

        job = job_for(character, job_id)
        directory = timeline.directory(job.root, facing, action, frame_set)
        return frame_repair.preview_reposition(job.root, directory, frame, dx=dx, dy=dy, reference=reference,
                                                axes=axes, include_png=include_png)

    @mcp.tool()
    def edit_timeline_frame(character: str, job_id: str, facing: str, action: str, operation: str,
                            frame: str | None = None, frame_set: str = "12f",
                            duration_ms: int | None = None, png_path: str | None = None,
                            version: int | None = None, position: int | None = None,
                            fingerprint: str | None = None, pixels: list[list[StrictInt]] | None = None,
                            playback: dict | None = None, tag_id: str | None = None, tag: dict | None = None,
                            despill: str = "profile", dx: StrictInt = 0, dy: StrictInt = 0,
                            reference: str | None = None, axes: str = "vertical",
                            pose_markers: list[str] | None = None) -> dict:
        """Playback takes a mode (source, loop, once) and optional start_frame and end_frame IDs.
        Paint takes a fingerprint and [x, y, r, g, b, a] rows. Move uses a zero-based position.
        Insert takes a PNG path and inserts after frame. Insert_blank adds a transparent frame.
        Remove hides a frame. Undo and redo reverse sequence edits.
        Save_tag takes name, start_frame, end_frame, loop in tag, with a tag_id to update.
        Remove_tag uses tag_id. Reprocess applies a comparison with its fingerprint and despill mode.
        Reposition applies a comparison with its fingerprint, plus dx and dy or a reference and axes.
        Pose replaces the selected frame's markers with pose_markers. An empty list clears them."""
        from .core import timeline
        job = job_for(character, job_id)
        directory = timeline.directory(job.root, facing, action, frame_set)
        value = duration_ms
        if operation in ("replace", "insert"):
            if not png_path:
                raise ValueError("Pass the PNG path in png_path.")
            with Path(png_path).open("rb") as stream:
                value = stream.read(timeline.MAX_IMAGE_BYTES + 1)
        elif operation == "activate":
            value = version
        elif operation == "move":
            value = position
        elif operation == "paint":
            value = {"fingerprint": fingerprint, "pixels": pixels}
        elif operation == "reprocess":
            value = {"fingerprint": fingerprint, "despill": despill}
        elif operation == "reposition":
            value = {"fingerprint": fingerprint, "dx": dx, "dy": dy, "reference": reference, "axes": axes}
        elif operation == "playback":
            value = playback
        elif operation == "save_tag":
            value = tag
        elif operation == "pose":
            value = pose_markers
        target = tag_id if operation in timeline.TAG_OPERATIONS else frame
        selected = timeline.update(job.root, directory, target, operation, value)
        return animation_timeline(character, job_id, facing, action, frame_set) | timeline.selected_result(operation, selected)

    @mcp.tool()
    def showcase(character: str, job_id: str, size: int = 512) -> dict:
        """GIF for showing the character to people: a turnaround through its facings, then each saved
        action with all its facings playing in a compass grid. Returns the file path."""
        from .core.profile import resolve
        from .export import showcase as sc
        job = job_for(character, job_id)
        return sc.for_job(job, resolve(job.read_meta()["inputs"].get("profile")), size=max(256, min(1024, size)))

    @mcp.tool()
    def stack(character: str, job_id: str, height: int = 24, regenerate_views: bool = True,
              seed: int | None = None) -> dict:
        """Sprite stacking for a rigid prop/vehicle (approved anchor = front view): queue orthographic
        back/right/top views, then carve them into `height` horizontal slices + turntable GIF + an
        8-angle rotation sheet. regenerate_views=False rebuilds from existing views (CPU only, seconds).
        Hollow shapes come out solid; the left side mirrors the right."""
        job = job_for(character, job_id)
        if regenerate_views and job.read_meta()["stages"].get("anchor", {}).get("status") != "approved":
            raise ValueError("the anchor is not approved yet; show it to the human first")
        ts = q.submit_stack_pipeline(job.root, profile=job.read_meta()["inputs"].get("profile"),
                                     views=regenerate_views, height=height, seed=seed)
        return {"character": character, "job_id": job_id, "tasks": [t["id"] for t in ts]}

    @mcp.tool()
    def animate_all(character: str, job_id: str, actions: list[str], facings: list[str] | None = None,
                    mirror: bool = True, seconds: float = 2.0) -> dict:
        """Queue many facings x actions at once (default: all 8 facings). With mirror=True, W/NW/SW
        are flipped from E/NE/SE (exact pixels, no render). Needs approved facings."""
        job = job_for(character, job_id)
        facings = facings or list(ORDER)
        bad = [f for f in facings if f not in ORDER]
        if bad:
            raise ValueError(f"unknown facings {bad}")
        if job.read_meta()["inputs"].get("prompt_writer") != "ai":
            for a in actions:
                builder.action_spec(a)
        if job.read_meta()["stages"].get("facings", {}).get("status") != "approved":
            raise ValueError("facings are not approved yet; show them to the human first")
        ts = q.submit_animate(job.root, facings, actions, profile=job.read_meta()["inputs"].get("profile"),
                              mirror=mirror, seconds=seconds)
        return {"character": character, "job_id": job_id, "tasks": len(ts),
                "mirrored": sorted({t["args"]["facing"] for t in ts if t["stage"] == "mirror"})}

    @mcp.tool()
    def project_style(action: str = "get", style: dict | None = None) -> dict:
        """Get or patch the jobs folder's style guide. Actions are get, set, and clear.
        Set accepts default_style, default_profile, target_engine, and art_direction.
        New jobs inherit omitted defaults and save a snapshot alongside their asset metadata."""
        if action == "get":
            return project.style(base)
        if action == "set" and style is not None:
            return project.set_style(base, style)
        if action == "clear":
            return project.set_style(base, None)
        raise ValueError("Use action='get', action='set' with a style object, or action='clear'")

    @mcp.tool()
    def project_palette(action: str = "get", colours: list[str] | None = None, file: str | None = None) -> dict:
        """Read or set the master palette used by future jobs. Set takes #RRGGBB colours.
        Import takes a local palette file and clear removes the default for future jobs."""
        if action == "get":
            return {"colours": project.palette(base)}
        if action == "set" and colours is not None:
            return {"colours": project.set_palette(base, colours)}
        if action == "import" and file:
            return {"colours": project.set_palette(base, job_palette.load_file(file))}
        if action == "clear":
            return {"colours": project.set_palette(base, None)}
        raise ValueError("Use get, set with colours, import with file, or clear")

    @mcp.tool()
    def palette(character: str, job_id: str, action: str = "get", colours: list[str] | None = None) -> dict:
        """Read the effective asset palette. Set provides an asset override as #RRGGBB colours.
        Unlock clears that override, revealing the saved project palette or automatic fitting."""
        job = job_for(character, job_id)
        if action == "set" and colours is not None:
            job_palette.save(job, colours, "job override")
        elif action == "unlock":
            job_palette.clear(job)
        elif action != "get":
            raise ValueError("Use get, set with colours, or unlock")
        return job_palette.current(job, resolve(job.read_meta()["inputs"].get("profile"))) or {}

    @mcp.tool()
    def tileset(character: str, job_id: str, operation: str = "inspect", path: str | None = None,
                grid: dict | None = None, tile: int | None = None, solid: bool = True,
                revision: str | None = None, terrain: dict | None = None,
                vertices: list[list[str | None]] | None = None, frames: list[dict] | None = None,
                overrides: dict | None = None, override_atlas: str | None = None, allow_unknown: bool = False,
                module: dict | None = None, shape: dict | None = None, properties: dict | None = None,
                weight: float | None = None) -> dict:
        """Import, inspect, edit, preview, or export a local PNG tileset.

        Import takes a local path and grid with tile_width, tile_height, margin and spacing.
        Collision takes a zero-based tile ID and solid true or false. Pass a revision to guard edits.
        Optional shape for a solid tile: {"shape": full | half_bottom | half_top | slope_up | slope_down |
        slope_up_low | slope_up_high | slope_down_low | slope_down_high} or {"points": [[x, y], ...]} in
        tile pixels (top-left origin), plus "one_way": true for jump-through platforms.
        Properties takes a tile ID and properties {name: bool | int | float | text}; {} clears them.
        Weight takes a tile ID and weight: how often Tiled picks it among tiles that fit the same place
        (random brush, terrain fill), exported as the tile's probability. 1 is normal, 0 never; null resets.
        Terrain takes colors (named terrains) and tiles (ID keys with NW, NE, SE, SW names or null).
        Animation takes a tile ID and ordered frames with tile and duration_ms. Pass [] to clear.
        Preview resolves cells from a rectangular vertex lattice of terrain names or null.
        It accepts manual cell overrides and their atlas binding from a saved map.
        Module takes a module object with name, start, and end atlas corner IDs.
        Stamp takes a module object with name, cell, vertices, and optional overrides,
        override_atlas, and revision. It returns overrides for the map draft.
        Export-module takes a saved module name and optional pivot [x, y] in the module argument.
        Export writes the PNG and two metadata files to the job's 06_export/tileset folder.
        """
        from .core import tileset as workspace

        if operation == "import":
            if not path or grid is None:
                raise ValueError("Import requires a local PNG path and grid.")
            job = workspace.create(base, character, job_id)
            return workspace.import_file(job, Path(path), grid)
        job = job_for(character, job_id)
        if operation == "inspect":
            return workspace.inspect(job)
        if operation == "collision":
            return workspace.collision(job, tile, solid, revision, shape)
        if operation == "properties":
            return workspace.properties(job, tile, properties or {}, revision)
        if operation == "weight":
            return workspace.probability(job, tile, weight, revision)
        if operation == "export":
            return workspace.export(job)
        if operation == "terrain":
            return workspace.update_terrain(job, terrain, revision)
        if operation == "animation":
            return workspace.update_animation(job, tile, frames, revision)
        if operation == "preview":
            return workspace.preview(job, vertices, revision, allow_unknown=allow_unknown,
                                     overrides=overrides, override_atlas=override_atlas)
        if operation == "module":
            options = module or {}
            return workspace.save_module(job, options.get("name"), options.get("start"), options.get("end"), revision)
        if operation == "stamp":
            options = module or {}
            return workspace.stamp(job, options.get("name"), options.get("cell"), options.get("vertices"),
                                   options.get("overrides"), options.get("override_atlas"), options.get("revision", revision))
        if operation == "export-module":
            from .core import tile_module_export
            options = module or {}
            return tile_module_export.export(job, options.get("name"), options.get("pivot"), options.get("revision", revision))
        raise ValueError("Choose import, inspect, collision, terrain, animation, preview, module, stamp, export-module, or export.")

    @mcp.tool()
    def tilemap(character: str, job_id: str, operation: str = "list", map_id: str | None = None,
                name: str | None = None, vertices: list[list[str | None]] | None = None,
                revision: str | None = None, tileset_revision: str | None = None,
                overrides: dict | None = None, override_atlas: str | None = None,
                objects: list[dict] | None = None, template_id: str | None = None,
                template: dict | None = None, placement: dict | None = None,
                allow_empty: bool = False, mix: bool | None = None, layers: list[dict] | None = None) -> dict | list[dict]:
        """Manage named terrain maps and reusable object templates in a tileset job.

        Save takes a name and a rectangular lattice of terrain names or null. Updates need
        the map ID and loaded revision. Export writes a portable ZIP to the job; it refuses
        unresolved cells unless allow_empty is true (they are then left empty).
        mix (save): true picks among terrain variants (tiles with the same corners) per cell by
        tile weight (tileset weight); false uses the first; omitted keeps the saved choice.
        layers (save): up to 4 extra tile layers above the terrain, [{"name": "Decor", "tiles": {"12": 5}}]
        (cell ID -> atlas tile ID), bottom first; [] removes them, omitted keeps them. They export as
        extra Tiled tile layers and LDtk Tiles layers.
        Overrides map row-major cell IDs to atlas tile IDs or null. An empty object clears
        overrides. Pass the loaded override_atlas to retain its source binding.
        Objects have an id, name, kind, cell, state, and list of named atlas states.
        Pass [] to clear them and retain each loaded atlas binding when updating.
        Templates lists reusable definitions. Save-template takes a template with name,
        kind, state, and states. Instantiate-template takes a template_id and placement
        with cell and optional state. It returns an object draft for the map's objects list.
        """
        from .core import object_templates
        from .core import tilemap as maps

        job = job_for(character, job_id)
        if operation == "list":
            return maps.list_maps(job)
        if operation == "load":
            return maps.load(job, map_id)
        if operation == "save":
            return maps.save(job, name, vertices, map_id, revision, tileset_revision,
                             overrides=overrides, override_atlas=override_atlas, objects=objects, mix=mix, layers=layers)
        if operation == "export":
            return maps.export(job, map_id, revision, tileset_revision, allow_empty=allow_empty)
        if operation == "templates":
            return object_templates.list_templates(job)
        if operation == "save-template":
            return object_templates.save(job, template)
        if operation == "instantiate-template":
            options = placement or {}
            return object_templates.instantiate(job, template_id, options.get("cell"), options.get("state"))
        raise ValueError("Choose list, load, save, export, templates, save-template, or instantiate-template.")

    @mcp.tool()
    def project_references(action: str = "list", reference_id: str | None = None, path: str | None = None,
                           fields: dict | None = None, include_archived: bool = False) -> dict:
        """Manage images in the local project's reference library. List hides archived images by default.
        Add takes a local path and optional name, collection, and notes in fields.
        Update takes a reference ID and fields to patch. Set archived=true to hide or false to restore.
        Use project_reference_image to look at a reference."""
        if action == "list":
            return {"references": references.list_all(base, include_archived)}
        if action == "add" and path:
            details = fields or {}
            if details.keys() - references.TEXT_LIMITS.keys():
                raise ValueError("Add fields are name, collection, and notes")
            return references.import_file(base, Path(path), **details)
        if action == "update" and reference_id and fields is not None:
            return references.update(base, reference_id, fields)
        raise ValueError("Use list, add with path, or update with reference_id and fields")

    @mcp.tool()
    def project_reference_image(reference_id: str) -> Image:
        """Show a preview of a local project reference by stable ID."""
        return thumb(references.image(base, reference_id, thumbnail=True))

    @mcp.tool()
    def camera_profile(action: str = "get", camera: dict | None = None, character: str | None = None,
                       job_id: str | None = None, project_id: str | None = None) -> dict:
        """Camera profile (elevation, framing, character_scale, light, background, border, style notes).
        Without character/job_id: the project's (jobs folder) profile; with them: one asset's override.
        action='get' reads; action='set' writes `camera` (only the fields to set; camera=None clears).
        Fields: camera_elevation_degrees, framing, character_scale, light_yaw, light_elevation,
        background_mode (green|black|transparent), canvas_border_px, style_notes."""
        from dataclasses import asdict

        from .core import camera as cam
        from .core import manifest
        if action not in ("get", "set"):
            raise ValueError("action must be 'get' or 'set'")
        if character and job_id:
            job = job_for(character, job_id)
            if action == "set":
                cam.set_asset(job, camera)
                manifest.refresh(job)
            return {"effective": cam.snapshot(job), "override": job.read_meta()["inputs"].get("camera")}
        if action == "set":
            cam.set_project(base, camera, project_id)
        return cam.project(base) | {"defaults": asdict(cam.CameraProfile())}

    @mcp.tool()
    def mirror_policy(character: str, job_id: str, policy: str, mirror_map: dict | None = None) -> dict:
        """Per-asset mirror policy: legacy (today's per-run choices, the default), none (never flip;
        use for asymmetric characters: shield arm, eyepatch, emblem), mirror_left_from_right (render S,
        N and the right-facing half, flip the left half), custom (mirror_map {"<view_index>": source})."""
        from .core import manifest
        return manifest.set_mirror_policy(job_for(character, job_id), policy, mirror_map)

    @mcp.tool()
    def style_check(character: str, job_id: str) -> dict:
        """Read-only comparison of an asset and processed clips against the current project style and palette."""
        from .qa import style_check as check
        return check.inspect(job_for(character, job_id))

    @mcp.tool()
    def manifest(character: str, job_id: str, rebuild: bool = False) -> dict:
        """The asset manifest (docs/MANIFEST.md): views by yaw, every frame's angle, foot point,
        colour/depth/normal/master paths and downscale record, camera snapshot, mirror policy."""
        from .core import manifest as mf
        job = job_for(character, job_id)
        if rebuild:
            mf.write(job)
        return mf.read(job)

    @mcp.tool()
    def texture(character: str, job_id: str = "t1", action: str = "status", description: str | None = None,
                tile_size: int | None = None, variants: int | None = None, colours: int | None = None,
                style: str | None = None, only: list[int] | None = None, seed: int | None = None,
                shared_edges: bool | None = None, surface_maps: bool | None = None,
                surface_strength: float | None = None) -> dict:
        """Seamless tileable textures (ground, walls, water). action: 'setup' (creates the job, saves
        settings), 'generate' (queues every variant, or `only` = 1-based variant numbers to re-roll),
        'retile' (queues re-cutting tiles at a new tile_size/colours, no render), 'status',
        'export' and 'to_tileset' (need the human's approval first: approve(character, job_id,
        'texture')). Each variant is seamed in code and gets a wrap score (about 1.0 = seamless).
        shared_edges: every variant takes variant 1's border (tone-matched, joined on least-visible cuts) so any
        two variants fit side by side; cross_score in the status is the worst join between different variants.
        surface_maps: export also writes a height and a normal map (OpenGL, green up) per tile and as sheets,
        estimated from the colour and seamless like the tile; surface_strength (0.25-16, default 2) sets the slope."""
        from .core import texture as tx
        root = base / character / job_id
        job = Job.open(root) if (root / "job.json").exists() else Job.create(character, job_id, base=base,
                                                                              asset_type=tx.TYPE, style=style or "pixel")
        if job.read_meta()["inputs"].get("asset_type") != tx.TYPE:
            raise ValueError(f"{character}/{job_id} is not a texture job")
        s = tx.configure(job, description=description, tile_size=tile_size, variants=variants, colours=colours, style=style,
                         shared_edges=shared_edges, surface_maps=surface_maps, surface_strength=surface_strength)
        if action == "generate":
            if not s["description"]:
                raise ValueError("give a description first")
            t = q.submit(job.root, "texture", {"only": [int(x) - 1 for x in only]} if only else ({"seed": seed} if seed is not None else {}))
            return {"queued": t["id"], "settings": s}
        if action == "retile":
            return {"queued": q.submit(job.root, "texture_retile", {})["id"], "settings": s}
        if action == "export":
            return tx.export(job)
        if action == "to_tileset":
            return tx.to_tileset(job)
        rp = job.root / "02_facings" / "texture_report.json"
        return {"settings": s, "stage": job.read_meta()["stages"].get("texture"),
                "variants": json.loads(rp.read_text())["variants"] if rp.exists() else {}}

    @mcp.tool()
    def transition(a: str, b: str, names: list[str] | None = None, tile_size: int | None = None, roughness: float = 0.5,
                   seed: int = 0, variant_a: int = 1, variant_b: int = 1, name: str | None = None,
                   job_id: str | None = None, kind: str = "corner", band: float | None = None) -> dict:
        """Terrain transition: two approved seamless texture jobs ('character/job_id') -> a tileset job
        with the 16-tile corner set (every corner combination) and its corner terrain rules filled in,
        ready for the terrain map preview and Tiled export. roughness 0 (straight border) .. 1 (ragged).
        kind 'corner' (16 tiles), 'blob' (47 blob tiles + plain, painted in Tiled/Godot) or 'edge' (16 path
        tiles: b is the path on ground a, every N/E/S/W combination; painted in Tiled/Godot). band: darker
        lip on the lower terrain in px. Variants are 1-based."""
        from .core import transition as tr
        ja, jb = (job_for(*x.split("/", 1)) for x in (a, b))
        return tr.make(ja, jb, name, job_id, tuple(names) if names else None, tile_size, roughness, seed,
                       variant_a - 1, variant_b - 1, kind, band)

    @mcp.tool()
    def manifest_migrate(rebuild: bool = False, limit: int = 0) -> dict:
        """Write manifests for jobs that have none (rebuild=True: all). limit > 0 stops after that
        many writes, so very large projects can be migrated in batches."""
        from .core import manifest as mf
        counts, failed = {}, []
        for job, st in mf.migrate(base, rebuild=rebuild):
            k = st.split(":")[0]
            counts[k] = counts.get(k, 0) + 1
            if k == "failed":
                failed.append(f"{job.root.parent.name}/{job.root.name}: {st}")
            if limit and counts.get("written", 0) >= limit:
                break
        return {"counts": counts, "failed": failed[:50]}

    @mcp.tool()
    def prompt(character: str, job_id: str, file: str, text: str | None = None, clear: bool = False) -> dict:
        """Read or edit the prompt behind one generated still before re-rolling it. file is the
        image inside the job, e.g. '02_facings/NE.png' or '01_anchor/anchor.png'. Without text:
        returns the prompt last used ('used') and any saved edit ('custom'). With text: saves it as
        that file's prompt for its next generation (then re-roll it: generate(..., stage='facings',
        only=['NE']) or the anchor). clear=True goes back to the built prompt. A human still approves
        the result."""
        from .core import prompt_edit
        job = job_for(character, job_id)
        if clear:
            return prompt_edit.set_prompt(job, file, None)
        if text is not None:
            return prompt_edit.set_prompt(job, file, text)
        return prompt_edit.get(job, file)

    @mcp.tool()
    def approve(character: str, job_id: str, stage: str) -> dict:
        """Mark a stage approved ('anchor' or 'facings'). ONLY call this after the human has looked at
        the output (status with include_images) and said yes; never approve on your own judgement."""
        gen.approve(job_for(character, job_id), stage)
        return {"approved": stage}

    @mcp.tool()
    def status(character: str | None = None, job_id: str | None = None, wait_seconds: float = 0,
               include_images: bool = False) -> list:
        """Without a job: list jobs and open queue tasks. With character+job_id: stage statuses,
        output file paths, facing drift, per-action QA verdicts, open/failed tasks.
        wait_seconds (max 900): block until this job has no queued or running tasks.
        include_images: also return the anchor / facings sheet / action previews as images."""
        if not (character and job_id):
            jobs = [{"character": p.parent.parent.name, "job_id": p.parent.name,
                     "stages": {k: v["status"] for k, v in json.loads(p.read_text())["stages"].items()}}
                    for p in sorted(base.glob("*/*/job.json"))]
            from .core import motion as motion_lib
            motions = [{k: m[k] for k in ("name", "status", "action", "facing", "frames", "method")} for m in motion_lib.list_all(base)]
            return [json.dumps({"jobs": jobs, "motions": motions, "open_tasks": open_tasks()}, indent=1)]
        job = job_for(character, job_id)
        deadline = time.time() + min(max(wait_seconds, 0), 900)
        while open_tasks(job) and time.time() < deadline:
            time.sleep(2)
        meta = job.read_meta()
        r = job.root
        fr = r / "02_facings" / "facings_report.json"
        from .core import stages
        actions = {}
        for d in sorted((r / "03_actions").glob("*/*")):
            if d.is_dir():
                key = f"{d.parent.name}/{d.name}"
                qa = stages.qa_review(job, d.parent.name, d.name)
                exp = r / "06_export" / d.parent.name / d.name
                actions[key] = {"qa": qa, "exports": sorted(str(p) for p in exp.glob("*/*") if p.suffix in (".png", ".aseprite", ".gif", ".json"))}
        failed = [t for t in q.list("failed") if Path(t["job"]).resolve() == r][-5:]
        st_dir = r / "06_export" / "stack"
        stack_out = sorted(str(p) for p in st_dir.glob("*")) if st_dir.is_dir() else []
        out = {"character": character, "job_id": job_id, "inputs": meta["inputs"],
               "stages": {k: v["status"] for k, v in meta["stages"].items()},
               "anchor": str(r / "01_anchor" / "anchor.png") if (r / "01_anchor" / "anchor.png").exists() else None,
               "facings": json.loads(fr.read_text())["facings"] if fr.exists() else {},
               "actions": actions, "open_tasks": [{k: t[k] for k in ("id", "stage", "status", "args")} for t in open_tasks(job)],
               "recent_failures": [{k: t[k] for k in ("id", "stage", "error")} for t in failed],
               "stack": stack_out}
        result: list = [json.dumps(out, indent=1, default=str)]
        if include_images:
            for p in [r / "01_anchor" / "anchor.png", r / "02_facings" / "facings_sheet.png"]:
                if p.exists():
                    result.append(thumb(p))
            for gif in sorted(r.glob("06_export/*/*/12f/*_preview.gif"))[:6]:
                result.append(thumb(gif, 256))
            for rot in sorted(r.glob("06_export/stack/*_rotations.png"))[:1]:
                result.append(thumb(rot, 1024))
        return result

    return mcp, q


def main(base: str | None = None) -> None:
    mcp, q = build(base)
    worker = Worker(q)
    worker.start(standby=True)             # idle while the web UI or a CLI worker holds the queue
    try:
        mcp.run("stdio")
    finally:
        worker.stop()
