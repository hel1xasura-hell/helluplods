"""Pure YouTube logic: OAuth state/PKCE, upload chunking, quota days, request bodies and the publishing policy.
No network and no framework imports, so it is fully unit-testable."""
import base64
import hashlib
import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

# Least privilege: upload videos and read channel identity. NOT the full "youtube" scope, so this app
# cannot delete videos or change channel settings.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
QUOTA_COST = {"videos.insert": 1600, "thumbnails.set": 50, "channels.list": 1}
DEFAULT_DAILY_QUOTA = 10_000
CHUNK = 8 * 256 * 1024  # resumable uploads need multiples of 256 KiB
VISIBILITIES = {"private", "unlisted", "public"}
PACIFIC = ZoneInfo("America/Los_Angeles")  # YouTube quota resets at midnight Pacific


class OAuthStateError(ValueError):
    pass


# ---------- PKCE + state ----------
def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def make_state(key: str, owner_id: str, verifier: str, ttl: int = 600, now: float | None = None) -> str:
    """Authenticated-encrypted state: the callback proves who started the flow and carries the PKCE verifier
    without exposing it to the browser."""
    payload = {"o": owner_id, "v": verifier, "e": (now or time.time()) + ttl, "n": secrets.token_hex(8)}
    return Fernet(key.encode()).encrypt(json.dumps(payload).encode()).decode()


def read_state(key: str, token: str, now: float | None = None) -> dict:
    try:
        data = json.loads(Fernet(key.encode()).decrypt(token.encode()))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise OAuthStateError("Invalid sign-in state") from exc
    if data["e"] < (now or time.time()):
        raise OAuthStateError("The sign-in link expired. Start again.")
    return {"owner_id": data["o"], "verifier": data["v"]}


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "include_granted_scopes": "true",
    })


