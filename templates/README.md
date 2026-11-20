# ComfyUI templates

For each slot, export a working workflow from ComfyUI in **API format** (Workflow → Export (API))
as `<slot>.json`, then fill `<slot>.map.json`:

```json
{
  "slot": "h3_action_i2v",
  "params": {
    "prompt":      {"node": "6",  "input": "text"},
    "first_frame": {"node": "12", "input": "image", "kind": "image"},
    "ref_images":  [{"node": "20", "input": "image", "kind": "image"},
                    {"node": "21", "input": "image", "kind": "image"}],
    "frames":      {"node": "3",  "input": "length"},
    "seed":        {"node": "3",  "input": "seed"}
  },
  "output_node": "30"
}
```

Params: prompt, negative, first_frame, last_frame, ref_images[], width, height, frames, seed, steps.
`frames` is snapped to H3's 17k+5 grid for `h3_*` slots. `spritewaffle comfy check --template <slot>`
validates the map against the workflow and the live node list.

Slots: anchor_still, facing_multiref, transition_pose, bridge_frame, h3_action_fl2va, h3_action_i2v,
h3_turntable, h3_tara_transfer, sam3_mask.
