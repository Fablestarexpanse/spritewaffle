# Asset workflows

[Wiki home](Home.md) · [Studio guide](Studio-Guide.md) · [CLI and MCP](Interfaces.md)

Each asset lives in a job. Use **New asset** and choose its type.

| Asset | Typical stages |
| --- | --- |
| Character or creature | Anchor, facings, animations, export |
| Base body | Turnaround sheet, approve facings, animate or fit an item |
| Standalone item | Front, back, export or fit on a body |
| Animal | Turnaround sheet, facings, animations, export |
| Effect | Render or import, process, export a flipbook |
| Prop | Anchor, sprite stack, export |
| Tileset | Import a sheet, define terrain and animation, create maps, export |

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
   Aseprite Importer makes one clip each, plus an Animator Controller) and atlas pages for other
   engines: trimmed frames packed into PNGs no bigger than the page limit (default 4096), each with
   a TexturePacker JSON (Phaser, PixiJS, Godot importers) plus one SpriteWaffle JSON with fps, loop
   and pivot per animation. *Engine flips W/NW/SW* leaves exact colour-only mirrors out of the atlas.
   Facings with depth or normal maps have their own atlas entries.
   Every file is downloadable from the same tab.

### Palette and pivot (pixel art)

- **One palette per character.** The first pixelize builds it from the anchor + every facing (so
  colours seen only from the back are included) and every clip uses it. Animations → **Palette**
  shows it; *Rebuild from facings*, or load your own `.gpl` (Aseprite / GIMP / Lospec), `.hex` or
  `.png`. Clips made with an older palette are listed; *Apply* re-pixelizes them from their frames
  (no rendering). CLI: `spritewaffle palette --job <job> [--file pal.gpl | --rebuild] [--apply]`.
  A loaded palette is matched by nearest colour, so it has to suit the character.
- **One pivot per character.** Each clip is placed so the feet sit on the cell's centre line, one
  pixel above the bottom, whatever the weapon or cape does. Every animation then shares the pivot
  `(cell/2, cell-1)`, written as a `pivot` slice in the `.aseprite` and as `pivot` / `pivot_norm`
  in the JSON. An action too wide for the cell is shifted just enough to fit; its QA report says
  so and its pivot records where the feet are (a bigger profile cell avoids it).

### Showcase GIF

**Export → Make showcase GIF** (`spritewaffle showcase`, MCP `showcase`) writes
`06_export/showcase/<name>_showcase.gif` to show a character to people: a turnaround of the game
sprite through every direction, each action with all directions playing in a compass grid (idle,
walk, run, jump, attack first), then an end card. It carries the SpriteWaffle branding: the
brand-purple header with the app icon, the character's name and what it wears, a "Made with
SpriteWaffle" wordmark, the icon in each grid's centre, and the horizontal logo on the end card.

### Unity import

With the 2D Aseprite Importer package, select the `.aseprite` and set:
Filter Mode **Point**, Compression **None**, Max Size **at least the atlas size**, Pixels Per Unit =
**one number for the whole project**, usually your tile size (16 or 32), never each sprite's cell
size: a 64 px goblin and a 384 px hare at their own cell sizes would both come out one unit tall and
break the Pixel Perfect Camera. Pivot **Custom** at the JSON's `pivot_norm` (for a 64 px cell,
`(0.5, 0.0156)`), Pivot Space **Canvas**. Each tag becomes a clip; one-shot actions (attack,
jump, …) are tagged to play once and import with Loop Time off. Checked 2026-11-26 in Unity 6000.6
with the 2D Aseprite Importer 6.0.0: a one-shot clip imported with `loopTime = false`, 12 keys
83 ms apart, and with the custom pivot above every frame's pivot sat on the exported foot point
(canvas (32, 1) from the bottom-left of a 64 px cell). Unity's default pivot (Canvas, Bottom
Center) is one pixel lower, under the feet, so set the custom pivot.

Frame timing: `.aseprite` stores whole milliseconds per frame, so 12 fps is 83 ms a frame
(12.05 fps), about 0.4 % fast against the JSON's exact fps over a long loop. Engines reading the
JSON or the TexturePacker `duration` get the same 83 ms; the drift only matters if you sync
animation to music by the nominal fps.

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

