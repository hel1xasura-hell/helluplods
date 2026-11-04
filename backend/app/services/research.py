"""Research pipeline (extraction-only, plus optional AI suggestions).

Builds a report from what was actually observed. It does not guess features, and it never claims hands-on
testing: `tested_hands_on` is only true when a workflow was really exercised (not yet implemented)."""
import asyncio
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.browser.safe_browser import PageCapture, RobotsDisallowed, explore_site
from app.models import AgentRun, Notification, ResearchReport, ResearchTarget, Screenshot, Source, StorageObject
from app.services.ai import AINotConfigured, AIProvider, get_ai_provider
from app.services.ai_enrichment import suggest_tutorial_opportunities
from app.services.claims import check_claim
from app.services.ssrf import UnsafeURL
from app.services.storage import Storage
from app.services.untrusted import sanitize_untrusted

CaptureFn = Callable[..., Awaitable[list[PageCapture]]]  # (url, on_page=None) -> pages
MAX_PAUSE_SECONDS = 15 * 60
PRICING_WORDS = ("pricing", "plans", "price")
DOC_WORDS = ("docs", "documentation", "help", "support", "guide", "api")
PRICE_RE = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d{1,2})?(?:\s?/\s?(?:mo|month|yr|year|user|seat))?", re.IGNORECASE)


def resolve_target_url(target: ResearchTarget) -> str | None:
    """Only URL-type targets can be opened. Names need a search/AI step that is not available yet."""
    return target.value if target.kind in {"website_url", "play_url"} else None


