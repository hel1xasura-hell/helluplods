"""YouTube Data API v3 + Google OAuth over HTTPS (httpx). Official endpoints only."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.integrations import youtube_logic as yl

if TYPE_CHECKING:
    import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"


class YouTubeError(Exception):
    def __init__(self, message: str, status: int = 0, reason: str = "", retriable: bool = False):
        super().__init__(message)
        self.status, self.reason, self.retriable = status, reason, retriable


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


def _raise(resp) -> None:
    if resp.status_code < 400:
        return
    reason, msg = "", resp.text[:300]
    try:
        err = resp.json().get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", msg)
            reason = (err.get("errors") or [{}])[0].get("reason", "")
        else:
            msg = f"{err}: {resp.json().get('error_description', '')}"
    except ValueError:
        pass
    quota = reason in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}
    raise YouTubeError(msg, resp.status_code, reason, retriable=resp.status_code >= 500 or quota)


class YouTubeClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str,
                 transport: "httpx.AsyncBaseTransport | None" = None):
        self.client_id, self.client_secret, self.redirect_uri, self.transport = client_id, client_secret, redirect_uri, transport

    def _http(self, timeout: float = 60):
        import httpx

        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    def auth_url(self, state: str, challenge: str) -> str:
        return yl.build_auth_url(self.client_id, self.redirect_uri, state, challenge)

    async def exchange_code(self, code: str, verifier: str) -> Tokens:
        async with self._http() as c:
            r = await c.post(TOKEN_URL, data={"code": code, "client_id": self.client_id, "client_secret": self.client_secret,
                                              "redirect_uri": self.redirect_uri, "grant_type": "authorization_code",
                                              "code_verifier": verifier})
        _raise(r)
        d = r.json()
        return Tokens(d["access_token"], d.get("refresh_token"), int(d.get("expires_in", 3600)))

    async def refresh_access_token(self, refresh_token: str) -> str:
        async with self._http() as c:
            r = await c.post(TOKEN_URL, data={"refresh_token": refresh_token, "client_id": self.client_id,
                                              "client_secret": self.client_secret, "grant_type": "refresh_token"})
        _raise(r)
        return r.json()["access_token"]

    async def revoke(self, token: str) -> None:
        async with self._http(15) as c:
            await c.post(REVOKE_URL, data={"token": token})

    async def channel_info(self, access_token: str) -> dict:
        async with self._http() as c:
            r = await c.get(f"{API}/channels", params={"part": "snippet", "mine": "true"},
                            headers={"Authorization": f"Bearer {access_token}"})
        _raise(r)
        items = r.json().get("items", [])
        if not items:
            raise YouTubeError("This Google account has no YouTube channel")
        return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}

    async def start_upload(self, access_token: str, resource: dict, size: int) -> str:
        async with self._http() as c:
            r = await c.post(f"{UPLOAD}/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                             headers={"Authorization": f"Bearer {access_token}", "X-Upload-Content-Type": "video/*",
                                      "X-Upload-Content-Length": str(size)}, json=resource)
        _raise(r)
        return r.headers["Location"]

    async def upload_chunk(self, session_uri: str, data: bytes, start: int, total: int) -> tuple[str, int | str]:
        """Returns ('incomplete', next_offset) or ('complete', video_id)."""
        end = start + len(data) - 1
        async with self._http(300) as c:
            r = await c.put(session_uri, content=data, headers={"Content-Range": yl.content_range(start, end, total)})
        if r.status_code == 308:
            return "incomplete", yl.next_offset_from_range(r.headers.get("Range"))
        _raise(r)
        return "complete", r.json()["id"]

    async def query_progress(self, session_uri: str, total: int) -> tuple[str, int | str]:
        """Ask where a broken upload stopped so it can resume instead of restarting."""
        async with self._http(60) as c:
            r = await c.put(session_uri, content=b"", headers={"Content-Range": f"bytes */{total}"})
        if r.status_code == 308:
            return "incomplete", yl.next_offset_from_range(r.headers.get("Range"))
        _raise(r)
        return "complete", r.json()["id"]

    async def set_thumbnail(self, access_token: str, video_id: str, png: bytes) -> None:
        async with self._http(120) as c:
            r = await c.post(f"{UPLOAD}/thumbnails/set", params={"videoId": video_id},
                             headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/png"}, content=png)
        _raise(r)

    async def video_stats(self, access_token: str, video_ids: list[str]) -> dict[str, dict]:
        """Public statistics for up to 50 videos. Costs 1 quota unit per call."""
        if not video_ids:
            return {}
        async with self._http() as c:
            r = await c.get(f"{API}/videos", params={"part": "statistics", "id": ",".join(video_ids[:50])},
                            headers={"Authorization": f"Bearer {access_token}"})
        _raise(r)
        out = {}
        for item in r.json().get("items", []):
            st = item.get("statistics", {})
            out[item["id"]] = {k: int(st[k]) for k in ("viewCount", "likeCount", "commentCount") if k in st}
        return out
