"""End-to-end test of the companion against a stub of the device API and a local site.
Runs a REAL Chromium recording. Skips if Chromium is unavailable. Run: python -m pytest desktop/tests  (or call directly)."""
import json
import sys
import threading
import http.server
import socketserver
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from companion import agent  # noqa: E402
from companion.client import ApiError, Client, require_safe_server  # noqa: E402

CRED = "hud_testcredential"


def serve(handler_cls):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler_cls)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def make_site():
    body = b"<title>Site</title><h1>Hello</h1>" + b"".join(b"<p style='height:400px'>s%d</p>" % i for i in range(6))

    class Site(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/robots.txt":
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    return serve(Site)


def make_api(site_url, state):
    class Api(http.server.BaseHTTPRequestHandler):
        def _json(self, code, obj=None):
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
            if obj is not None: self.wfile.write(json.dumps(obj).encode())
        def _authed(self):
            if self.headers.get("Authorization") != f"Device {CRED}" or state.get("revoked"):
                self._json(401, {"detail": "bad"}); return False
            return True
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n)
            if self.path == "/api/devices/pair":
                body = json.loads(raw)
                if body["code"] != "TESTC-ODE12": return self._json(400, {"detail": "Invalid or expired pairing code"})
                state["paired"] = body; return self._json(201, {"device_id": "dev1", "credential": CRED})
            if not self._authed(): return
            if self.path == "/api/device/heartbeat": state["beats"] = state.get("beats", 0) + 1; return self._json(204)
            if self.path == "/api/device/tasks/claim":
                task = state["tasks"].pop(0) if state["tasks"] else None
                return self._json(200, {"task": task})
            if self.path.endswith("/complete"): state["complete"] = json.loads(raw); return self._json(200, {"recording_id": "r1"})
            if self.path.endswith("/fail"): state["failed"] = json.loads(raw); return self._json(204)
            self._json(404, {})
        def do_PUT(self):
            n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n)
            if not self._authed(): return
            state["uploaded"] = raw; self._json(200, {"stored": True})
        def log_message(self, *a): pass
    return serve(Api)


def test_pair_record_upload_and_fail_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG_PATH", tmp_path / "cfg.json")
    site, site_url = make_site()
    host = site_url.removeprefix("http://")
    state = {"tasks": [{"id": "t1", "kind": "record", "url": site_url + "/", "duration_seconds": 3},
                       {"id": "t2", "kind": "record", "url": "http://169.254.169.254/", "duration_seconds": 3}]}
    api, api_url = make_api(site_url, state)
    try:
        # pairing: wrong code rejected, right code stores a user-only credential file
        try:
            Client(api_url).pair("WRONG", "pc", "linux"); assert False
        except ApiError as e:
            assert e.status == 400
        res = Client(api_url).pair("TESTC-ODE12", "My PC", "linux")
        agent.save_config({"server": api_url, "credential": res["credential"], "device_id": res["device_id"]}, tmp_path / "cfg.json")
        cfg = json.loads((tmp_path / "cfg.json").read_text())
        assert cfg["credential"] == CRED
        if sys.platform != "win32":
            assert (tmp_path / "cfg.json").stat().st_mode & 0o077 == 0, "config must be user-only"

        client = Client(api_url, CRED)
        validator = agent.make_validator([host])
        assert agent.run_loop(client, validator, once=True) == 1     # task 1: real recording
        assert state["uploaded"][:4] == b"\x1a\x45\xdf\xa3" and len(state["uploaded"]) > 1000
        assert state["complete"]["width"] == 1280 and state["complete"]["duration_seconds"] > 2
        assert any(a["type"] == "scroll" for a in state["complete"]["actions"])

        assert agent.run_loop(client, validator, once=True) == 1     # task 2: metadata IP must be refused
        assert "not publicly routable" in state["failed"]["error"]
        assert agent.run_loop(client, validator, once=True) == 0     # nothing left
        assert state["beats"] >= 3

        state["revoked"] = True                                       # revoked device must stop, not loop
        try:
            agent.run_loop(client, validator, once=True); assert False
        except SystemExit as e:
            assert "revoked" in str(e)
    finally:
        site.shutdown(); api.shutdown()


def test_server_url_must_be_https_unless_local():
    assert require_safe_server("http://localhost:8000/") == "http://localhost:8000"
    assert require_safe_server("https://api.example.com")
    try:
        require_safe_server("http://api.example.com"); assert False
    except ValueError:
        pass


def test_validator_allows_only_explicit_hosts():
    v = agent.make_validator(["127.0.0.1:9999"])
    assert v("http://127.0.0.1:9999/x")
    try:
        v("http://127.0.0.1:8888/x"); assert False
    except Exception as e:
        assert "publicly routable" in str(e)
