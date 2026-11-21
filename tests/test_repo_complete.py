"""The repo ships everything a fresh install needs: editor copies of every workflow, the setup doc
naming every model the templates load, the dependency lock, and the agent install guide."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = sorted(p for p in (ROOT / "templates").glob("*.json") if not p.name.endswith(".map.json"))


def test_every_template_has_an_editor_workflow():
    for p in API:
        ui = ROOT / "comfyui" / "workflows" / p.name
        assert ui.exists(), f"no editor copy of {p.name}"
        d = json.loads(ui.read_text(encoding="utf-8"))
        api_types = {n["class_type"] for n in json.loads(p.read_text(encoding="utf-8")).values()}
        ui_types = {n["type"] for n in d["nodes"]}
        assert api_types <= ui_types, (p.name, api_types - ui_types)


def test_setup_doc_names_every_model():
    doc = (ROOT / "docs" / "COMFYUI_SETUP.md").read_text(encoding="utf-8")
    for p in API:
        for node in json.loads(p.read_text(encoding="utf-8")).values():
            for v in node["inputs"].values():
                if isinstance(v, str) and v.endswith(".safetensors"):
                    assert Path(v.replace("\\", "/")).name in doc, f"{p.name}: {v} not in COMFYUI_SETUP.md"


def test_lock_pins_every_runtime_dependency():
    lock = {l.split("==")[0].lower().replace("_", "-") for l in (ROOT / "requirements-lock.txt").read_text().split()}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.findall(r'"([A-Za-z0-9_.-]+)\s*[=<>~]', pyproject.split("\ndependencies")[1].split("]")[0])
    for d in deps:
        assert d.lower().replace("_", "-") in lock, d


def test_agent_guide_exists_and_readme_links_it():
    assert (ROOT / "AGENT_INSTALL.md").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "AGENT_INSTALL.md" in readme and "COMFYUI_SETUP.md" in readme


def test_comfy_address_from_env():
    out = subprocess.run([sys.executable, "-c", "from spritewaffle.comfy.client import ComfyClient; print(ComfyClient().base)"],
                         env={**__import__("os").environ, "SPRITEWAFFLE_COMFY": "http://10.0.0.5:9000/"},
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "http://10.0.0.5:9000"
