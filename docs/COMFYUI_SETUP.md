# ComfyUI setup

SpriteWaffle has one outside dependency: a local ComfyUI. It does not use Claude or any cloud
service. Claude/MCP is an optional extra (see the README). Frame processing (pixelize, QA,
export, mirror, flow transfer, sprite stacking, showcase) runs without ComfyUI.

## ComfyUI

- ComfyUI **0.45 or newer** (tested on 0.45, Windows 11, RTX 4090 24 GB).
- Listening on `http://127.0.0.1:8188` (set `SPRITEWAFFLE_COMFY`, e.g. `http://192.168.1.20:8188`, to use another address).
- Every node SpriteWaffle uses ships with ComfyUI core, **except** the TARA motion-transfer
  template, which needs [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes)
  (`BFSMiniMaxH3NativeTemporal`). Skip it if you don't use TARA.

## Models

Put each file in the ComfyUI `models/` subfolder shown. LoRAs go in a **`MiniMax H3`
subfolder** under `loras/`, because the templates name them with that prefix. Sizes are as
measured on disk.

### Needed for characters (anchor → facings → actions)

| File | Folder | Size | Used by | Source |
|---|---|---|---|---|
| `minimax_h3_image_pruned_int8_convrot.safetensors` | `diffusion_models/` | 20.0 GB | anchor, facings, transition pose, bridge | [Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors) |
| `minimax_h3_image_vae_fp16.safetensors` | `vae/` | 1.1 GB | image templates | [Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/vae/minimax_h3_image_vae_fp16.safetensors) |
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | `text_encoders/` | 25.9 GB | image templates | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) |
| `qwen3.5_9b_w4a8_gptq.safetensors` | `text_encoders/` | 7.0 GB | image templates (prompt enhancer, switched off but must exist) | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors) |
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `diffusion_models/` | 20.0 GB | action clips (FL2VA, I2V) | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors) |
| `minimax_h3_video_vae_int8_convrot.safetensors` | `vae/` | 3.0 GB | action clips | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors) |
| `minimax_h3_audio_vae_fp32.safetensors` | `vae/` | 0.6 GB | all video templates | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders/` | 15.0 GB | all video templates | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `loras/MiniMax H3/` | 1.9 GB | action clips (turbo toggle, **off** by default but must exist) | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors) |

About 94 GB in total.

### Optional features

| File | Folder | Size | Feature | Source |
|---|---|---|---|---|
| `qwen3vl_4b_bf16.safetensors` | `text_encoders/` | 8.5 GB | AI prompt writer (`Prompts → AI`) | [Comfy-Org/Fibo-2.0](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/text_encoders/qwen3vl_4b_bf16.safetensors) |
| `sam3.1_multiplex_fp16.safetensors` | `checkpoints/` | 1.7 GB | character-sheet import | [Comfy-Org/sam3.1](https://huggingface.co/Comfy-Org/sam3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors) |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `diffusion_models/` | 20.0 GB | TARA motion transfer (experimental) | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) |
| `minimax_h3_video_vae_fp16.safetensors` | `vae/` | 5.0 GB | TARA | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | `loras/MiniMax H3/` | 1.9 GB | TARA | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors) |
| `minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors` | `loras/MiniMax H3/` | 0.1 GB | TARA (community) | [Alissonerdx/Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI) |

Stability Matrix users: its shared folders are `Models/DiffusionModels`, `TextEncoders`, `VAE`,
`Lora`, `StableDiffusion` (checkpoints).

## Check it

```powershell
.venv\Scripts\spritewaffle doctor
```

`doctor` asks your running ComfyUI for every node and model file each template needs, and
names any that are missing.

## The workflows

There are two copies of each workflow:

- [`templates/`](../templates/README.md): **API format**, what SpriteWaffle sends to
  ComfyUI. Each comes with a `.map.json` that says which inputs it fills in. Edit these
  together, or the tool breaks.
- [`comfyui/workflows/`](../comfyui/workflows/): the same graphs in **editor format**, laid out
  in groups with notes. Drag one onto the ComfyUI canvas to inspect it or try it by hand.
  Changes you make there don't affect SpriteWaffle. Export in API format and replace the
  file in `templates/` to apply them.

| Workflow | What it does |
|---|---|
| `anchor_still` | text → the anchor image (H3 Image t2i) on flat #00FF00 |
| `facing_multiref` | anchor (+ nearest cardinal) → one other facing (H3 Image edit) |
| `transition_pose` | facing → the pose that starts and ends a clip |
| `bridge_frame` | in-between frame when a clip needs one |
| `h3_action_fl2va` | first + last frame → action clip (H3 FL2VA) |
| `h3_action_i2v` | first frame only, the fallback when FL2VA freezes |
| `h3_tara_transfer` | TARA motion transfer from a driving clip (experimental, needs BFSNodes) |
| `prompt_writer` | Qwen3-VL 4B looks at the character and writes prompt text |
| `sam3_mask` | SAM 3 cuts figures off a character sheet |
