# Prompting lessons (measured)

Each line was measured on real runs; dates and numbers are in [DECISIONS.md](../../DECISIONS.md).
Read this before changing a prompt in `prompts/builder.py`.

## H3 image edit (facings, variants, items)

- **Saved project style reference.** A single sprite from the project library can guide a new
  anchor through the existing image-edit workflow. The prompt identifies Picture 1 as an art
  style reference and describes the new subject. PNG and lossless WebP versions of one knight
  reference both produced a teal courier at seed 417. These two renders had different pixels.
- **Standalone Item anchors.** Extract colour swatches locally and pass them as text to the still
  generator. The model receives the item description, active style, and colour cues without the
  character image. At seed 417, specifying a strict side profile and downward grip made the toy ray
  gun silhouette clearer. Character fitting uses the approved item image in the separate variant workflow.
- **One reference picture per facing.** Adding the front view as a second picture made every
  facing come out as that front view. Diagonals use only the nearest cardinal as Picture 1
  (more pictures pulled SE to pure E).
- **Say where the camera is** for top-down / iso. Style words alone kept an eye-level camera.
  Under raised cameras 4 directions work; 8 do not (diagonals copy).
- **Green background is flattened to exact #00FF00** after every still. Edit models amplify an
  off-green background when a still is fed back.
- **Item as a reference picture needs H3's own caption format.** "X in <Picture 1> is
  <Subject 1>…", "The target image shows…", per-Subject preservation. Also needed: the item
  shrunk onto a grey card, and a <Subject 3> pinning Picture 1's frame and camera. Without those,
  the item picture was read as the canvas (huge armor, tiny knight).
- **Back of an item:** "draw it seen from behind" copied the front. "Turn the item around 180
  degrees… the back is one closed outer surface" works (one roll in two still shows a clasp).
- **Straight back view (N) of a fitted item goes by words.** With the back picture, H3 drew the
  base's belt across the cape 5/5 times; in words 0/2. NE/NW keep the picture.
- **Back views lose front details only in words:** "a golden breastplate" for N, not the full
  description with the gem (it put the gem on the back). But keep what wraps round or hangs behind:
  "a long red velvet cape with gold trim along the edges" drew the trim on N (2/2; without it 0/2),
  and "reaching to the knees" kept the cloak's length (2026-11-27).
- **Plain bodies and four-legged animals don't turn one facing at a time** (only the head turned;
  7/7 copies). A **turnaround sheet** drawn in one go turns them. On a sheet, "only plain
  undergarments" came out as bare mannequins; named, coloured garments are drawn.

## H3 video

- Clip length is a frame count, not seconds (`frames` param).
- A frozen clip is re-rendered automatically (FL2VA → I2V).
- Prompts follow the H3 structure (see the h3-prompt-writing skill). Motion short and literal;
  the transition pose is a small step from idle, never the extreme pose.

## Local models

- **Qwen3-VL 4B (prompt writer):** literal braces / a JSON example in the system prompt gave empty
  output, and so did a strict "one word only" instruction. Plain "Answer yes or no." works.
  Descriptions over ~30 words returned empty text too.
- **Qwen3-VL 4B as a mistake checker:** not reliable (caught half the belts, none of the clasps).
  Ronan's ruling: the human reviews and re-rolls; no automatic checker.
- **TRELLIS.2:** needs a 3D-look render of the anchor (pixel art in gave a flat card); free VRAM
  before it.

## Effects

H3 may draw a "green" effect on black, or a green card on black. The background is detected
(black / green / both) before keying.

- **H3 image edit fills enclosed gaps** (between arms and body, between legs) with speckled green or with solid black ringed by a thin green line, measured 2026-11-26 on a leather vest fitted onto a base body. The key cleans both in code (pixel/chroma._clean_holes); a dark fill that touches the drawn outline stays and reads as shading. Re-rolling changes which of the two you get, not whether.
- **Layered items (a second item fitted over the first):** H3 image edit keeps a part of the first item that <Picture 1> shows prominently in that view (the vest's round shoulder pad in E), drawing it over the new item, 1 of 8 views. "Covers ... which cannot be seen" did not help (pad stayed, re-roll 1); a POSITIVE description of the top layer did: "the cloak is the outermost layer: it drapes over the shoulder and upper arm, so the shoulder is dark blue cloak fabric" (re-roll 2, fixed). Say what is visible, not what is hidden. 2026-11-26.
- **Video clips of a layered fit:** in a back view the top layer (cloak) hides the clothes under it, and the video prompt names no clothing, so when motion swings the cloak aside H3 invents bare skin or recolours (NE run 0/2). Naming what is underneath in the action text fixed it (1/1): "under the open cloak he keeps wearing the brown leather vest and grey shorts, which show whenever the cloak swings aside". 2026-11-26. Now a default for layered fits (builder.outfit_line): 0/3 -> 3/3 on NE run, 2026-11-27.
- **Front-view attack clips turn sideways** with the preset ('makes one forward strike'): 0/2 stayed front. Saying where the punch goes and what stays square fixed it: "punches once straight toward the viewer ... the arm reaching forward toward the camera ... the chest, hips and feet stay square to the viewer the whole time" (3/3, mannequin S). 2026-11-27.
- **Views from a 3D model:** redraw the render ALONE (with the nearest facing as Picture 2 the pixel knight copied it 4/4); say what shows from that side ("the back of the head or helmet, the shoulder blades, the heels; the face ... on the far side") or near-back views come out as fronts; "Add nothing that is not in Picture 1" stops plain bodies being dressed; draw it large and scale down after (small renders lose the view). 2026-11-27.
