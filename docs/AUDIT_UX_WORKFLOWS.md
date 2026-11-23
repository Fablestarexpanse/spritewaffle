# SpriteWaffle workflow usability audit

Baseline `b3caaa4`. Inspected the workspace, single-page stage controller, editor scripts, FastAPI routes, and the CLI and MCP operation maps. Chromium recorded 100 screen and viewport combinations and 3,603 rendered control observations at 1440, 800, and 390 CSS pixels. This is a workflow audit with disposable assets.

## Inventory

| Workflow | Entry and sequence | Discoverability and feedback |
| --- | --- | --- |
| Create or resume | Home and New asset → asset type and name → first stage. Job browser for search, filters, and returning to a saved asset. | Frequent actions belong in the header. Home and asset descriptions should describe what the selected type produces. |
| Character, base body, creature, animal, item, prop | Anchor → import or generate → review → facings, sprite stack, or export. Image viewer and earlier takes sit beside the image. | A path input is the only entry to single-image import. Asset types that work from a sheet use the secondary sheet controls. |
| Item fitting | Item front and back → standalone item export, or Fit on after approval. Character or base body → Make a variant. | Fitting is a contextual action after approval. Standalone export needs a clear path of its own. |
| Animation and repair | Animations → choose actions and facings → queue → clip details → timeline → repair or edit pixels → check and export. | Existing clips come after generation. Opening the timeline requires two activations after reaching the clip. QA, reprocessing, and attachments belong with the selected clip. |
| Effects | New effect → preset or text → render → process → preview and files. Attach from animation details. | Processing belongs with the existing clip. Export links sit with generated results. |
| Sprite stack | Prop → anchor → Sprite stack → build or rebuild → viewer, sheets, and GIF previews. | The stack method and viewer controls belong in the stack workspace. |
| Tilesets, terrain, maps, modules | Tileset → choose sheet and grid → mark tiles and terrain → preview or edit map → save, stamp, or export. | Existing shortcuts reach each long section. Tile and module settings belong near their previews. |
| Project consistency | Project menu → style guide, master palette, reference library, motion library. Job settings → per-job overrides. | These are occasional project-level tools. Style reference and motion choices also appear where they are used. |
| Queue and recovery | Header Queue → All, Active, or Failed → task, job link, cancel or retry. | A new failure opens the queue over the workspace even while someone is entering a value. |
| Appearance and help | Appearance → preview, theme, scale, density, motion; About for version and attribution. | These are preferences. Keep them apart from asset actions. |

## Prioritized implementation

1. **High — make image import a visible start.** Offer a local image chooser from the Anchor stage and keep the existing path import under the same action. Use the existing queue and review state. Keep the original bytes in the job so a retry can read the same file.
2. **High — keep queue feedback from interrupting work.** Announce new failures and leave the queue under the user's control. Keep status and error messages accessible without stealing focus.
3. **High — protect the current asset from stale requests.** Ignore outdated job responses. Preserve relevant inputs, disclosure state, and focus when the same stage refreshes.
4. **High — make animation editing a direct path.** Put existing clips before generation, add one direct timeline action per editable clip, and retain details for QA, exports, and attachments. Base the generation selector on the job's supported directions and available source facings.
5. **Medium — clarify labels and first-use guidance.** Use plain outputs in the asset-type chooser, label source fields, and show what to do at an empty or blocked stage.
6. **Medium — recover from an empty job search.** Ignore unavailable saved filters and offer one action to clear an empty search with its filters.

The existing stage layout and job formats support these changes. A new navigation model would move familiar actions and require migration of existing deep links. The project menus, specialized editor controls, output formats, and approval rules stay in their existing contexts.

## Validation

| Task | Before | After |
| --- | --- | --- |
| Start with an existing image | Enter or paste an absolute path and choose Import. | Open the file chooser and select the artwork. The original is copied into the job and the result appears for review. The path option remains available. |
| Adjust a saved animation | Scroll past generation and open the clip, then choose Timeline. Two activations after reaching the clip. | Find clips first and choose Edit timeline. One activation. |
| React to a queue failure | The panel opens automatically. | A status message and failed count appear. Open Queue and choose Failed when ready. |
| Return to the previous stage | The browser's Back action could leave the asset because stage changes replaced its history entry. | Back and Forward revisit the stages in order. |
| Recover from an empty search | Change the query and filters individually. | Clear the query and filters with one action. |

The revised sweep covered 100 screen and viewport combinations and 3,658 control observations with no horizontal overflow in the measured regions. Chromium created an Item from Home, refused a corrupt upload, verified the original bytes, approved the processed anchor, and revisited stages with Back and Forward. Supplied front and back fixture images made it possible to test manual approval and a real standalone item export. The browser opened the timeline directly, saved and reopened a 137 ms frame duration, and checked pixel-editor access and focus return at 1440, 800, and 390 px. The tablet and phone checks used desktop Chromium viewport emulation. A four-direction profile offered four facings and counted eight clips for two actions. Resetting an empty search restored the results and focus.

The browser refused a stale response from an earlier asset and preserved a path draft and keyboard focus through a background refresh. At 390 px, the failure message left Retry clickable and the retry created a queued task. Midnight, Slate, Forest, Light, OLED, and System passed the 390 px layout check at 150% interface scale. The regression suite passed 340 Python tests and eight Node tests. Python emitted the existing Starlette deprecation warning.

The existing tileset fixture created a standalone module ZIP and reopened a map with two placements. Tiled 1.12.2 imported, re-exported, and rendered the map. Live ComfyUI generation, touch-device testing, and screen-reader testing remain open. Further usability work should cover touch and keyboard use in the map and attachment canvases, failure recovery during live generation, and long camera and export forms.

[Logical focus order](https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html) · [Status announcements](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) · [Minimum pointer target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
