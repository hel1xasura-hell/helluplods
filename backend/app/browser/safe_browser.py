"""Playwright page capture with SSRF protection on every request, blocked downloads and robots.txt respect."""
import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from app.services.ssrf import UnsafeURL, validate_public_url

USER_AGENT = "HellUploadsResearchBot/0.1 (+private owner research)"
Validator = Callable[[str], str]


class RobotsDisallowed(Exception):
    pass


@dataclass
class PageCapture:
    requested_url: str
    final_url: str
    status: int | None
    title: str
    description: str
    headings: list[str]
    nav_links: list[dict]
    text_excerpt: str
    screenshot_png: bytes
    console: list[str] = field(default_factory=list)
    blocked_requests: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    robots_checked: bool = False


def robots_allows(robots_txt: str | None, url: str, agent: str = USER_AGENT) -> bool:
    """A missing robots.txt allows crawling; otherwise obey it."""
    if not robots_txt:
        return True
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(agent, url)


_EXTRACT_JS = """
() => {
  const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
  const meta = (n) => (document.querySelector(`meta[name="${n}"], meta[property="${n}"]`) || {}).content || '';
  const headings = [...document.querySelectorAll('h1,h2,h3')].map(text).filter(Boolean).slice(0, 40);
  const links = [...document.querySelectorAll('nav a[href], header a[href], footer a[href]')]
    .map(a => ({label: text(a), href: a.href})).filter(l => l.label && l.label.length < 80).slice(0, 80);
  return {
    title: document.title || '',
    description: meta('description') || meta('og:description'),
    headings, links,
    body: (document.body ? document.body.innerText : '').slice(0, 20000),
  };
}
"""


async def capture_page(
    url: str,
    validator: Validator = validate_public_url,
    timeout_ms: int = 20000,
    respect_robots: bool = True,
) -> PageCapture:
    from playwright.async_api import async_playwright  # imported lazily

    await asyncio.to_thread(validator, url)
    blocked: list[str] = []
    history: list[str] = []
    console: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            ctx = await browser.new_context(
                user_agent=USER_AGENT, accept_downloads=False, java_script_enabled=True,
                viewport={"width": 1366, "height": 768}, service_workers="block",
            )

            async def guard(route):
                req_url = route.request.url
                if req_url.startswith(("data:", "blob:", "about:")):
                    return await route.continue_()
                try:
                    await asyncio.to_thread(validator, req_url)
                except UnsafeURL:
                    blocked.append(req_url)
                    return await route.abort("blockedbyclient")
                await route.continue_()

            await ctx.route("**/*", guard)
            page = await ctx.new_page()
            page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:300]))
            page.on("framenavigated", lambda f: history.append(f.url) if f == page.main_frame else None)
            page.on("download", lambda d: asyncio.ensure_future(d.cancel()))

            robots_checked = False
            if respect_robots:
                parts = urlsplit(url)
                robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
                try:
                    await asyncio.to_thread(validator, robots_url)
                    resp = await ctx.request.get(robots_url, timeout=8000, max_redirects=0)
                    robots_txt = await resp.text() if resp.ok else None
                    robots_checked = True
                except Exception:
                    robots_txt = None
                if not robots_allows(robots_txt, url):
                    raise RobotsDisallowed(f"robots.txt disallows {url}")

            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            final_url = page.url
            await asyncio.to_thread(validator, final_url)  # redirect target must also be public
            data = await page.evaluate(_EXTRACT_JS)
            shot = await page.screenshot(type="png", full_page=False)
            links = [
                {"label": l["label"], "href": urljoin(final_url, l["href"])} for l in data["links"]
                if re.match(r"^https?://", urljoin(final_url, l["href"]))
            ]
            return PageCapture(
                requested_url=url, final_url=final_url, status=response.status if response else None,
                title=data["title"], description=data["description"], headings=data["headings"],
                nav_links=links, text_excerpt=data["body"], screenshot_png=shot, console=console,
                blocked_requests=blocked, history=history, robots_checked=robots_checked,
            )
        finally:
            await browser.close()


EXPLORE_WORDS = ("feature", "pricing", "plans", "product", "how it works", "docs", "documentation", "help", "guide")


def pick_links_to_explore(start: PageCapture, limit: int = 3) -> list[str]:
    """Same-site links whose label or path suggests features, pricing or docs. Deterministic and capped."""
    base = urlsplit(start.final_url).netloc.removeprefix("www.")
    chosen: list[str] = []
    for link in start.nav_links:
        href = link["href"].split("#")[0]
        parts = urlsplit(href)
        if parts.netloc.removeprefix("www.") != base or href.rstrip("/") == start.final_url.rstrip("/"):
            continue
        text = f"{link['label']} {parts.path}".lower()
        if any(w in text for w in EXPLORE_WORDS) and href not in chosen:
            chosen.append(href)
        if len(chosen) >= limit:
            break
    return chosen


async def explore_site(
    url: str, validator: Validator = validate_public_url, max_extra_pages: int = 3, delay_seconds: float = 1.0,
    on_page=None,
) -> list[PageCapture]:
    """Capture the start page, then politely visit a few relevant same-site pages. Failures on extra pages
    are skipped (recorded as blocked) rather than failing the whole run."""
    first = await capture_page(url, validator=validator)
    pages = [first]
    total = 1 + len(pick_links_to_explore(first, max_extra_pages))
    # on_page(capture, index, total) -> False asks the explorer to stop (owner pressed Stop)
    if on_page and not await on_page(first, 1, total):
        return pages
    for href in pick_links_to_explore(first, max_extra_pages):
        await asyncio.sleep(delay_seconds)
        try:
            pages.append(await capture_page(href, validator=validator))
            if on_page and not await on_page(pages[-1], len(pages), total):
                break
        except (UnsafeURL, RobotsDisallowed):
            first.blocked_requests.append(href)
        except Exception:
            continue
    return pages