Each job has a style (header **Style**, or `spritewaffle style --job <job> <style>`): **Pixel art** (default),
**Hand-painted**, **Anime cel**, **Comic ink**. The style changes the prompt wording and the
processing: pixel art goes through the pixelizer (grid, shared palette); the others are keyed,
despilled and scaled smoothly with soft edges at 4x the profile size (a 64 px profile cell becomes
256 px) and export as full-colour `.aseprite` / PNG. Switch, then generate a new anchor. Mirroring
works in every style; flow transfer and sprite stacking are pixel art only. New styles are one
entry in `spritewaffle/prompts/styles.py`.

### AI prompt writer (optional)

Header **Prompts → AI** (or `spritewaffle writer --job <job> ai`): a small local model (Qwen3-VL 4B, run
by ComfyUI) looks at your character and writes its description and per-action motion text, so a
goblin swings *its club* and new actions like `cast spell` work. Every reply is checked and falls
back to the fixed template wording; the rules (green background, framing, in-place motion) are
never left to the model. `spritewaffle prompts --job <job> --action walk` shows template vs AI text
without rendering.

### Effects (spells, fire, explosions, impacts)

Home → **New effect** (type `effect`). Pick a preset (fireball, explosion, magic circle, healing,
slash, lightning) or write your own first frame and motion; choose loops / once, the background,
size, frames and fps; **Render effect**. H3 draws the first frame, then a clip; the background
becomes transparency:
- **black** (glowing effects): alpha from brightness. Works with normal alpha blending and, since
  empty areas stay black, with an additive material too.
- **green** (effects with dark parts, like smoke or dust): keyed like a character. Dark smoke on
  black can't be separated from the background.

Loops skip the clip's first frames and use the window (at least 1 s) whose ends match best;
one-shots keep everything from the first to the last visible frame. Exports: strip PNG, frames,
square flipbook sheet, `.aseprite` (one-shots play once), preview GIF, JSON (fps, loop, blend).
**Re-process frames** changes size / frames / colours without rendering again.

### Variants: one change, or an item from a picture

On a character with approved facings: **Make a variant…** → describe the change ("add a long green
cape") *or* give an item picture (armor, weapon, hat) and say how it's used ("wearing this",
"holding this in the right hand"). The picture goes to H3 Image edit as a second reference (shrunk
onto a grey card, `01_anchor/item_ref.png`), so the item keeps its real design; the variant's anchor
and every facing are the base's own images with the item fitted on, so poses line up. Back views show
only the back of the item (no chest gem on the back).

### Directional sprites: manifest, camera profile, turntable

Every asset keeps a manifest (`manifest.json`): each frame's view angle in degrees (any number of
views), foot point, colour / depth / normal / high-res master files and how it was downscaled,
ready for engines that blend between angles and light sprites with maps. **Camera…** sets the
project's camera profile (or one asset's), **Mirror policy** on Facings/Animations decides which
views are flipped, **Align feet** pins every frame's foot point, and **Turntable…** spins through
the views (read-only) to spot angle-to-angle drift. Existing assets: `spritewaffle manifest`.
Details and every call: [docs/MANIFEST.md](../../docs/MANIFEST.md).

### Standalone items and equipment

Choose **New asset → Item** to create a standalone game object. Describe the item, its colours, and
the view you want. The anchor defaults to a front view. **Facings** draws the back view.
The active art style sets the render style. An optional library or approved hero reference
contributes up to six colour swatches. The renderer receives those cues and your description.
Approve both views to export the item on its own.

Every facing has **Edit prompt…** beside Re-roll: the prompt that view was generated with, editable,
saved for that view's next generation only (`spritewaffle prompt --job … --file 02_facings/NE.png --set …`,
HTTP `GET/POST /api/jobs/{character}/{job}/prompt`, MCP `prompt`, so an agent can do the same).
Provenance marks generations made from an edited prompt (`prompt_edited`).

To equip the item after approving both views, open a character, choose **Make a variant…**,
pick the item, and say how it is used. The worn variant gets all eight facings. The standalone
item keeps its views and lists the characters it was fitted on.

For a clean body to fit items on, choose **New asset → Base body**. It's drawn as a turnaround sheet in plain
grey undershirt and shorts (all 8 views at once, like animals) and animates like any character. An
item's **Export** tab saves its front and back as game sprites (`06_export/item/`).

### Animals (four-legged)

