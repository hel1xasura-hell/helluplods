"""Real screen recording of a browser session with Playwright (WebM). Standalone: only stdlib + playwright, so the
desktop companion can vendor this exact file. The caller supplies the URL validator (SSRF policy).

A recording is a genuine capture of a real page load and scroll tour. Nothing is synthesised."""
import asyncio
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "HellUploadsResearchBot/0.1 (+private owner research)"


class RecordingRefused(Exception):
    pass


@dataclass
class RecordingResult:
    path: Path
    duration_seconds: float
    width: int
    height: int
    final_url: str
    actions: list[dict] = field(default_factory=list)  # timestamped scrolls/mouse moves, for cursor highlights
    blocked_requests: list[str] = field(default_factory=list)


def _robots_ok(txt: str | None, url: str) -> bool:
    if not txt:
        return True
    p = RobotFileParser()
    p.parse(txt.splitlines())
    return p.can_fetch(USER_AGENT, url)


async def record_tour(
    url: str,
    out_dir: Path,
    validator: Callable[[str], str],
    duration_seconds: float = 10.0,
    size: tuple[int, int] = (1280, 720),
    should_stop: Callable[[], bool] | None = None,
) -> RecordingResult:
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(validator, url)
    blocked: list[str] = []
    actions: list[dict] = []
    t0 = time.monotonic()
    stamp = lambda: round(time.monotonic() - t0, 2)  # noqa: E731  (reads t0 at call time)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            ctx = await browser.new_context(
                user_agent=USER_AGENT, accept_downloads=False, service_workers="block",
                viewport={"width": size[0], "height": size[1]},
                record_video_dir=str(out_dir), record_video_size={"width": size[0], "height": size[1]},
            )

            async def guard(route):
                u = route.request.url
                if u.startswith(("data:", "blob:", "about:")):
                    return await route.continue_()
                try:
                    await asyncio.to_thread(validator, u)
                except Exception:
                    blocked.append(u)
                    return await route.abort("blockedbyclient")
                await route.continue_()

            await ctx.route("**/*", guard)
            parts = urlsplit(url)
            try:
                resp = await ctx.request.get(f"{parts.scheme}://{parts.netloc}/robots.txt", timeout=8000, max_redirects=0)
                robots = await resp.text() if resp.ok else None
            except Exception:
                robots = None
            if not _robots_ok(robots, url):
                raise RecordingRefused(f"robots.txt disallows {url}")

            page = await ctx.new_page()
            t0 = time.monotonic()  # the video starts when the page is created; action times are relative to it
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.to_thread(validator, page.url)  # redirects must stay public too
            actions.append({"t": stamp(), "type": "load", "url": page.url})
            await page.wait_for_timeout(1200)

            height = await page.evaluate("document.documentElement.scrollHeight")
            view = size[1]
            steps = max(1, min(8, int(duration_seconds // 1.2)))
            max_scroll = max(0, height - view)
            for i in range(1, steps + 1):
                if should_stop and should_stop():
                    break
                y = int(max_scroll * i / steps)
                await page.mouse.move(size[0] * (0.3 + 0.4 * (i % 2)), view * 0.5, steps=15)
                actions.append({"t": stamp(), "type": "mouse", "x": int(size[0] * (0.3 + 0.4 * (i % 2))), "y": int(view * 0.5)})
                await page.evaluate("y => window.scrollTo({top: y, behavior: 'smooth'})", y)
                actions.append({"t": stamp(), "type": "scroll", "y": y})
                await page.wait_for_timeout(int(max(800, duration_seconds * 1000 / steps)))
            final_url = page.url
            video = page.video
            await ctx.close()  # flushes the video file
            path = Path(await video.path()) if video else None
        finally:
            await browser.close()

    if path is None or not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("The browser produced no video file")
    duration = probe_duration(path) or round(time.monotonic() - t0, 2)
    return RecordingResult(path, duration, size[0], size[1], final_url, actions, blocked)


def probe_duration(path: Path) -> float | None:
    """Real duration from the file via ffprobe when available."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return round(float(out), 2)
    except (ValueError, subprocess.SubprocessError):
        return None


def looks_like_video(head: bytes) -> bool:
    """Magic-byte check: WebM/Matroska (EBML) or MP4 (ftyp). Used to validate uploads."""
    return head[:4] == b"\x1a\x45\xdf\xa3" or head[4:8] == b"ftyp"
