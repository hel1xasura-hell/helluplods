import asyncio

import pytest

from app.agents.base import run_agent
from app.agents.registry import AGENTS, IMPLEMENTATIONS
from app.services.ssrf import UnsafeURL, validate_public_url
from app.services.storage import LocalStorage


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/", "http://localhost/",
    "http://[::1]/", "file:///etc/passwd", "ftp://example.com", "http://u:p@example.com/",
    "http://[::ffff:127.0.0.1]/",
])
def test_ssrf_blocks(url):
    with pytest.raises(UnsafeURL):
        validate_public_url(url, resolve=False)


def test_ssrf_allows_public_ip():
    assert validate_public_url("https://8.8.8.8/", resolve=False)


def test_storage_blocks_traversal(tmp_path):
    store = LocalStorage(str(tmp_path))
    for bad in ["../x", "/etc/passwd", "a/../../x", ""]:
        with pytest.raises(ValueError):
            store.put(bad, b"x")
    meta = store.put("shots/a.png", b"data")
    assert store.get("shots/a.png") == b"data" and meta["size_bytes"] == 4


def test_all_sixteen_agents_defined_with_limits():
    assert len(AGENTS) == 16
    for spec in AGENTS.values():
        assert spec.timeout_seconds > 0 and spec.max_retries >= 0


def test_unbuilt_agent_reports_not_implemented():
    spec = AGENTS["research"]
    result = asyncio.run(run_agent(spec, IMPLEMENTATIONS["research"], {"project_id": "p", "target": "x"}))
    assert result.status == "not_implemented"


def test_agent_cannot_use_unlisted_tool_or_secret():
    from app.agents.base import PermissionDenied, ToolBox
    box = ToolBox(AGENTS["screenshot"], {"shell": print}, {"ANTHROPIC_API_KEY": "k"})
    with pytest.raises(PermissionDenied):
        box.tool("shell")
    with pytest.raises(PermissionDenied):
        box.secret("ANTHROPIC_API_KEY")


def test_claim_check_statuses():
    from app.services.claims import check_claim

    pages = {"a": "Notes app for teams with offline mode", "b": "Pricing: notes app for teams from $12", "c": "Blog"}
    assert check_claim("Notes app for teams", pages)["status"] == "corroborated_on_multiple_pages"
    assert check_claim("Notes app for teams with offline mode", {"a": pages["a"]})["status"] == "found_on_one_page"
    assert check_claim("Unlimited quantum storage", pages)["status"] == "not_found_in_pages"
    assert check_claim("the a of", pages)["status"] == "not_checkable"
    assert check_claim("Notes app for teams", pages)["proves_truth"] is False


def test_executor_rules():
    from app.services.executor import NoLocalDevice, choose_executor

    assert choose_executor("cloud", "record", True) == "cloud"
    assert choose_executor("local", "record", True) == "local"
    assert choose_executor("both", "record", True) == "local"
    assert choose_executor("both", "record", False) == "cloud"
    assert choose_executor("both", "research", True) == "cloud"
    with pytest.raises(NoLocalDevice):
        choose_executor("local", "record", False)
    with pytest.raises(ValueError):
        choose_executor("sideways", "record", True)


def test_video_magic_bytes():
    from app.browser.recorder import looks_like_video

    assert looks_like_video(b"\x1a\x45\xdf\xa3rest") and looks_like_video(b"\x00\x00\x00\x18ftypmp42")
    assert not looks_like_video(b"<html>") and not looks_like_video(b"")