Choose **New asset → Animal**. The anchor step draws one **turnaround sheet** (front, side, back and two
three-quarter views in a row) and cuts it apart, so all 8 directions exist at once (W/SW/NW
mirrored). Actions use four-legged wording: walk (diagonal pairs), run (gallop), pounce, sit,
sleep. A side-on animal is wider than tall. Set a larger cell in **Job settings → Profile sizes**
(for example, 96 px for a 48 px
sprite); a clip that doesn't fit says which cell would.

### Spells, auras, thrown objects (effect + character)

Make the effect first (Effects above), then open the character's animation (click it on the
Animations tab) → **Effect**: pick the effect job, scrub to the frame, click where it starts,
choose *in front* / *behind* and *stays* (burst, aura) or *flies* (projectile, at N px per frame
toward the facing), **Attach + preview**. The two stay separate sprites, as games use them: the
export JSON gets an event (frame, point, layer, velocity) and the effect's files are copied into
`06_export/character/effects/`.

For a throw, write the action in **Prompts… → Actions** (e.g. "throws the shield forward…") and
set **Ends: anywhere** so the clip doesn't end with the object back in the hand; then attach the
thrown object (an effect, e.g. a spinning shield) as a projectile at the release frame.

### Tileset

Choose **New asset → Tileset**, select a PNG sheet, and enter the tile width and height.
Margin is the space around the sheet. Spacing is the gap between cells. The grid must
fit the image exactly. Imports accept still PNGs up to 16 MiB and 4096 × 4096 pixels,
with at most 4096 tiles.

Click the grid or enter a **Tile ID** to select a cell. IDs start at zero and run left
to right, top to bottom. Transparent cells keep their IDs. **Collision** makes the cell solid;
**Shape** picks the full square, a half tile (top or bottom), a 45° slope (◢ up, ◣ down), one
half of a gentle 2:1 slope, or a custom polygon (x,y points in tile pixels, top-left origin).
**One-way** makes a jump-through platform (solid from above only). **Properties** are name=value
pairs for the game (`damage=5, water=true, footstep=grass`); numbers and true/false keep their
type, and one name keeps one type across the tileset. The sheet preview draws each shape, with a
dashed top edge on one-way tiles. Importing the same sheet again keeps shapes and properties;
a different sheet or grid preserves the earlier PNG and grid record and starts a new collision
layout.

In the exports, a shaped tile becomes a polygon object in Tiled's tile collision editor (with a
`one_way` bool property), a collision polygon with `one_way = true` in the Godot TileSet, and a
`collision` entry (shape, polygon, one_way) in `tileset.json`. Properties become Tiled tile
properties and typed Godot custom data layers (`get_custom_data("damage")`), checked by loading
the TileSet in Godot 4.6. Tile modules list each shaped tile's bounding box plus its `polygon`.

**Export tileset** writes `tiles.png`, `tileset.json`, and `tileset.tsj` to the job's
`06_export/tileset` folder. Keep the PNG next to either metadata file. Collision changes
flag the previous export as stale. The PNG in the bundle is an exact copy of the source.

```powershell
spritewaffle tileset import --job meadow/v1 --file meadow.png --tile-width 16 --tile-height 16
spritewaffle tileset collision --job meadow/v1 --tile 1
spritewaffle tileset collision --job meadow/v1 --tile 2 --shape slope_up
spritewaffle tileset collision --job meadow/v1 --tile 3 --shape half_top --one-way
spritewaffle tileset properties --job meadow/v1 --tile 2 --set "damage=5, footstep=grass"
spritewaffle tileset export --job meadow/v1
```

`tileset inspect` reports the grid and export status. Add `--clear` to a collision command
to remove the rectangle. The MCP `tileset` tool offers the same operations. The HTTP
base is `/api/jobs/{character}/{job}/tileset`, with `import`, `collision` (optional `shape`), `properties`, `terrain`, `animation`, `preview`,
and `export` POST routes.

The `.tsj` and map `.tmj` name the Tiled release they follow (`tiledversion` 1.10.2), and the terrain
set shows a plain tile of its first terrain as its icon. **Allow empty cells** (map export,
`tilemap export --allow-empty`, HTTP/MCP `allow_empty`) leaves cells no tile matches empty instead of
refusing the export, and lists them under `empty_cells` in `map.json`.

#### Terrain transitions

Save a list of terrain names, select a tile, and assign its four corners. A grass tile
has Grass on all four corners. A tile transitioning from grass on the left to water on
the right has Grass, Water, Water, Grass in top-left, top-right, bottom-right, bottom-left order.

