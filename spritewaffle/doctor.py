"""`spritewaffle doctor`: one place to see whether everything SpriteWaffle needs is in order."""
from __future__ import annotations

import sys
from pathlib import Path

from . import __version__, paths

OK, WARN, FAIL = "ok", "warn", "fail"


def _combo_values(info: dict, cls: str, name: str) -> list | None:
    """Allowed values for a combo input of a node class (None if not a combo)."""
    spec = info.get(cls, {}).get("input", {})
    for group in ("required", "optional"):
        v = spec.get(group, {}).get(name)
        if v and isinstance(v[0], list):
            return v[0]
        if v and v[0] == "COMBO" and len(v) > 1 and isinstance(v[1], dict):
            return v[1].get("options")
    return None


def check(comfy_url: str | None = None) -> list[tuple[str, str, str]]:
    from .comfy import templates
    from .comfy.client import ComfyClient, ComfyError
    from .core import motion
    from .core.profile import list_all as profiles
    from .core.queue import pid_alive

    out = [(OK if sys.version_info >= (3, 11) else FAIL, "python", sys.version.split()[0]),
           (OK, "spritewaffle", f"{__version__} at {paths.root()}")]
    jobs = paths.jobs()
    try:
        jobs.mkdir(parents=True, exist_ok=True)
        probe = jobs / ".write_test"
        probe.write_text("x")
        probe.unlink()
        out.append((OK, "jobs folder", str(jobs)))
    except OSError as e:
        out.append((FAIL, "jobs folder", f"{jobs}: {e}"))
    out.append((OK if profiles() else WARN, "profiles", ", ".join(profiles()) or "none (the built-in default is used)"))

    loaded = {}
    for slot in templates.SLOTS:
        if not (paths.templates() / f"{slot}.json").exists():
            out.append((WARN, f"template {slot}", "not exported (stages using it are unavailable)"))
            continue
        try:
            loaded[slot] = templates.load(slot)[0]
        except ValueError as e:
            out.append((FAIL, f"template {slot}", str(e)))

    try:
        comfy_url = comfy_url or ComfyClient().base
        client = ComfyClient(comfy_url, timeout=10)
        info = client.check()
        out.append((OK, "ComfyUI", f"{info['version']} at {comfy_url}, {info['node_count']} nodes"))
        obj = client.object_info()
        for slot, wf in loaded.items():
            problems = [f"node {c} not installed" for c in client.missing_nodes(wf)]
            for nid, node in wf.items():
                for name, val in node["inputs"].items():
                    if isinstance(val, str) and val.endswith((".safetensors", ".ckpt", ".pt", ".pth", ".gguf")):
                        allowed = _combo_values(obj, node["class_type"], name)
                        if allowed is not None and val not in allowed:
                            problems.append(f"model missing: {val}")
            out.append((FAIL if problems else OK, f"template {slot}", ("; ".join(problems) + " (see docs/COMFYUI_SETUP.md)") if problems else "nodes + models present"))
    except ComfyError as e:
        out.append((FAIL, "ComfyUI", f"{e} (generation stages need it; frame processing does not)"))

    lock = jobs / "_queue" / "worker.lock"
    if lock.exists():
        parts = lock.read_text().split()
        pid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1
        out.append((OK if pid_alive(pid) else WARN, "queue worker",
                    f"running (pid {pid})" if pid_alive(pid) else f"stale lock from pid {pid} (taken over automatically)"))
    else:
        out.append((OK, "queue worker", "not running (start `spritewaffle ui` or `spritewaffle worker`)"))
    lib = motion.list_all(jobs)
    out.append((OK, "motion library", f"{sum(m['status'] == 'approved' for m in lib)} approved / {len(lib)} total"))
    return out


def render(rows: list[tuple[str, str, str]]) -> str:
    mark = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}
    width = max(len(r[1]) for r in rows)
    return "\n".join(f"{mark[s]} {name:<{width}}  {detail}" for s, name, detail in rows)