def _host(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def _is_pricing(cap: PageCapture) -> bool:
    return any(w in urlsplit(cap.final_url).path.lower() or w in cap.title.lower() for w in PRICING_WORDS)


def build_report(target: ResearchTarget, caps: list[PageCapture], screenshot_ids: list[str],
                 stopped: bool = False) -> dict:
    main = caps[0]
    title, title_flags = sanitize_untrusted(main.title, 300)
    desc, desc_flags = sanitize_untrusted(main.description, 600)
    flagged = bool(title_flags or desc_flags)
    links = [{"label": sanitize_untrusted(l["label"], 80)[0], "href": l["href"]} for l in main.nav_links]
    is_store = target.kind == "play_url"
    now = datetime.now(timezone.utc).isoformat()

    features, seen = [], set()
    for cap in caps:
        body_clean, body_flags = sanitize_untrusted(cap.text_excerpt, 3000)
        flagged = flagged or bool(body_flags)
        for h in cap.headings:
            name, hflags = sanitize_untrusted(h, 160)
            flagged = flagged or bool(hflags)
            if name and name.lower() not in seen and len(features) < 30:
                seen.add(name.lower())
                features.append({"name": name, "verified": False, "evidence": f"Heading on {cap.final_url}"})

    pricing_pages = [c for c in caps if _is_pricing(c)]
    prices = []
    for c in pricing_pages:
        prices += PRICE_RE.findall(sanitize_untrusted(c.text_excerpt, 6000)[0])
    pricing_links = [l for l in links if any(w in l["label"].lower() or w in l["href"].lower() for w in PRICING_WORDS)][:5]
    doc_links = [l for l in links if any(w in l["label"].lower() or w in l["href"].lower() for w in DOC_WORDS)][:5]

    sources = [{"url": c.final_url, "official": (not is_store) and _host(c.final_url) == _host(main.final_url),
                "fetched_at": now} for c in caps]
    fetched = {s["url"] for s in sources}
    sources += [{"url": l["href"], "official": _host(l["href"]) == _host(main.final_url), "fetched_at": None}
                for l in doc_links if l["href"] not in fetched]

    return {
        "target_name": title or _host(main.final_url),
        "target_kind": target.kind,
        "canonical_url": main.final_url,
        "publisher": None,
        "description": desc or None,
        "features": features,
        "demonstrated_workflows": [],
        "pricing": {"pages_found": pricing_links, "read": bool(pricing_pages),
                    "observed_prices": sorted(set(p.strip() for p in prices))[:12], "verified": False},
        "limitations": [
            f"Surface extraction from {len(caps)} page load(s): headings, navigation and metadata only.",
            "No workflows were exercised.",
            *(["The owner stopped this run early, so some planned pages were not visited."] if stopped else []),
            *(["Google Play listing only; the app itself was not installed or tested."] if is_store else []),
        ],
        "pages_explored": [{"url": c.final_url, "title": sanitize_untrusted(c.title, 200)[0], "status": c.status}
                           for c in caps],
        "screenshot_ids": screenshot_ids,
        "recording_ids": [],
        "sources": sources,
        "navigation": links[:40],
        "verification": {
            "verified_at": now, "redirected": main.requested_url.rstrip("/") != main.final_url.rstrip("/"),
            "http_status": main.status, "robots_checked": main.robots_checked,
            "blocked_requests": [b for c in caps for b in c.blocked_requests][:20],
        },
        "unverified_claims": [d for d in [desc] if d],
        "claim_checks": [check_claim(d, {c.final_url: c.text_excerpt + " " + c.title for c in caps})
                         for d in [desc] if d],
        "tutorial_opportunities": [],
        "tutorial_opportunities_source": None,
        "security_flags": {"possible_prompt_injection": flagged},
        "tested_hands_on": False,
        "page_text_excerpt": sanitize_untrusted(main.text_excerpt, 1500)[0],
    }


async def _default_capture(url: str, on_page=None) -> list[PageCapture]:  # pragma: no cover - real browser
    return await explore_site(url, on_page=on_page)


async def _maybe_enrich(report: dict, provider: AIProvider | None) -> None:
    try:
        provider = provider or get_ai_provider()
    except AINotConfigured:
        return
    try:
        ideas = await suggest_tutorial_opportunities(provider, report)
    except Exception:
        return  # AI suggestions are optional; a failure must not fail research
    if ideas:
        report["tutorial_opportunities"] = ideas
        report["tutorial_opportunities_source"] = "ai_suggestion_unverified"


def run_research(
    db: Session, target_id: uuid.UUID, storage: Storage, capture: CaptureFn | None = None,
    ai_provider: AIProvider | None = None,
) -> None:
    """Synchronous entry point (background task / worker). Updates target status and stores results."""
    capture = capture or _default_capture
    target = db.get(ResearchTarget, target_id)
    if target is None:
        return
    project = target.project
    run = AgentRun(project_id=project.id, agent_key="research", status="running",
                   input={"target_id": str(target.id)}, started_at=datetime.now(timezone.utc))
    db.add(run)
    target.status, target.error = "running", None
    db.commit()

    def finish(status: str, error: str | None = None, output: dict | None = None):
        run.control = None
        run.status = {"done": "succeeded", "failed": "failed"}.get(status, "needs_input")
        run.error, run.output = error, output
        run.finished_at = datetime.now(timezone.utc)
        run.progress = 1.0
        target.status, target.error = status, error
        titles = {"done": "Research finished", "failed": "Research failed", "needs_url": "Research needs a URL"}
        db.add(Notification(owner_id=project.owner_id, kind="research", title=titles.get(status, "Research update"),
                            body=(error or target.value)[:300]))
        db.commit()

    url = resolve_target_url(target)
    if url is None:
        run.logs = [{"msg": "Name targets need a URL; automatic resolution requires an AI/search provider."}]
        return finish("needs_url", "Add the official URL for this target so it can be opened and verified.")
    state = {"stopped": False}

    async def on_page(cap: PageCapture, index: int, total: int) -> bool:
        """Called after every page: report progress, honour Pause and Stop from the owner."""
        run.progress = min(0.9, index / max(total, 1) * 0.9)
        run.current_url = cap.final_url
        db.commit()
        waited = 0.0
        while True:
            db.refresh(run)
            if run.control == "stop":
                state["stopped"] = True
                return False
            if run.control != "pause":
                break
            if run.status != "paused":
                run.status = "paused"
                db.commit()
            if waited >= MAX_PAUSE_SECONDS:
                state["stopped"] = True
                return False
            await asyncio.sleep(1)
            waited += 1
        if run.status == "paused":
            run.status = "running"
            db.commit()
        return True

    try:
        caps = asyncio.run(capture(url, on_page=on_page))
    except UnsafeURL as exc:
        return finish("failed", f"URL blocked: {exc}")
    except RobotsDisallowed as exc:
        return finish("failed", str(exc))
    except Exception as exc:
        return finish("failed", f"Browser capture failed: {type(exc).__name__}: {exc}"[:500])
    if not caps:
        return finish("failed", "The page produced no content.")

    shot_ids: list[str] = []
    for cap in caps:
        key = f"{project.owner_id}/{project.id}/screenshots/{uuid.uuid4()}.png"
        meta = storage.put(key, cap.screenshot_png, "image/png")
        obj = StorageObject(owner_id=project.owner_id, backend=storage.backend, key=key,
                            content_type="image/png", size_bytes=meta["size_bytes"], sha256=meta["sha256"])
        db.add(obj)
        db.flush()
        shot = Screenshot(project_id=project.id, storage_object_id=obj.id, url=cap.final_url,
                          captured_at=datetime.now(timezone.utc))
        db.add(shot)
        db.flush()
        shot_ids.append(str(shot.id))

    body = build_report(target, caps, shot_ids, stopped=state["stopped"])
    asyncio.run(_maybe_enrich(body, ai_provider))
    report = ResearchReport(target_id=target.id, body=body, tested_hands_on=False,
                            verified_at=datetime.now(timezone.utc))
    db.add(report)
    db.flush()
    for s in body["sources"]:
        db.add(Source(report_id=report.id, url=s["url"][:2048], is_official=s["official"]))
    target.canonical_url = caps[0].final_url
    run.logs = [{"msg": "capture complete", "pages": len(caps),
                 "blocked": sum(len(c.blocked_requests) for c in caps)}]
    finish("done", output={"report_id": str(report.id)})
    if state["stopped"]:
        run.status = "cancelled"
        db.commit()