# ---------- quota ----------
def quota_day(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(PACIFIC).date()


def upload_cost(with_thumbnail: bool, insert_cost: int = QUOTA_COST["videos.insert"]) -> int:
    return insert_cost + (QUOTA_COST["thumbnails.set"] if with_thumbnail else 0)


def can_afford(used_today: int, cost: int, limit: int = DEFAULT_DAILY_QUOTA) -> bool:
    return used_today + cost <= limit


def uploads_per_day(limit: int = DEFAULT_DAILY_QUOTA, with_thumbnail: bool = True,
                    insert_cost: int = QUOTA_COST["videos.insert"]) -> int:
    return limit // upload_cost(with_thumbnail, insert_cost)


# ---------- resumable upload ----------
def plan_chunks(total: int, chunk: int = CHUNK) -> list[tuple[int, int]]:
    if total <= 0:
        raise ValueError("Empty file")
    return [(s, min(s + chunk, total) - 1) for s in range(0, total, chunk)]


def content_range(start: int, end: int, total: int) -> str:
    return f"bytes {start}-{end}/{total}"


def next_offset_from_range(range_header: str | None) -> int:
    """After a 308 response: 'bytes=0-524287' means 524288 bytes are stored. No header means nothing is."""
    if not range_header:
        return 0
    try:
        return int(range_header.split("-")[-1]) + 1
    except ValueError as exc:
        raise ValueError(f"Unexpected Range header: {range_header}") from exc


# ---------- request body ----------
def validate_publish_at(publish_at: datetime | None, now: datetime | None = None) -> None:
    if publish_at is None:
        return
    now = now or datetime.now(timezone.utc)
    if publish_at.tzinfo is None:
        raise ValueError("publish_at needs a timezone")
    if publish_at < now + timedelta(minutes=5):
        raise ValueError("Scheduled time must be at least 5 minutes in the future")


def build_video_resource(meta: dict, visibility: str, publish_at: datetime | None, made_for_kids: bool,
                         contains_synthetic_media: bool, chapters_text: str = "", language: str = "en") -> dict:
    if visibility not in VISIBILITIES:
        raise ValueError(f"Visibility must be one of {sorted(VISIBILITIES)}")
    title, desc = (meta.get("title") or "").strip(), (meta.get("description") or "").strip()
    if not title:
        raise ValueError("A title is required")
    if any(ch in title + desc for ch in "<>"):
        raise ValueError("YouTube does not allow < or > in titles or descriptions")
    if chapters_text and chapters_text.splitlines()[0] not in desc:
        desc = f"{desc}\n\n{chapters_text}".strip()
    validate_publish_at(publish_at)
    status = {"privacyStatus": "private" if publish_at else visibility, "selfDeclaredMadeForKids": bool(made_for_kids),
              "containsSyntheticMedia": bool(contains_synthetic_media), "embeddable": True}
    if publish_at:  # YouTube publishes it at that time; the video must be private until then
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags = [t for t in meta.get("tags", []) if isinstance(t, str) and t.strip()]
    hashtags = " ".join(h if h.startswith("#") else f"#{h}" for h in meta.get("hashtags", [])[:15])
    return {"snippet": {"title": title[:100], "description": (desc + (f"\n\n{hashtags}" if hashtags else ""))[:5000],
                        "tags": tags, "categoryId": "27", "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": status}


# ---------- publishing policy ----------
def evaluate_policy(*, render: dict, metadata: dict, accuracy_warnings: list[str], defaults: dict,
                    uploads_today: int, existing_titles: set[str], uses_tts: bool, automatic: bool) -> list[dict]:
    """Return policy problems. Hard problems always block; the extra automatic-mode rules are stricter because
    no human reviews the video first."""
    problems: list[dict] = []

    def add(code, message):
        problems.append({"code": code, "message": message})

    if render.get("status") != "ready":
        add("render_not_ready", "The render is not ready")
    quality = {c["name"]: c["status"] for c in render.get("quality", [])}
    if "fail" in quality.values():
        add("quality_failed", "A quality check failed")
    title, desc = (metadata.get("title") or "").strip(), (metadata.get("description") or "").strip()
    if not title:
        add("missing_title", "Add a title")
    if not desc:
        add("missing_description", "Add a description")
    if title and title.lower() in existing_titles:
        add("duplicate_title", "A video with this title was already uploaded (repetitive-content protection)")
    if automatic:
        if quality.get("real_footage") != "pass":
            add("not_all_real_footage", "Automatic publishing requires real footage in every scene")
        if quality.get("narration") != "pass":
            add("missing_narration", "Automatic publishing requires narration audio in every scene")
        if accuracy_warnings:
            add("metadata_accuracy", "The metadata mentions things the script does not: review the warnings")
        for key in ("made_for_kids", "contains_synthetic_media"):
            if not isinstance(defaults.get(key), bool):
                add(f"{key}_unset", f"Set '{key}' in your publishing defaults before automatic publishing")
        if uses_tts and defaults.get("contains_synthetic_media") is not True:
            add("synthetic_disclosure", "Narration is AI-generated, so synthetic-content disclosure must be on")
        if defaults.get("visibility") not in VISIBILITIES:
            add("visibility_unset", "Choose a default visibility for automatic uploads")
        limit = int(defaults.get("daily_limit", 0) or 0)
        if limit <= 0:
            add("daily_limit_unset", "Set a daily upload limit for automatic publishing")
        elif uploads_today >= limit:
            add("daily_limit_reached", f"The daily limit of {limit} uploads is reached")
    return problems


def next_publish_slot(hours_utc: list[int], taken: list[datetime], now: datetime, daily_limit: int,
                      min_lead_minutes: int = 10, horizon_days: int = 14) -> datetime | None:
    """Pick the next configured UTC hour that is in the future and on a day that still has room."""
    if not hours_utc:
        return None
    earliest = now + timedelta(minutes=min_lead_minutes)
    for day in range(horizon_days):
        d = (now + timedelta(days=day)).date()
        used = sum(1 for t in taken if t.astimezone(timezone.utc).date() == d)
        if daily_limit and used >= daily_limit:
            continue
        for h in sorted(set(hours_utc)):
            slot = datetime(d.year, d.month, d.day, h, 0, tzinfo=timezone.utc)
            if slot >= earliest and not any(abs((slot - t).total_seconds()) < 60 for t in taken):
                return slot
    return None
