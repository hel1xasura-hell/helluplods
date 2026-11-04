from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from app.integrations import youtube_logic as yl

KEY = Fernet.generate_key().decode()
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def test_pkce_and_state_roundtrip_hides_verifier():
    verifier, challenge = yl.new_pkce()
    state = yl.make_state(KEY, "owner-1", verifier)
    assert verifier not in state and yl.read_state(KEY, state) == {"owner_id": "owner-1", "verifier": verifier}
    assert len(challenge) == 43


def test_state_rejects_tampering_wrong_key_and_expiry():
    verifier, _ = yl.new_pkce()
    state = yl.make_state(KEY, "o", verifier)
    for bad in (state[:-3] + "AAA", "garbage"):
        with pytest.raises(yl.OAuthStateError):
            yl.read_state(KEY, bad)
    with pytest.raises(yl.OAuthStateError):
        yl.read_state(Fernet.generate_key().decode(), state)
    with pytest.raises(yl.OAuthStateError):
        yl.read_state(KEY, yl.make_state(KEY, "o", verifier, ttl=-5))


def test_auth_url_uses_least_privilege_and_pkce():
    url = yl.build_auth_url("cid", "https://x/cb", "st", "chal")
    assert "youtube.upload" in url and "youtube.readonly" in url
    assert "auth%2Fyoutube+" not in url and "auth%2Fyoutube&" not in url  # not the full channel-management scope
    assert "code_challenge_method=S256" in url and "access_type=offline" in url


def test_quota_math_and_pacific_day():
    assert yl.upload_cost(True) == 1650 and yl.uploads_per_day(10_000) == 6
    assert yl.uploads_per_day(82_500) == 50
    assert yl.can_afford(8350, 1650) and not yl.can_afford(8351, 1650)
    assert str(yl.quota_day(datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc))) == "2026-11-01"


def test_chunk_planning_and_range_parsing():
    chunks = yl.plan_chunks(5_000_000)
    assert chunks[0] == (0, yl.CHUNK - 1) and chunks[-1][1] == 4_999_999
    assert all((e - s + 1) % (256 * 1024) == 0 for s, e in chunks[:-1])
    assert yl.plan_chunks(10) == [(0, 9)]
    with pytest.raises(ValueError):
        yl.plan_chunks(0)
    assert yl.next_offset_from_range("bytes=0-524287") == 524288 and yl.next_offset_from_range(None) == 0
    assert yl.content_range(0, 9, 10) == "bytes 0-9/10"


def test_video_resource_rules():
    meta = {"title": "Acme tutorial", "description": "Learn Acme", "tags": ["notes", " "], "hashtags": ["acme"]}
    scheduled = yl.build_video_resource(meta, "public", NOW + timedelta(days=1), False, True, "0:00 Intro")
    assert scheduled["status"]["privacyStatus"] == "private" and scheduled["status"]["publishAt"].endswith("Z")
    assert scheduled["status"]["selfDeclaredMadeForKids"] is False and scheduled["status"]["containsSyntheticMedia"] is True
    assert "0:00 Intro" in scheduled["snippet"]["description"] and "#acme" in scheduled["snippet"]["description"]
    assert scheduled["snippet"]["tags"] == ["notes"]
    assert yl.build_video_resource(meta, "unlisted", None, False, False)["status"]["privacyStatus"] == "unlisted"
    for args in (("secret", None), ("private", datetime.now(timezone.utc) + timedelta(minutes=1)), ("private", datetime(2030, 1, 1))):
        with pytest.raises(ValueError):
            yl.build_video_resource(meta, args[0], args[1], False, False)
    with pytest.raises(ValueError):
        yl.build_video_resource({"title": "a<b", "description": "d"}, "private", None, False, False)
    with pytest.raises(ValueError):
        yl.build_video_resource({"title": " ", "description": "d"}, "private", None, False, False)


def _render(footage="pass", narration="pass", status="ready"):
    return {"status": status, "quality": [{"name": "real_footage", "status": footage}, {"name": "narration", "status": narration}]}


GOOD_DEFAULTS = {"made_for_kids": False, "contains_synthetic_media": True, "visibility": "private", "daily_limit": 3}


def _policy(**kw):
    base = dict(render=_render(), metadata={"title": "New", "description": "d"}, accuracy_warnings=[], defaults=GOOD_DEFAULTS,
                uploads_today=0, existing_titles=set(), uses_tts=True, automatic=True)
    base.update(kw)
    return {p["code"] for p in yl.evaluate_policy(**base)}


def test_policy_clean_automatic_passes():
    assert _policy() == set()


def test_policy_blocks_each_unsafe_case():
    assert "render_not_ready" in _policy(render=_render(status="failed"))
    assert "quality_failed" in _policy(render={"status": "ready", "quality": [{"name": "audio_stream", "status": "fail"}]})
    assert "duplicate_title" in _policy(existing_titles={"new"})
    assert "missing_title" in _policy(metadata={"title": "", "description": "d"})
    assert "not_all_real_footage" in _policy(render=_render(footage="warn"))
    assert "missing_narration" in _policy(render=_render(narration="warn"))
    assert "metadata_accuracy" in _policy(accuracy_warnings=["x"])
    assert "synthetic_disclosure" in _policy(defaults={**GOOD_DEFAULTS, "contains_synthetic_media": False})
    assert "made_for_kids_unset" in _policy(defaults={k: v for k, v in GOOD_DEFAULTS.items() if k != "made_for_kids"})
    assert "daily_limit_reached" in _policy(uploads_today=3)
    assert "daily_limit_unset" in _policy(defaults={**GOOD_DEFAULTS, "daily_limit": 0})


def test_approval_mode_is_less_strict_because_a_human_reviews():
    assert _policy(automatic=False, render=_render(footage="warn", narration="warn"), accuracy_warnings=["x"], defaults={}) == set()
    assert "duplicate_title" in _policy(automatic=False, existing_titles={"new"})


def test_publish_slots_respect_hours_limits_and_lead_time():
    s1 = yl.next_publish_slot([14, 18], [], NOW, 2)
    assert s1 == datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)          # 14:00 already passed
    s2 = yl.next_publish_slot([14, 18], [s1], NOW, 2)
    assert s2 == datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
    assert yl.next_publish_slot([14, 18], [s1, s2], NOW, 2) == datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
    assert yl.next_publish_slot([], [], NOW, 2) is None
    full = [datetime(2026, 11, 2 + d, 14, 0, tzinfo=timezone.utc) for d in range(14)]
    assert yl.next_publish_slot([14], full, NOW, 1) is None
