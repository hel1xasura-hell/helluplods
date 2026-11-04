"""Minimal HTTP client for the HELL UPLOADS device API (stdlib only)."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


def require_safe_server(url: str) -> str:
    parts = urlsplit(url)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme != "https" and not local:
        raise ValueError("Server URL must use https (plain http is only allowed for localhost development).")
    return url.rstrip("/")


class Client:
    def __init__(self, server: str, credential: str | None = None, timeout: float = 30):
        self.server, self.credential, self.timeout = require_safe_server(server), credential, timeout

    def _req(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None,
             auth: bool = True):
        req = urllib.request.Request(f"{self.server}{path}", data=body, method=method)
        if content_type:
            req.add_header("Content-Type", content_type)
        if auth and self.credential:
            req.add_header("Authorization", f"Device {self.credential}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise ApiError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise ApiError(0, f"Can't reach the server: {exc.reason}") from exc

    def _json(self, method, path, payload, auth=True):
        return self._req(method, path, json.dumps(payload).encode(), "application/json", auth)

    def pair(self, code: str, name: str, platform: str) -> dict:
        return self._json("POST", "/api/devices/pair", {"code": code, "name": name, "platform": platform}, auth=False)

    def heartbeat(self) -> None:
        self._req("POST", "/api/device/heartbeat")

    def claim(self) -> dict | None:
        return self._req("POST", "/api/device/tasks/claim")["task"]

    def upload(self, task_id: str, data: bytes) -> dict:
        return self._req("PUT", f"/api/device/tasks/{task_id}/file", data, "application/octet-stream")

    def complete(self, task_id: str, meta: dict) -> dict:
        return self._json("POST", f"/api/device/tasks/{task_id}/complete", meta)

    def fail(self, task_id: str, error: str) -> None:
        self._json("POST", f"/api/device/tasks/{task_id}/fail", {"error": error[:500]})
