# Install SpriteWaffle (instructions for an AI agent)

> **Human:** paste this to your coding agent (Claude Code, Codex, Cursor, …):
>
> *Install SpriteWaffle by following `AGENT_INSTALL.md` in https://github.com/Fablestarexpanse/spritewaffle. Ask me before downloading models.*

---

**Agent:** do these steps in order and stop to ask the human where it says **ASK**. Windows +
PowerShell is assumed. Adapt the paths on Linux/macOS (`.venv/bin/` instead of `.venv\Scripts\`).
Once installed, SpriteWaffle runs without you. The human uses the web UI or CLI, and the MCP server is optional.

## 1. Check prerequisites

```powershell
python --version        # need 3.11 or newer
git --version
nvidia-smi              # an NVIDIA GPU; 24 GB VRAM tested
```

**ASK** where their ComfyUI is installed (the folder with `main.py` and `models/`), and whether
it is running at `http://127.0.0.1:8188`. If they have no ComfyUI, point them to
https://github.com/comfyanonymous/ComfyUI (or Stability Matrix) and wait. It must be **0.45 or newer**.

## 2. Get the code and install

```powershell
git clone https://github.com/Fablestarexpanse/spritewaffle.git
cd spritewaffle
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
.venv\Scripts\python -m pip install -e ".[dev]" --no-deps
.venv\Scripts\python -m pytest -q
```

All tests must pass. They don't need ComfyUI.

## 3. Models

Run `.venv\Scripts\spritewaffle doctor`. Every `[FAIL] template … model missing: X` names a
file that ComfyUI doesn't have. Look up each one in [`docs/COMFYUI_SETUP.md`](docs/COMFYUI_SETUP.md) to get its folder and URL.

**ASK** before downloading. Tell them the total size (required set ≈ 94 GB, optional
features listed separately in that doc) and which features they want: AI prompt writer, sheet
import, TARA. Skip a file they already have under another folder. ComfyUI's
`extra_model_paths.yaml` may map one in.

Download each approved file into `<ComfyUI>\models\<folder>\` with a resumable download:

```powershell
$models = "C:\path\to\ComfyUI\models"            # from the human's answer
$f = "diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors"
$url = "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/$f"
New-Item -ItemType Directory -Force (Split-Path "$models\$f") | Out-Null
curl.exe -L -C - -o "$models\$f" $url
```

LoRAs go in `models\loras\MiniMax H3\`, with the space, because the workflows reference that subfolder.
TARA needs one custom node pack too, if they want it:

```powershell
git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes "C:\path\to\ComfyUI\custom_nodes\ComfyUI-BFSNodes"
```

Downloads are 20 GB+ each. Run them in the background and report progress. After
adding models or nodes, **ask the human to restart ComfyUI**, then run `doctor` again until
every template is `[ ok ]`. (`h3_turntable  not exported` is an expected warning.)

## 4. Address (only if ComfyUI is not on 127.0.0.1:8188)

```powershell
setx SPRITEWAFFLE_COMFY "http://HOST:PORT"
```

## 5. Hand over

```powershell
.venv\Scripts\spritewaffle ui
```

Tell the human to open http://127.0.0.1:8765 and read the README's *Workflows* section. Offer the
optional agent hookup. The human decides; it isn't needed to use the tool.

```powershell
claude mcp add spritewaffle -- "<repo>\.venv\Scripts\spritewaffle.exe" mcp
```

Don't approve anything inside SpriteWaffle for the human. Approval of anchors, facings and
clips is theirs.
