"""HELL UPLOADS desktop companion (Windows, macOS, Linux).

  python -m companion pair --server https://api.example.com --code ABCDE-FGH23
  python -m companion run  --server https://api.example.com

Pairs with a one-time code, then polls for recording tasks, records them locally with Playwright (real
screen capture of a real browser), and uploads the result. The credential is stored in a user-only file."""
import argparse
import asyncio
import json
import os
import socket
import stat
import sys
import tempfile
import time
from pathlib import Path

from companion.client import ApiError, Client
from companion.vendor.recorder import RecordingRefused, record_tour
from companion.vendor.ssrf import UnsafeURL, validate_public_url

CONFIG_PATH = Path(os.environ.get("HELL_COMPANION_CONFIG", Path.home() / ".hell-uploads" / "companion.json"))


def platform_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def save_config(data: dict, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # best effort; Windows ignores POSIX modes
    except OSError:
        pass


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise SystemExit("Not paired yet. Run: python -m companion pair --server URL --code CODE")
    return json.loads(path.read_text())


def make_validator(allow_hosts: list[str]):
    """Public URLs only, unless the owner explicitly allows specific hosts (e.g. their own dev site)."""
    allowed = set(allow_hosts)

    def validate(url: str) -> str:
        from urllib.parse import urlsplit
        if urlsplit(url).netloc in allowed:
            return url
        return validate_public_url(url)

    return validate


def process_task(client: Client, task: dict, validator) -> str:
    """Record one task and upload it. Returns 'done' or 'failed'."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            result = asyncio.run(record_tour(task["url"], Path(tmp), validator,
                                             duration_seconds=float(task.get("duration_seconds", 10))))
            client.upload(task["id"], result.path.read_bytes())
            client.complete(task["id"], {
                "duration_seconds": result.duration_seconds, "width": result.width, "height": result.height,
                "final_url": result.final_url, "actions": result.actions})
            return "done"
        except (UnsafeURL, RecordingRefused) as exc:
            client.fail(task["id"], str(exc))
        except Exception as exc:  # report and keep the loop alive
            client.fail(task["id"], f"{type(exc).__name__}: {exc}")
        return "failed"


def run_loop(client: Client, validator, once: bool = False, poll_seconds: float = 5.0) -> int:
    processed = 0
    while True:
        try:
            client.heartbeat()
            task = client.claim()
            if task:
                print(f"Recording {task['url']} ...", flush=True)
                print(process_task(client, task, validator), flush=True)
                processed += 1
                if once:
                    return processed
                continue
            if once:
                return processed
        except ApiError as exc:
            if exc.status == 401:
                raise SystemExit("This device was revoked or its credential is invalid. Pair again.")
            print(f"Server problem: {exc}", flush=True)
            if once:
                return processed
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="companion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pair", "run"):
        p = sub.add_parser(name)
        p.add_argument("--server", required=True)
        p.add_argument("--allow-host", action="append", default=[], help="host:port you explicitly trust")
    sub.choices["pair"].add_argument("--code", required=True)
    sub.choices["pair"].add_argument("--name", default=socket.gethostname())
    sub.choices["run"].add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "pair":
        res = Client(args.server).pair(args.code, args.name, platform_name())
        save_config({"server": args.server, "credential": res["credential"], "device_id": res["device_id"]})
        print("Paired. You can now run: python -m companion run --server", args.server)
        return 0
    cfg = load_config()
    client = Client(args.server or cfg["server"], cfg["credential"])
    run_loop(client, make_validator(args.allow_host), once=args.once)
    return 0