Use **Fill preview** and **Paint cell** to try the rules on an 8 × 6 map. Adjacent cells
share corners, and the map picks the lowest matching tile ID when several tiles have the
same corners. Dashed cells need a matching tile. The preview stays in the browser tab,
including through reloads. Export saves the authored rule set in both metadata formats.

CLI `tileset terrain --job meadow/v1 --file terrain.json` reads a `colors` list and a `tiles`
object keyed by tile ID. Each tile has four corner names or `null` in the order above.
`tileset preview --job meadow/v1 --file vertices.json` takes a rectangular array of corner
names or `null` and reports tile IDs and missing cell coordinates. A 9 × 7 vertex grid
produces the same 8 × 6 preview size as the browser.

#### Animated tiles

Select a tile and add 2 to 64 frames under **Tile animation**. Enter zero-based IDs
from the imported sheet and durations from 1 to 60,000 milliseconds. Move frames into
playback order and select **Save animation** before switching tiles. The selected-tile
preview and terrain map use the saved sequence. Select **Play previews** to start both.
The selected tile keeps its collision and terrain rules throughout playback.

`spritewaffle tileset animation --job meadow/v1 --tile 2 --file frames.json` saves a
sequence such as `[{"tile":2,"duration_ms":260},{"tile":4,"duration_ms":520}]`. Use
`--clear` to remove it. Each entry selects an atlas cell directly. Both metadata formats
carry the saved timing. Export again after changing an animation to refresh the bundle.

#### Saved maps

Paint the preview, enter a name under **Saved maps**, and select **Save map**. Saved maps
live with that tileset job and can be reopened in a fresh browser session. Select **New draft**
to start a separate 8 × 6 map. Saved maps use the current terrain rules, so changing rules may
leave cells that need repainting. You can save work with unresolved cells and return to it later.

**Cell action** also lets you place the tile selected in the sheet, leave a cell empty, or
restore the terrain result. These choices leave the terrain corners intact. Manual tile
placements stay tied to their sheet. If you replace the sheet, restore outdated cells
before placing tiles from the replacement.

When the map is saved and all painted cells match a tile, select **Prepare map ZIP** and then
**Download map ZIP**. Extract the files together and open `map.tmj` in Tiled. The archive also
includes SpriteWaffle JSON, the PNG, and both tileset descriptions with collision, animation,
and terrain metadata. Untouched and explicitly empty cells export as empty space. Tiled 1.12.2
imported and rendered the map and preserved the cells and tileset metadata when re-exporting it.

For LDtk, open `map.ldtk` from the same folder (square tiles only; the export status says when it
was left out). It has one level with a **Tiles** layer and a **Collision** IntGrid layer
(1 = solid, 2 = one-way). LDtk has no collision polygons, so each tile's exact polygon, one-way
flag and properties are stored as JSON in the tileset's per-tile custom data. Map objects stay
in the Tiled map. LDtk 1.5.3 opened the export (2026-11-26).

```powershell
spritewaffle tilemap save --job meadow/v1 --name "South meadow" --file vertices.json
spritewaffle tilemap list --job meadow/v1
spritewaffle tilemap load --job meadow/v1 --map-id MAP_ID
spritewaffle tilemap export --job meadow/v1 --map-id MAP_ID
```

The CLI and MCP accept rectangular maps up to 32 × 32 tiles. To include manual placements, pass a
JSON object with `vertices` and `overrides`, for example
`{"vertices":[[null,null,null],[null,null,null]],"overrides":{"0":4,"1":null}}`.
Override keys are zero-based cell numbers in row order. Each value is an atlas tile ID or
`null` for an empty cell. Updates keep existing overrides if the field is omitted. Pass
`{}` to clear them. Use the loaded revision when updating an existing map. The `tilemap` MCP tool and the HTTP routes under
`/api/jobs/{character}/{job}/tileset/maps` expose the same operations. ZIPs are written under
the job's `06_export/maps/` folder.

#### Tile modules

Open **Tile modules** after importing a sheet. Choose two corner tile IDs, preview the
rectangle, and save it under a unique name. Each module can cover up to 16 × 16 tiles.
Use **Map preview → Cell action → Place module** to select the module and position its
top-left corner. A transparent atlas slot leaves that map cell intact. The entire
module must fit inside the map. Placement changes the draft, which you save with
**Save map**.

The tileset export includes the module definitions in SpriteWaffle JSON. In Tiled,
each placed tile appears on the map's ground layer with its existing collision and
animation metadata.

