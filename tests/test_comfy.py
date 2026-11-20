"""Comfy client against an in-process fake ComfyUI (HTTP only, no websocket)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from spritewaffle.comfy import templates
from spritewaffle.comfy.client import ComfyClient, ComfyError

WF = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["3", 0]}},
    "3": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"length": 97, "seed": 0, "width": 512, "height": 512}},
    "9": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "sw"}},
}
MAP = {"slot": "h3_action_i2v", "output_node": "9", "params": {
    "first_frame": {"node": "1", "input": "image", "kind": "image"},
    "prompt": {"node": "2", "input": "text"},
    "frames": {"node": "3", "input": "length"},
    "seed": {"node": "3", "input": "seed"},
}}


class Fake(BaseHTTPRequestHandler):
    queued: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/system_stats":
            self._send({"system": {"comfyui_version": "0.45.0"}, "devices": [{"name": "cuda:0 RTX 4090"}]})
        elif u.path == "/object_info":
            self._send({c: {} for c in ("LoadImage", "CLIPTextEncode", "MiniMaxH3ImageToVideo", "SaveVideo")})
        elif u.path.startswith("/history/"):
            pid = u.path.rsplit("/", 1)[1]
            self._send({pid: {"status": {"status_str": "success", "completed": True},
                              "outputs": {"9": {"images": [{"filename": "sw_0001.mp4", "subfolder": "", "type": "output"}]}}}}
                       if pid in Fake.queued else {})
        elif u.path == "/view":
            self._send(b"VIDEO:" + parse_qs(u.query)["filename"][0].encode(), "video/mp4")
        else:
            self.send_error(404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/prompt":
            wf = json.loads(body)["prompt"]
            Fake.queued["p1"] = wf
            self._send({"prompt_id": "p1", "number": 0, "node_errors": {}})
        elif self.path == "/upload/image":
            assert b'name="image"' in body
            self._send({"name": "up.png", "subfolder": "", "type": "input"})
        else:
            self.send_error(404)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_snap_h3_frames():
    assert [templates.snap_h3_frames(n) for n in (1, 5, 20, 22, 30, 97, 100)] == [5, 5, 22, 22, 22, 90, 107]


def test_map_validation():
    assert templates.validate(WF, MAP) == []
    bad = json.loads(json.dumps(MAP)); bad["params"]["seed"]["input"] = "nope"; bad["output_node"] = "77"
    errs = templates.validate(WF, bad)
    assert any("no input 'nope'" in e for e in errs) and any("output_node" in e for e in errs)


def test_inject_snaps_and_copies():
    wf = templates.inject(WF, MAP, {"prompt": "marching in place", "frames": 48, "seed": 7})
    assert wf["3"]["inputs"]["length"] == 56 and wf["2"]["inputs"]["text"] == "marching in place"
    assert WF["3"]["inputs"]["length"] == 97


def test_client_end_to_end(server, tmp_path):
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "h3_action_i2v.json").write_text(json.dumps(WF))
    (tmp_path / "t" / "h3_action_i2v.map.json").write_text(json.dumps(MAP))
    img = tmp_path / "f.png"; img.write_bytes(b"\x89PNG fake")
    c = ComfyClient(server)
    assert c.check() == {"version": "0.45.0", "node_count": 4, "devices": ["cuda:0 RTX 4090"]}
    prov = c.run_template("h3_action_i2v", {"first_frame": img, "prompt": "walk", "frames": 24, "seed": 3},
                          tmp_path / "out", base=tmp_path / "t")
    assert Fake.queued["p1"]["1"]["inputs"]["image"] == "up.png"
    assert Fake.queued["p1"]["3"]["inputs"]["length"] == 22
    assert (tmp_path / "out" / "sw_0001.mp4").read_bytes() == b"VIDEO:sw_0001.mp4"
    assert prov["prompt_id"] == "p1"


def test_missing_nodes_refused(server):
    wf = dict(WF); wf["5"] = {"class_type": "NotInstalled", "inputs": {}}
    with pytest.raises(ComfyError, match="NotInstalled"):
        ComfyClient(server).queue(wf)


def test_unreachable():
    with pytest.raises(ComfyError, match="cannot reach"):
        ComfyClient("http://127.0.0.1:1", timeout=1).check()
