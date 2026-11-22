# Roadmap (open items, 2026-11-21)

Everything else in [docs/BACKLOG.md](../BACKLOG.md) and the audits is done. Suggested order:

1. **Directional test prep** (when the Myth-style test starts): generate more than 8 views
   (prompts worded by yaw degrees, nearest generated view as reference); depth/normal map
   generation from masters via `manifest.replay_downscale`.
2. **Style sets** (backlog #13): the local image library is available in Settings. Add palette
   inheritance and style validation, then test reuse of a reference collection in new generation.
   Terrain and tiles that match a character's style and palette are still open (#8, items done).
3. **Motion library** (#2, #11): more driving clips (idle, run, attack, jump); flow vs TARA per
   action; optional mannequin conversion of added clips.
4. **Effects:** auras lying flat on the ground (squash), a slash preset.
5. **QA-fail auto re-roll** (optional, off by default; Ronan prefers human review).
6. **Sprite stacks:** spikes at thin tips; colours follow the render unless a palette is set.
7. **UI polish (audit P3):** placeholder text on imported anchors, the Sizes dialog's long
   "used by" line, hide Style/Prompts on finished items.
8. **Equipment:** N view of a fitted item drops fine trim (words route); fitting several items in
   one go (layers of clothing) is untested.
