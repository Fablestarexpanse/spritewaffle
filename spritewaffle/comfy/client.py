"""ComfyUI HTTP/WebSocket client: connect, validate, upload, queue, wait, download. Stdlib HTTP."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import templates


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base: str = "http://127.0.0.1:8188", timeout: float = 30):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex
        self._object_info: dict | None = None

    # --- plumbing -----------------------------------------------------------------------
    def _req(self, path: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise ComfyError(f"{path}: HTTP {e.code} {e.read()[:500]!r}") from e
        except urllib.error.URLError as e:
            raise ComfyError(f"cannot reach ComfyUI at {self.base}: {e.reason}") from e

    def _json(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        hdr = {"Content-Type": "application/json"} if payload is not None else {}
        return json.loads(self._req(path, data, hdr))

    # --- API ----------------------------------------------------------------------------
    def system_stats(self) -> dict:
        return self._json("/system_stats")

    def object_info(self) -> dict:
        if self._object_info is None:
            self._object_info = self._json("/object_info")
        return self._object_info

    def check(self) -> dict:
        stats = self.system_stats()
        info = self.object_info()
        return {"version": stats.get("system", {}).get("comfyui_version"), "node_count": len(info),
                "devices": [d.get("name") for d in stats.get("devices", [])]}

    def missing_nodes(self, workflow: dict) -> list[str]:
        info = self.object_info()
        return sorted(c for c in templates.class_types(workflow) if c not in info)

    def upload_image(self, path: str | Path, overwrite: bool = True) -> str:
        """POST /upload/image (multipart). Returns the name to put in LoadImage inputs."""
        path = Path(path)
        boundary = uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode() + path.read_bytes() + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
            f"{'true' if overwrite else 'false'}\r\n".encode(),
            f"--{boundary}--\r\n".encode(),
        ]
        r = json.loads(self._req("/upload/image", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
        return f"{r['subfolder']}/{r['name']}" if r.get("subfolder") else r["name"]

    def queue(self, workflow: dict) -> str:
        missing = self.missing_nodes(workflow)
        if missing:
            raise ComfyError(f"ComfyUI lacks nodes: {missing}")
        r = self._json("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if r.get("node_errors"):
            raise ComfyError(f"node errors: {r['node_errors']}")
        return r["prompt_id"]

    def history(self, prompt_id: str) -> dict | None:
        return self._json(f"/history/{prompt_id}").get(prompt_id)

    def wait(self, prompt_id: str, timeout: float = 3600, poll: float = 1.0, on_progress=None) -> dict:
        """Block until the prompt finishes. Listens on /ws for progress when available,
        always confirms completion via /history."""
        deadline = time.time() + timeout
        try:
            self._ws_wait(prompt_id, deadline, on_progress)
        except Exception:
            pass                                 # no websocket (mock, proxy): fall back to polling
        while time.time() < deadline:
            h = self.history(prompt_id)
            if h:
                status = h.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(f"prompt {prompt_id} failed: {status.get('messages')}")
                if status.get("completed", True):
                    return h
            time.sleep(poll)
        raise ComfyError(f"prompt {prompt_id} timed out")

    def _ws_wait(self, prompt_id: str, deadline: float, on_progress) -> None:
        from websockets.sync.client import connect
        url = self.base.replace("http", "ws", 1) + f"/ws?clientId={self.client_id}"
        with connect(url, open_timeout=3) as ws:
            while time.time() < deadline:
                msg = ws.recv(timeout=max(1.0, deadline - time.time()))
                if isinstance(msg, bytes):
                    continue                     # preview images
                m = json.loads(msg)
                d = m.get("data", {})
                if d.get("prompt_id") not in (None, prompt_id):
                    continue
                if m["type"] == "progress" and on_progress:
                    on_progress(d.get("value"), d.get("max"))
                if m["type"] == "executing" and d.get("node") is None and d.get("prompt_id") == prompt_id:
                    return
                if m["type"] == "execution_error":
                    return

    def download_outputs(self, hist: dict, node: str | None, out_dir: str | Path) -> list[Path]:
        """GET /view for every file the node (or all nodes) produced."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        outputs = hist.get("outputs", {})
        nodes = [str(node)] if node is not None else list(outputs)
        files = []
        for nid in nodes:
            for key, items in outputs.get(nid, {}).items():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict) or "filename" not in it:
                        continue
                    q = urllib.parse.urlencode({"filename": it["filename"], "subfolder": it.get("subfolder", ""),
                                                "type": it.get("type", "output")})
                    p = out / it["filename"]
                    p.write_bytes(self._req(f"/view?{q}"))
                    files.append(p)
        if not files:
            raise ComfyError(f"no output files on node {node}")
        return files

    def run_template(self, slot: str, values: dict, out_dir: str | Path,
                     base: Path = templates.TEMPLATES_DIR, timeout: float = 3600) -> dict:
        """Upload image params, inject, queue, wait, download. Returns provenance."""
        wf, mp = templates.load(slot, base)
        vals = dict(values)
        for k in templates.IMAGE_PARAMS:
            if vals.get(k) is None:
                continue
            if k == "ref_images":
                vals[k] = [self.upload_image(p) for p in vals[k]]
            else:
                vals[k] = self.upload_image(vals[k])
        prompt_id = self.queue(templates.inject(wf, mp, vals))
        hist = self.wait(prompt_id, timeout=timeout)
        files = self.download_outputs(hist, mp["output_node"], out_dir)
        return {"slot": slot, "prompt_id": prompt_id, "values": {k: v for k, v in values.items()},
                "files": [str(f) for f in files]}