```powershell
spritewaffle tileset module --job meadow/v1 --file module.json
spritewaffle tileset stamp --job meadow/v1 --file stamp.json
```

`module.json` takes `name`, `start`, and `end`, such as
`{"name":"Workshop doorway","start":0,"end":6}`. A stamp takes `name`, `cell`, and
`vertices`, with optional `overrides`, `override_atlas`, and `revision`. It returns
updated placement overrides to include when saving a map. Use the same payload as
the `module` argument in the MCP `tileset` tool. The HTTP routes are
`POST /tileset/modules` and `POST /tileset/stamp` under the job.

#### Export a standalone module

Under **Tile modules**, choose a saved module in **Export a standalone module**. The
preview shows its collision cells and pivot. The pivot defaults to bottom-center and
accepts whole pixel coordinates anywhere from the top-left to the bottom-right edge.
Choose **Prepare asset ZIP** and then **Download module ZIP**.

The archive contains `module.png` and `module.json`. The PNG is a still composed of the
base atlas artwork. It keeps the full module dimensions and the original alpha while
removing sheet margins and spacing. The JSON gives the image size, pivot, and one
rectangle per solid tile that the module uses. All coordinates are pixels measured
from the image's top-left, with X to the right and Y down.

For headless export, call `spritewaffle tileset export-module --job meadow/v1 --file export.json`
with a request such as `{"name":"Workshop doorway","pivot":[12,20]}`. Use
`operation="export-module"` and the same `module` payload in MCP. Omit `pivot` for
bottom-center. The HTTP route is `POST /tileset/modules/export` under the job. ZIPs
are stored in `06_export/modules/`. Changing the pivot or asset data produces a
separate ZIP.

A Godot 4.6 test project imported the PNG and read the JSON to position a `Sprite2D`
and a `RectangleShape2D`. With the sprite's centering disabled, its offset is
`-pivot`. The collision center is the rectangle's top-left point plus half its size,
minus the pivot. [Godot Sprite2D](https://docs.godotengine.org/en/stable/classes/class_sprite2d.html)

#### Stateful map objects

Open **Map objects** inside the map editor. Enter the object name, type, and zero-based
cell. Give each state a name and tile ID from the current atlas, then choose the active
state. Select **Apply object** to preview it and **Save map** to keep it. For a workshop
door, use tiles named `closed` and `open` and mark the closed tile solid in the tileset.
Both states sit above the same ground cell. **Clear ground** leaves objects in place.

A map supports up to 64 objects, one per cell, and 2 to 8 named states per object.
Replacing the atlas keeps recorded states and flags them for review. Enter new tile IDs
for every state before exporting the object with the replacement atlas.

The map ZIP retains all the object states in SpriteWaffle JSON. Tiled gets a tile object
for the active state and properties for the stable ID, active state, alternate states,
and whether the active tile is solid. A game's own logic can use that metadata to switch
states during play. The CLI map draft and MCP save operation accept an `objects` array
with `id`, `name`, `kind`, `cell`, `state`, and `states` entries such as
`[{"name":"closed","tile":3},{"name":"open","tile":4}]`. When editing an existing object,
keep the `atlas` binding from the loaded record, or omit it to bind the supplied tiles
to the current atlas. Omit `objects` to keep them unchanged, or pass `[]` to clear them.

#### Reusable object templates

Select an applied object and choose **Save as template** to store its name, type, states,
and default state in the tileset library. On any map using that tileset, select a target
cell, choose the template, and select **Use template**. Set the new object's active
state, then **Apply object** and **Save map**. Each placement has an independent state and
keeps the template ID for reference. Templates use unique names and the atlas they were
created from. When the atlas changes, save a new template from an object with updated
state tiles.

```powershell
spritewaffle tilemap save-template --job meadow/v1 --file bush.json
spritewaffle tilemap templates --job meadow/v1
spritewaffle tilemap instantiate-template --job meadow/v1 --template-id TEMPLATE_ID --cell 10 --state harvested
```

`bush.json` contains `name`, `kind`, `state`, and `states`. Instantiation prints an object
draft for the map's `objects` list. MCP exposes the same operations through `tilemap`.
The map ZIP contains each placed object and its template ID, so it travels independently
of the local library.

### Prop (sprite stacking)

Choose **New asset → Prop**. Create and approve a straight front-view anchor, then open **Sprite
stack** → *Make 3D model + build*. Method **3D model** (default): the anchor is redrawn as a lit
3D render and TRELLIS.2 (on your ComfyUI) builds a real 3D model, which is cut into slices:
overhangs, gaps and uneven sides survive (a pine keeps its branch tiers). Method **outline carve**:
front/back/side/top outlines intersected; fine for boxy props, but hollows come out solid and the
left side mirrors the right. The viewer spins the result (tilt, layer spacing, zoom); exports: slice
strip + JSON for stacking engines, rotation sheet, spin and build-up GIFs, and `model.glb`.

### An existing clip → pixel art

```powershell
.venv\Scripts\spritewaffle run clip.mp4 --character knight --action walk --facing S
```

### Motion library (experimental)

Reuse one approved driving clip (a plain grey mannequin works best) across the whole cast:
**Animations → Source**. *flow* moves the character's own pixels (exact colours, no render,
can't turn the character); *TARA* re-renders with H3 (follows the motion better, colours can
drift — each transfer reports an identity-drift score).

