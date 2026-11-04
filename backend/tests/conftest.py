import os

os.environ.setdefault("OWNER_EMAIL", "owner@example.com")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")
from cryptography.fernet import Fernet as _F  # noqa: E402

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", _F.generate_key().decode())
os.environ.setdefault("YOUTUBE_CLIENT_ID", "test-client")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/youtube/oauth/callback")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.auth import deps  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

TOKENS = {
    "owner-token": {"uid": "uid-owner", "email": "owner@example.com", "email_verified": True},
    "stranger-token": {"uid": "uid-x", "email": "stranger@example.com", "email_verified": True},
    "unverified-token": {"uid": "uid-owner", "email": "owner@example.com", "email_verified": False},
    "impostor-token": {"uid": "uid-other", "email": "owner@example.com", "email_verified": True},
}


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def db_session(session_factory):
    session = session_factory()
    yield session
    session.close()


def make_capture(**overrides):
    from app.browser.safe_browser import PageCapture

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    data = dict(
        requested_url="https://acme.example/", final_url="https://acme.example/", status=200, title="Acme Notes",
        description="Notes app for teams", headings=["Shared folders", "Offline mode"],
        nav_links=[{"label": "Pricing", "href": "https://acme.example/pricing"},
                   {"label": "Docs", "href": "https://acme.example/docs"}],
        text_excerpt="Acme Notes helps teams.", screenshot_png=png, robots_checked=True,
    )
    data.update(overrides)
    return PageCapture(**data)


@pytest.fixture()
def capture_holder():
    return {"fn": None}


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048


@pytest.fixture()
def stage4_holder():
    """Fakes for AI, TTS and the renderer so API tests never need external services."""
    from app.browser.recorder import looks_like_video  # noqa: F401
    from app.media.ffmpeg_render import RenderResult

    def fake_renderer(scenes, st, out, progress=None, should_stop=None, workdir=None):
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        fake_renderer.last_scenes = scenes
        if progress:
            progress(1.0)
        return RenderResult(out, 12.5, "1\n00:00:00,000 --> 00:00:02,000\nhi\n\n", "WEBVTT\n\n", [], [], [])

    fake_renderer.last_scenes = []
    return {"hooks": (fake_renderer, lambda r, st, sc: [{"name": "video_stream", "status": "pass", "detail": "ok"}]),
            "tts": None, "ai": None, "renderer": fake_renderer}


class FakeYT:
    """Stands in for the YouTube API. Records calls so tests can assert on resumability and dedupe."""

    def __init__(self):
        self.calls, self.chunk_failures, self.fatal_chunk_error = [], 0, None
        self.refresh_error = None
        self.thumbnail_error = None
        self.refresh_token = "refresh-secret-123"
        self.stored = 0

    def auth_url(self, state, challenge):
        return f"https://accounts.example/auth?state={state}&code_challenge={challenge}&scope=youtube.upload+youtube.readonly"

    async def exchange_code(self, code, verifier):
        from app.integrations.youtube_client import Tokens
        self.calls.append(("exchange", code, bool(verifier)))
        return Tokens("access-1", self.refresh_token, 3600)

    async def channel_info(self, access):
        return {"id": "UC123", "title": "My Channel"}

    async def refresh_access_token(self, rt):
        from app.integrations.youtube_client import YouTubeError
        self.calls.append(("refresh",))
        if self.refresh_error:
            raise YouTubeError("invalid_grant: Token revoked", 400, "invalid_grant")
        return "access-2"

    async def revoke(self, token):
        self.calls.append(("revoke",))

    async def start_upload(self, access, resource, size):
        self.calls.append(("start_upload", resource["status"]["privacyStatus"], size))
        self.resource = resource
        return "https://upload.example/session/abc"

    async def upload_chunk(self, uri, data, start, total):
        from app.integrations.youtube_client import YouTubeError
        self.calls.append(("chunk", start, len(data)))
        if self.fatal_chunk_error:
            raise YouTubeError("bad request", 400, "invalid")
        if self.chunk_failures > 0:
            self.chunk_failures -= 1
            raise YouTubeError("backend error", 503, "backendError", retriable=True)
        self.stored = start + len(data)
        return ("complete", "VID123") if self.stored >= total else ("incomplete", self.stored)

    async def query_progress(self, uri, total):
        self.calls.append(("query", total))
        return ("incomplete", self.stored)

    async def video_stats(self, access, ids):
        self.calls.append(("stats", tuple(ids)))
        return {i: {"viewCount": 100, "likeCount": 7, "commentCount": 2} for i in ids}

    async def set_thumbnail(self, access, vid, png):
        self.calls.append(("thumbnail", vid))
        if self.thumbnail_error:
            raise RuntimeError("thumbnail denied")


@pytest.fixture()
def yt():
    return FakeYT()


@pytest.fixture()
def recorder_holder(tmp_path):
    from app.browser.recorder import RecordingResult

    async def fake(url, out_dir, validator, duration_seconds=10.0, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "rec.webm"
        path.write_bytes(WEBM)
        return RecordingResult(path, 8.5, 1280, 720, url, [{"t": 0.1, "type": "load", "url": url}])

    return {"fn": fake}


@pytest.fixture()
def client(db_session, session_factory, capture_holder, recorder_holder, stage4_holder, yt, tmp_path, monkeypatch):
    def fake_verify(token):
        if token not in TOKENS:
            raise ValueError("bad token")
        return TOKENS[token]

    monkeypatch.setattr(deps, "verify_token", fake_verify)
    app = create_app()
    from app.api.routes import research as research_routes
    from app.services.storage import LocalStorage, get_storage

    store = LocalStorage(str(tmp_path / "store"))

    async def default_capture(url, on_page=None):
        return [make_capture(requested_url=url, final_url=url)]

    capture_holder["fn"] = default_capture
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_storage] = lambda: store
    from app.api.routes import recordings as rec_routes
    from app.api.routes import renders as render_routes
    from app.api.routes import youtube as yt_routes

    app.dependency_overrides[yt_routes.get_youtube_client] = lambda: yt
    from app.api.routes import ops as ops_routes

    class FakeRedis:
        def ping(self): return True
        def llen(self, q): return 0

    app.dependency_overrides[ops_routes.get_redis] = lambda: FakeRedis()
    app.dependency_overrides[ops_routes.get_session_factory] = lambda: session_factory
    from app.api.routes import scripts as script_routes
    from app.media import tts as tts_mod
    from app.core.config import get_settings

    app.dependency_overrides[render_routes.get_render_hooks] = lambda: stage4_holder["hooks"]
    app.dependency_overrides[script_routes.get_tts_providers] = lambda: stage4_holder["tts"] or tts_mod.providers(get_settings())
    app.dependency_overrides[script_routes.get_ai] = lambda: stage4_holder["ai"] or script_routes.get_ai()
    from app.api.routes import runs as runs_routes

    app.dependency_overrides[rec_routes.get_recorder] = lambda: recorder_holder["fn"]

    app.dependency_overrides[research_routes.get_session_factory] = lambda: session_factory
    app.dependency_overrides[runs_routes.get_ws_session_factory] = lambda: session_factory
    app.dependency_overrides[research_routes.get_capture_fn] = lambda: capture_holder["fn"]
    return TestClient(app)


def auth(token="owner-token"):
    return {"Authorization": f"Bearer {token}"}
