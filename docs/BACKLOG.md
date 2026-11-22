# Backlog

Ronan's notes (2026-11-20, notebook), each checked against the code. Status: **have** = exists,
**part** = some of it exists, **new** = not built. Order inside a group = suggested order.

## A. Fixes (small)

| # | Note | Status | What's there / what's needed |
|---|---|---|---|
| 15 | "Can't get out of view when enlarging facing images" | **done** 2026-11-20 | Anchor/facing/contact images open with `target="_blank"`: a bare image tab, no way back in an app window. Needs an in-page viewer (close button, Esc, click outside). |
| 14 | "Re-roll originals should still be there in case I decide I want it" | **done** 2026-11-20 | Re-roll overwrites `anchor.png` / `<facing>.png` / clips in place (audit #8). Needs: keep every take (`takes/` folder), show them, "use this one". |
| 6 | "Show what's currently running in queue" | **done** 2026-11-20 | Queue panel now lists running tasks first; header says "Working (1)". Needs: the running task's job/stage/elapsed in the header, visible without opening the panel. |
| 4 | "If animation fails does it re-run?" | **done** 2026-11-20 (QA-fail re-roll still open) | A frozen clip is re-rendered automatically (FL2VA → I2V). Any other failure stops at *failed* and waits for **Retry**. Needs: optional auto-retry (once, new seed) for GPU stages, and QA-fail → re-roll option. |

## B. Control (medium)

| # | Note | Status | What's there / what's needed |
|---|---|---|---|
| 1 | "Access to the prompts" | **done** 2026-11-20 (Prompts… dialog) | `spritewaffle prompts --job J --action A` prints them; provenance stores every prompt used. Needs: see and edit the prompt in the UI before rendering (per anchor / facing / action), with the fixed rules kept. |
| 10, 12 | "Adjust size of cell borders if needed" / "set size if we want" | **done** 2026-11-20 (Sizes… dialog) | Profiles hold cell size, sprite height, palette size, fps — but only `spritewaffle profile new` makes one, and the UI only picks. Needs: profile editor in the UI; per-job cell override; the "too wide for the cell" warning offering a bigger cell. |
| 7 | "Better sorting tools" | **done** 2026-11-20 | Job list is search-only. Needs: sort (recent, name, progress), filter by type/style/status, group by character. |

## C. Experiments (need real runs to answer)

| # | Note | Status | What's there / what's needed |
|---|---|---|---|
| 5 | "Test if we can also change game angle" | **tested** 2026-11-20: 4 directions work under top-down/iso; 8 do not (diagonals copy) | Profiles have `projection` side / topdown_34 / iso_2to1 and the prompts change with it; never run end to end. Needs: one character in each projection, judged. |
| 2 | "Test more motion libraries" | **part** | Library holds 1 approved mannequin walk. Needs: more driving clips (idle, run, attack, jump) and a flow-vs-TARA comparison per action. |
| 11 | "If I add to motion library it should convert to mannequin, or option to just use that one" | **new** | Library stores the clip as given. Idea: render a grey mannequin version of any added clip (TARA onto a mannequin) and keep both; test whether the mannequin transfers better. |

## D. Bigger features

| # | Note | Status | What's there / what's needed |
|---|---|---|---|
| 9, 3 | "Edit model to make changes" / "test default character adding items, clothing etc." | **done** 2026-11-20 (Make a variant…; item from a picture done 2026-11-21) | Needs: edit an approved character with H3 Image edit ("add a red cape", "swap club for sword") → a new variant job that keeps the base's facings as references; test with a plain base character. |
| 8 | "Items, accents, terrain etc, style match" | **part** (equipment items done 2026-11-21: item jobs, front + back, Fit on…; terrain/tiles open) | Props exist (sprite stacking, style reference from a hero). Needs: item/terrain/tile asset types that match a character's style and palette. |
| 13 | "Style reference tool, way to add a set or view" | **part** | Anchor can take one style reference. The local project library can collect and preview several reference images. Applying a saved collection to new generation is open. |

## E. Found while working

| # | Note | Status | What's there / what's needed |
|---|---|---|---|
| 16 | Atlas PNG too big for game engines | **done** 2026-11-20 | Character atlas is one row per animation, untrimmed: the hare at a 384 px cell is 4608×15360 (Unity's limit is 8192, many GPUs 16384). The `.aseprite` is unaffected (Unity imports that). Needs: max texture size, multiple pages, trim, mirror dedupe (audit "missing" list). |
| 17 | Effects section (spells, fire, explosions) | **done** 2026-11-20 | asset type `effect`: H3 on black (or green), brightness alpha, loop / one-shot picking, flipbook export. Next: character + effect as two layers with an event; thrown objects. |
| 18 | Animals, effects on characters, thrown objects | **done** 2026-11-21 | animal type via turnaround sheet; attach effect (spawn / projectile, front / behind) with export events; throws end anywhere. Open: auras lying flat on the ground (squash), slash preset reads as a flash. |
| 19 | Sprite stacks from real 3D | **done** 2026-11-21 | TRELLIS.2 via a 3D-look render; default method. Open: slight spikes at thin tips; colours follow the render, not the pixel anchor's palette, unless a job/profile palette is set. |