## Seamless textures

New asset → **seamless texture** (ground, walls, water, roofs…). On the Texture tab:

1. Describe it ("mossy cobblestone ground with grass in the gaps"), pick the **tile size** (16–512 px),
   **style** (pixel art, hand-painted, anime, comic), **variants** (1–16) and, for pixel art, **colours**.
2. **Generate.** Each variant is rendered seen from straight above. It's zoomed in (**Detail zoom**;
   Auto picks 4× for tiles up to 32 px, 3× up to 64, 2× up to 128) so a small tile holds a few readable
   features. It's then made seamless by joining its edges along the least visible cut (image
   quilting), and cut to the tile size. Pixel art takes each tile pixel's dominant colour, then the palette.
3. Check each variant in the repeat preview (2×2 to 8×8, **Offset by half** puts the wrap seams in the
   middle). The **wrap score** is about 1.0 when seamless (green ≤ 1.3). **Re-roll** a bad variant.
   **Re-cut tiles** redoes the seaming and cutting from the saved renders, with no new render, after a
   tile size, zoom or colour change.
4. **Approve**, then **Export** (`06_export/texture/`: each tile, a sheet of all variants in a row,
   3×3 previews, JSON with tile size, seeds and wrap scores). Or use **Send to tileset**: a new
   tileset job with the variants as tiles, ready for terrain rules, maps and Tiled export.

CLI: `spritewaffle texture --job cobble/t1 --describe "..." --tile-size 32 --variants 4 --generate`,
then `--approve` (after looking), `--export` or `--to-tileset`; `--retile` after changing settings.
MCP: `texture(character, job_id, action="setup"|"generate"|"retile"|"status"|"export"|"to_tileset", ...)`.

Generator feature size varies between renders (some come out with tiny detail even when zoomed):
re-roll those or raise Detail zoom.

**Variants fit together** (setting; CLI `--shared-edges on`, MCP/HTTP `shared_edges`): every variant
takes variant 1's outer border, colour-matched to it and joined along the least visible cut, and pixel
art gets one palette for all variants. Any variant then sits next to any other, so a map can mix them
for variety. The Variants panel shows all of them mixed and a **side by side** score (the step across
a join against the steps beside it; about 1.0 = fits). Measured 2026-11-26: grass 2.98 -> 1.26 and
cobble 3.25 -> 0.80, the same as variant 1 tiling with itself; each variant keeps 60-70 % of its own
pixels. The shared border repeats, and a variant with very different detail size can still read as a
patch: re-roll it. Off by default; Re-cut tiles after changing it.

### Terrain transitions (two textures → corner or blob tileset)

On an approved seamless texture: **Make transition…** → pick a second approved texture (e.g. dirt
next to grass), name the two terrains, the tile size, how ragged the border is, and a border-shape
seed. The result is a new tileset job with the **16 corner tiles** (every combination of the four
corners being one terrain or the other) and its **corner terrain rules already filled in**. The
tileset's map preview and Tiled export (corner Wang set) work straight away. Running it again on
the same pair replaces the sheet.

Each tile blends the two textures with a mask: its four corners interpolated across the tile, plus
a noise wobble that repeats once per tile. Neighbouring tiles share their edge's corners, and the
noise and both textures continue across tile edges, so any arrangement fits pixel for pixel.
Pixel art gets a hard border, painted styles a soft blend.

