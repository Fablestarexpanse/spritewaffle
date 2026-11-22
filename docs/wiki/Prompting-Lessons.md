# Prompting lessons (measured)

Each line was measured on real runs; dates and numbers are in [DECISIONS.md](../../DECISIONS.md).
Read this before changing a prompt in `prompts/builder.py`.

## H3 image edit (facings, variants, items)

- **Saved project style reference.** A single sprite from the project library can guide a new
  anchor through the existing image-edit workflow. The prompt identifies Picture 1 as an art
  style reference and describes the new subject. PNG and lossless WebP versions of one knight
  reference both produced a teal courier at seed 417. These two renders had different pixels.
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
  description with the gem (it put the gem on the back).
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
