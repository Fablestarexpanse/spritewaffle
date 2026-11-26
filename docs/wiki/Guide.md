# Guide: what do you want to make?

Each section is one job from start to finish, using the app only (`spritewaffle ui`, then
<http://127.0.0.1:8765>). Buttons are named as they appear. Command line, HTTP and agent (MCP)
versions of every step are in [CLI and MCP](Interfaces.md); details and options are in
[Workflows](Workflows.md).

Two habits hold everywhere:
- **You approve, the tool never does.** Nothing moves on until you click **Approve**. If a result
  looks wrong, **Re-roll** it; the old take is kept under **Earlier takes**.
- **Queue** (top bar) shows what's running. A failed task waits under **Queue → Failed** with its
  error and a **Retry** button.

---

## A walking character for my game

1. **New asset… → Character**. Give it a short name (`knight`).
2. **Anchor**: describe the character under **Generate with ComfyUI**, or use **Choose and import
   image…** for your own art. When the picture is right, **Approve anchor**. Everything else is
   drawn from this one image, so take your time here.
3. **Facings**: **Generate facings** makes the other seven directions. Re-roll any that look
   different from the anchor or didn't turn, then **Approve**.
4. **Animations**: open **Generate animations**, tick the directions and actions (idle, walk, run,
   attack…) and **Queue animations**. Left-facing directions are mirrored from the right-facing ones
   unless you untick mirroring. Click a finished clip to see its frames; **Edit timeline** changes
   frame order and timing.
5. **Export**: **Export character**. Then see [Put it in my engine](#put-it-in-my-engine).

Making several characters for one game? Make the first one (your *hero*), then pick it as the
**Style reference** in the others' **Anchor** step, and set a **Master palette…** under **Project**
so they share colours.

## Animate art I already have

**New asset… → Character**, then in **Anchor** use **Choose and import image…** for one picture.
For a character sheet with several views, open **Import a sheet of directional views**, paste the
file's path, list the views from left to right (`S,SE,E,N`) and **Import sheet** (needs ComfyUI to
cut the figures out). Approve it and carry on from step 3 above.
Have a clip already? See *An existing clip → pixel art* in [Workflows](Workflows.md).

## A four-legged animal

**New asset… → Animal**. The anchor step draws all directions at once as a turnaround sheet. Approve
it, then queue animations as for a character. Animals are wider than tall: if a clip says it doesn't
fit, raise the cell size in **Job settings → Profile sizes…**.

## Armour, clothes or a weapon that fits any character

1. **New asset… → Item**. Describe it, approve its front, then **Facings** draws the back. Approve.
   **Export item** saves the item on its own.
2. Optional: **New asset… → Base body** for a plain body to try items on.
3. Open a character (or base body) with approved facings → **Make a variant…**, pick the item, say
   how it's worn ("wearing this", "holding this in the right hand"), **Create variant**. Or start from
   the item: **Fit on…**, pick the character, **Fit it**. The variant gets all eight directions and
   animates like any character.

## A spell, explosion or other effect

**New asset… → Effect**. Pick a preset or describe the first frame and the motion, choose whether it
loops, and the background: **black** for glowing effects, **green** for smoke and dust. Then
**Render effect**. To fire it from a character's hand, use **Attach + preview** on the character's
animation.

## Ground tiles that repeat without a seam

1. **New asset… → Seamless texture**. Describe the ground ("mossy cobblestones"), pick the tile size
   and how many variants.
2. **Generate**. Look at each variant in the repeat preview; tick **Offset by half** to put the
   joins in the middle where you'd notice them. A wrap score near 1.0 means seamless. **Re-roll** bad
   ones. Tiny detail on a small tile? Raise **Detail zoom** and **Re-cut tiles**.
   Want to mix variants on one map? Set **Variants fit together** to *Yes, shared edges* and
   **Re-cut tiles**; the mixed preview shows whether they blend.
3. **Approve**, then **Export** (tiles and a sheet), or **Send to tileset** to build maps with it.

## Ground that blends into other ground (grass to dirt)

1. Make and approve two seamless textures (above).
2. On the first one: **Make transition…**, pick the second texture and name the two terrains.
   **Set** chooses *Corner (16 tiles)* or *Blob (47 + plain)*, the rounded set most RPG tile
   painters expect. **Edge lip** darkens the border so one terrain sits on top. **Make transition
   tileset**.
3. A new tileset opens with the tiles and their rules filled in. Corner sets can be painted right
   there under **Map preview** (**Paint cell**, **Save map**); blob sets are painted in Tiled or Godot.
4. **Export tileset**, then see [Put it in my engine](#put-it-in-my-engine).

## Platforms, slopes and tiles with game data

Open a tileset and click a tile on the sheet:
- **Collision** makes it solid. **Shape** picks a half tile, a slope or a custom polygon.
- **One-way** makes a platform you can jump up through.
- **Properties**: anything your game needs (`damage=5, water=true`), then **Save properties**.

The sheet shows each shape. **Export tileset** carries all of it into Tiled and Godot.

## A big object made of several tiles (a house, a bridge)

In a tileset, under **Tile modules**, select the top-left tile, **Use selected as first**, select the
bottom-right tile, **Use selected as opposite**, name it and **Save module**. **Prepare asset ZIP**
exports it as one sprite with its collision and pivot.

## Put it in my engine

Ship the **`06_export/character/`** folder (or `06_export/tileset/`, `06_export/item/`,
`06_export/texture/`). The per-direction folders next to it are previews for you, not the game.

- **Godot 4**: copy the folder into the project. Characters: open `<name>.tscn` (a ready animated
  sprite, feet on its origin) or use `<name>.tres` in your own AnimatedSprite2D. Tiles: use
  `tileset.tres` in a TileMapLayer. Paint the base terrain one cell wider than you need; Godot
  leaves the outer edge empty.
- **Unity**: import the `.aseprite` with the 2D Aseprite Importer (one clip per animation). Use
  **one Pixels Per Unit for the whole game** (usually your tile size), Filter Mode Point,
  Compression None. Tiles: slice by the tile size and use Rule Tiles. Full settings:
  [Workflows → Unity import](Workflows.md#unity-import).
- **Tiled**: open `tileset.tsj`; terrains appear as a Wang set ready for the terrain brush.
- **Phaser, PixiJS, others**: load the atlas pages with their TexturePacker JSON
  (`<name>_atlas_0.json`); frames carry their durations.
- **Aseprite**: open the `.aseprite`; each animation is a tag.

Using smooth (non-pixel) scaling or mip maps? Tick **power-of-two pages** and set **Extrude** to
1-2 px before **Export character**, so neighbouring sprites don't bleed in.

## Words you'll see

| Word | Meaning |
|---|---|
| Asset / job | One thing you're making (a character, a tileset), stored in `jobs/<name>/<id>/`. |
| Anchor | The one approved picture everything else is drawn from. |
| Facings | The eight directions (S, SE, E, NE, N, NW, W, SW). S faces the camera. |
| Re-roll | Draw that one result again; the old one stays under Earlier takes. |
| Profile | The sprite size and frame rates for a job (**Profile sizes…**). |
| 12f / 24f | The two frame sets each animation is made in: 12 or 24 frames per loop. |
| Check freshness | Tells you whether the export still matches the current frames, or needs exporting again (*stale*). |
| Wrap score | How seamless a texture tile is: about 1.0 is seamless. |
| Manifest | A file listing every frame's view angle and foot point, for engines that blend between angles ([Directional sprites](Directional-Sprites.md)). |