CLI: `spritewaffle transition --a grass/t1 --b dirt/t1 --names grass,dirt --roughness 0.5`.
MCP: `transition(a, b, names, tile_size, roughness, seed, ...)`. Both textures need a human's approval.

Limits: the border wobble repeats every tile, so a long straight border shows a regular pattern
(change the seed for another shape). Pixel art can leave single-pixel specks along the border.
Corner (16) and blob (47 + plain) sets; no edge-only sets yet.

#### Blob sets, edge lip, palette

- **Set:** *Corner (16 tiles)*, painted in SpriteWaffle's map preview, Tiled and Godot; or *Blob
  (47 + plain)*, the 8-neighbour set with rounded inner corners (RPG Maker / Godot 3×3 style). Blob
  tiles are built from a 3×3 lattice per tile (corners, edge middles, centre; a corner counts only
  when both its edges are set), so neighbours always agree. A blob tileset is painted in **Tiled**
  (mixed Wang set) or **Godot** (Match Corners and Sides). SpriteWaffle's corner map preview says
  so instead of opening. Tiled can't tell the isolated "island" tile from plain ground (its Wang ids
  have no centre), so the island is only in the Godot export; a single isolated cell won't resolve
  in Tiled.
- **Edge lip:** a darker band on the lower terrain along the border (default 1 px for pixel art,
  `tile/32` for painted; 0 turns it off), so the upper terrain reads as sitting on top.
- **Palette:** pixel-art textures snap to the project's master palette (Project menu) when one is
  set, by perceptual (OKLab) distance, so every tile and transition shares one set of colours.
  Lone "orphan" pixels are cleaned up, checking neighbours across the wrap so the tile still tiles.

## Engines

**Godot 4.** Every character export now also writes `<name>.tres` (a SpriteFrames with each frame
cut from the atlas pages, trim restored, per-frame durations, loop flags) and `<name>.tscn` (an
AnimatedSprite2D with the pivot on the node origin, nearest filtering for pixel art). Every tileset
export writes `tileset.tres` (a TileSet with the atlas, collision shapes, custom data and the terrain set).
Paths inside are relative, so copy the export folder anywhere in the Godot project. Verified with
Godot 4.6: the knight's SpriteFrames loads with 64×64 frames and the right fps and loops, and a blob
TileSet paints terrain with `set_cells_terrain_connect`. Paint the base terrain one cell beyond
the area you care about; Godot leaves the outermost ring of a painted area empty when it has no
painted neighbours to match. Mirrored animations the atlas leaves out (*engine flips W/NW/SW*)
reuse their source frames and are listed in the scene's `flip_h` metadata.

**Unity** (tiles and pixel art): Texture Type Sprite, Sprite Mode Multiple (grid by cell size),
**Pixels Per Unit = tile size**, the same project PPU on every character, effect and tile, Filter Mode
**Point**, Compression **None**, mip maps off. Pack tiles into a Sprite Atlas with **padding ≥ 2**
and rotation and tight packing off. Use a Pixel Perfect Camera (plus the Cinemachine Pixel Perfect
extension if you use Cinemachine) with anti-aliasing off. Rule Tile (2D Tilemap Extras) handles
corner and blob sets, and a Rule Override Tile reuses one rule set across terrains with the same
layout.

### What to put in the game

**Ship `06_export/character/`** (atlas pages, `<name>_atlas.json`, the TexturePacker page files,
Godot `.tres`/`.tscn`, the `.aseprite`). The per-facing folders (`06_export/S/walk/…`: strips,
single frames, GIF and APNG previews) are review files. Measured on `hare/courier`: 150 MB of the
183 MB export is those preview folders; the game bundle is about 21 MB.

**Atlas options** (Export tab, `export-character`, HTTP and MCP `export_character`):
- *Page limit* 2048 for Unity's default import size.
- *Power-of-two pages* (`--pot`) rounds pages up to 2^n, for older GPUs or mip maps.
- *Extrude* (`--extrude 1-2`) repeats each sprite's edge pixels outward, so bilinear filtering or
  mip maps don't pull in the neighbour. Pixel art on Point filtering doesn't need it.
- The TexturePacker page files give each frame a `duration` (ms) and list every animation's fps,
  loop and `flip_x_of` in `meta.animations`. With *engine flips W/NW/SW*, a flipped animation has no
  frames of its own: play its `flip_x_of` animation mirrored.
- Painted (RGBA) characters no longer write a colour list into the JSON (it was 5.6 MB for the
  hare); indexed pixel characters keep their `palette`.
