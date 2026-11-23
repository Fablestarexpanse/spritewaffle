# Troubleshooting

| Symptom | Fix |
|---|---|
| Header says *ComfyUI offline* | Start ComfyUI (default 127.0.0.1:8188). Frame processing still works. |
| `doctor`: *model missing* | The model isn't in ComfyUI's model folders, or the template map points at another file name ([COMFYUI_SETUP](../COMFYUI_SETUP.md)). |
| A task failed | Open **Queue → Failed** to read the error and use **Retry**. GPU tasks already retry once with a new seed. |
| `another worker holds …` | One worker per jobs folder: close the other UI/worker. A dead worker's lock is taken over automatically. |
| New job types or buttons missing after an update | Restart `spritewaffle ui`; the server doesn't reload itself. |
| A facing "looks like a copy of S" / didn't turn | Re-roll it. For plain bodies and animals use the turnaround sheet types (base body, animal). |
| A facing drifts (colours/height) | Re-roll. Under legacy mirroring, a drifted W/NW/SW is replaced by its flipped partner automatically. |
| A fitted item looks wrong in one view (belt over cape, clasp on the back) | Re-roll that facing. Human review is the check. |
| Sprite cut off / feet off centre | The action is wider than the cell; the QA warning names a cell size that fits (Sizes…). |
| Clip came out frozen | Already handled: re-rendered automatically. |
| TARA fails with *USE_FLASH_ATTENTION* | Use the `comfy kitchen` attention backend (already set in the template). |
| TRELLIS out of memory | Already handled: VRAM is freed first. Lower the upsample in the template if it still fails. |
| Manifest missing on old jobs | `spritewaffle manifest` (or MCP `manifest_migrate`). |
