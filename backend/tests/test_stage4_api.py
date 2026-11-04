import shutil
import subprocess

import pytest

from app.models import Owner, Project, Recording, Script
from tests.conftest import auth

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096


def mkproject(client, name="p"):
    return client.post("/api/projects", json={"name": name}, headers=auth()).json()["id"]


def mkscript(client, pid, title="Acme tutorial"):
    r = client.post(f"/api/projects/{pid}/scripts", json={"title": title}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mkscene(client, sid, narration="Welcome to Acme.", **kw):
    r = client.post(f"/api/scripts/{sid}/scenes", json={"narration": narration, **kw}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()


def wav(tmp_path, seconds=2):
    p = tmp_path / "n.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}", str(p)], check=True)
    return p.read_bytes()


# ---- scripts & scenes ----
def test_script_scene_crud_reorder_and_renumber(client):
    sid = mkscript(client, mkproject(client))
    a, b, c = (mkscene(client, sid, t)["id"] for t in ("One.", "Two.", "Three."))
    assert client.post(f"/api/scripts/{sid}/scenes/reorder", json={"order": [c, a, b]}, headers=auth()).status_code == 200
    got = client.get(f"/api/scripts/{sid}", headers=auth()).json()["scenes"]
    assert [s["narration"] for s in got] == ["Three.", "One.", "Two."]
    assert client.post(f"/api/scripts/{sid}/scenes/reorder", json={"order": [a]}, headers=auth()).status_code == 422
    assert client.delete(f"/api/scenes/{a}", headers=auth()).status_code == 204
    assert [s["position"] for s in client.get(f"/api/scripts/{sid}", headers=auth()).json()["scenes"]] == [1, 2]


def test_scene_option_validation(client):
    sid = mkscript(client, mkproject(client))
    scene = mkscene(client, sid)
    for bad in ({"zoom": {"factor": 9}}, {"trim_start": -1}, {"evil": 1}, {"min_seconds": 999}):
        assert client.patch(f"/api/scenes/{scene['id']}", json={"options": bad}, headers=auth()).status_code == 422
    ok = client.patch(f"/api/scenes/{scene['id']}", json={"options": {"zoom": {"factor": 1.5, "cx": .3, "cy": .3}}}, headers=auth())
    assert ok.status_code == 200


def test_clearing_scene_options_with_null_is_allowed(client):
    sid = mkscript(client, mkproject(client))
    scene = mkscene(client, sid, options={"trim_start": 2})
    r = client.patch(f"/api/scenes/{scene['id']}", json={"options": None}, headers=auth())
    assert r.status_code == 200 and r.json()["options"] == {}


def test_scene_cannot_use_recording_from_another_project(client, db_session):
    client.get("/api/me", headers=auth())
    owner = db_session.query(Owner).one()
    mine = mkproject(client)
    other = Project(owner_id=owner.id, name="other")
    db_session.add(other); db_session.flush()
    rec = Recording(project_id=other.id, is_real_capture=True)
    db_session.add(rec); db_session.commit()
    sid = mkscript(client, mine)
    r = client.post(f"/api/scripts/{sid}/scenes", json={"narration": "x", "recording_id": str(rec.id)}, headers=auth())
    assert r.status_code == 422


def test_scripts_are_private_to_owner(client, db_session):
    client.get("/api/me", headers=auth())
    other = Owner(firebase_uid="oq", email="oq@example.com")
    db_session.add(other); db_session.flush()
    proj = Project(owner_id=other.id, name="theirs")
    db_session.add(proj); db_session.flush()
    s = Script(project_id=proj.id, title="secret")
    db_session.add(s); db_session.commit()
    assert client.get(f"/api/scripts/{s.id}", headers=auth()).status_code == 404
    assert client.post(f"/api/scripts/{s.id}/render", json={}, headers=auth()).status_code == 404
    assert client.post(f"/api/scripts/{s.id}/scenes", json={"narration": "x"}, headers=auth()).status_code == 404
    assert client.get(f"/api/scripts/{s.id}").status_code == 401


def test_script_skeleton_from_research_report_has_no_invented_narration(client):
    pid = mkproject(client)
    tid = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": "https://acme.example/"}, headers=auth()).json()["id"]
    client.post(f"/api/targets/{tid}/research", headers=auth())
    r = client.post(f"/api/projects/{pid}/scripts", json={"title": "t", "from_target_id": tid}, headers=auth())
    scenes = r.json()["scenes"]
    assert scenes and all(s["narration"] == "" and s["title"] for s in scenes)


def test_ai_generation_needs_key_then_adds_scenes(client, stage4_holder):
    pid = mkproject(client)
    tid = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": "https://acme.example/"}, headers=auth()).json()["id"]
    client.post(f"/api/targets/{tid}/research", headers=auth())
    sid = mkscript(client, pid)
    r = client.post(f"/api/scripts/{sid}/generate-ai?target_id={tid}", headers=auth())
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]

    class Fake:
        name = "fake"
        async def complete(self, system, prompt, max_tokens=1000):
            assert "untrusted_content" in prompt
            return '[{"title": "Shared folders", "narration": "Open Shared folders."}, {"title": "x", "narration": ""}]'

    stage4_holder["ai"] = Fake()
    r = client.post(f"/api/scripts/{sid}/generate-ai?target_id={tid}", headers=auth())
    assert r.status_code == 200 and [s["narration"] for s in r.json()["scenes"]] == ["Open Shared folders."]


# ---- subtitles / metadata ----
def test_subtitle_export_and_edit(client):
    sid = mkscript(client, mkproject(client))
    scene = mkscene(client, sid, "Open the app and tap Shared folders to create a new folder.")
    srt = client.get(f"/api/scripts/{sid}/subtitles.srt", headers=auth())
    assert srt.status_code == 200 and "Shared folders" in srt.text and "-->" in srt.text
    client.patch(f"/api/scenes/{scene['id']}", json={"narration": "Open the app.", "subtitle": "Open the app (edited)"}, headers=auth())
    assert "(edited)" in client.get(f"/api/scripts/{sid}/subtitles.vtt", headers=auth()).text
    assert client.get(f"/api/scripts/{sid}/subtitles.txt", headers=auth()).status_code == 404


def test_metadata_validation_chapters_and_accuracy(client):
    sid = mkscript(client, mkproject(client))
    for t in ("Intro to the app.", "Sharing folders.", "Inviting people."):
        mkscene(client, sid, t + " " + "word " * 40)
    assert client.put(f"/api/scripts/{sid}/metadata", json={"title": "x" * 150}, headers=auth()).status_code == 422
    ok = client.put(f"/api/scripts/{sid}/metadata", json={"title": "Acme tutorial", "description": "Works with Dropbox", "tags": ["notes"]}, headers=auth())
    assert ok.status_code == 200
    got = client.get(f"/api/scripts/{sid}/metadata", headers=auth()).json()
    assert got["chapters"][0]["start"] == 0 and got["chapters_text"].startswith("0:00")
    assert any("Dropbox" in w for w in got["accuracy_warnings"])
    one = mkscript(client, mkproject(client, "p2"))
    mkscene(client, one)
    assert any("at least 3" in w for w in client.get(f"/api/scripts/{one}/metadata", headers=auth()).json()["chapter_warnings"])


# ---- narration ----
def test_audio_upload_rejects_non_audio(client):
    sc = mkscene(client, mkscript(client, mkproject(client)))
    r = client.put(f"/api/scenes/{sc['id']}/audio", content=b"<html>nope</html>", headers=auth())
    assert r.status_code == 422


@needs_ffmpeg
def test_uploaded_audio_is_tied_to_the_narration_text(client, tmp_path):
    sid = mkscript(client, mkproject(client))
    sc = mkscene(client, sid, "Welcome to Acme.")
    r = client.put(f"/api/scenes/{sc['id']}/audio", content=wav(tmp_path), headers=auth())
    assert r.status_code == 200 and r.json()["audio"]["up_to_date"] is True and r.json()["audio"]["duration_seconds"] == pytest.approx(2, abs=0.2)
    edited = client.patch(f"/api/scenes/{sc['id']}", json={"narration": "A different sentence now."}, headers=auth()).json()
    assert edited["audio"]["up_to_date"] is False
    assert client.get(f"/api/scenes/{sc['id']}/audio", headers=auth()).status_code == 200


def test_voice_unconfigured_is_honest_503(client):
    sid = mkscript(client, mkproject(client))
    r = client.post(f"/api/scripts/{sid}/voice", json={"provider": "piper"}, headers=auth())
    assert r.status_code == 503 and "upload your own narration" in r.json()["detail"]
    assert client.post(f"/api/scripts/{sid}/voice", json={"provider": "robot"}, headers=auth()).status_code == 422
    assert {v["name"] for v in client.get("/api/voices", headers=auth()).json()} == {"piper", "elevenlabs"}


@needs_ffmpeg
def test_voice_generation_with_configured_provider(client, stage4_holder, tmp_path):
    audio = wav(tmp_path)

    class FakeTTS:
        name, extension = "piper", ".wav"
        def missing(self): return []
        async def synthesize(self, text, out): out.write_bytes(audio); return out

    stage4_holder["tts"] = {"piper": FakeTTS(), "elevenlabs": FakeTTS()}
    sid = mkscript(client, mkproject(client))
    mkscene(client, sid, "Narrate me."); mkscene(client, sid, "")
    assert client.post(f"/api/scripts/{sid}/voice", json={"provider": "piper"}, headers=auth()).status_code == 202
    scenes = client.get(f"/api/scripts/{sid}", headers=auth()).json()["scenes"]
    assert scenes[0]["audio"]["source"] == "tts" and scenes[0]["audio"]["up_to_date"] and scenes[1]["audio"] is None


# ---- rendering ----
def test_render_lifecycle_with_quality_checks_and_download(client):
    sid = mkscript(client, mkproject(client))
    mkscene(client, sid)
    r = client.post(f"/api/scripts/{sid}/render", json={"aspect_ratio": "9:16", "fps": 24}, headers=auth())
    assert r.status_code == 202
    job = client.get(f"/api/renders/{r.json()['id']}", headers=auth()).json()
    assert job["status"] == "ready" and job["width"] == 1080 and job["height"] == 1920 and job["has_file"]
    assert job["quality"][0]["name"] == "video_stream" and job["duration_seconds"] == 12.5
    f = client.get(f"/api/renders/{job['id']}/file", headers=auth())
    assert f.status_code == 200 and f.headers["content-type"] == "video/mp4" and f.content == MP4
    assert client.get(f"/api/renders/{job['id']}/file", headers={**auth(), "Range": "bytes=0-3"}).status_code == 206
    assert "-->" in client.get(f"/api/renders/{job['id']}/subtitles.srt", headers=auth()).text
    assert client.get("/api/notifications", headers=auth()).json()["items"][0]["title"] == "Video ready for review"
    assert client.post(f"/api/renders/{job['id']}/cancel", headers=auth()).status_code == 409


def test_render_validation_errors(client):
    sid = mkscript(client, mkproject(client))
    assert client.post(f"/api/scripts/{sid}/render", json={}, headers=auth()).status_code == 422  # no scenes
    mkscene(client, sid)
    for bad in ({"fps": 5}, {"aspect_ratio": "4:3"}, {"accent": "red"}, {"width": 1001, "height": 1000}):
        assert client.post(f"/api/scripts/{sid}/render", json=bad, headers=auth()).status_code == 422, bad


def test_failed_quality_check_marks_render_failed(client, stage4_holder):
    fake = stage4_holder["hooks"][0]
    stage4_holder["hooks"] = (fake, lambda r, st, sc: [{"name": "audio_stream", "status": "fail", "detail": "No audio stream"}])
    sid = mkscript(client, mkproject(client))
    mkscene(client, sid)
    job = client.post(f"/api/scripts/{sid}/render", json={}, headers=auth()).json()
    got = client.get(f"/api/renders/{job['id']}", headers=auth()).json()
    assert got["status"] == "failed" and "No audio stream" in got["error"]


def test_renderer_crash_is_reported(client, stage4_holder):
    def boom(*a, **k):
        raise RuntimeError("ffmpeg exploded")
    stage4_holder["hooks"] = (boom, None)
    sid = mkscript(client, mkproject(client))
    mkscene(client, sid)
    job = client.post(f"/api/scripts/{sid}/render", json={}, headers=auth()).json()
    got = client.get(f"/api/renders/{job['id']}", headers=auth()).json()
    assert got["status"] == "failed" and "ffmpeg exploded" in got["error"]


@needs_ffmpeg
def test_stale_audio_is_not_rendered_and_user_is_told(client, stage4_holder, tmp_path):
    sid = mkscript(client, mkproject(client))
    sc = mkscene(client, sid, "Original narration.")
    client.put(f"/api/scenes/{sc['id']}/audio", content=wav(tmp_path), headers=auth())
    client.patch(f"/api/scenes/{sc['id']}", json={"narration": "Changed narration."}, headers=auth())
    job = client.post(f"/api/scripts/{sid}/render", json={}, headers=auth()).json()
    assert stage4_holder["renderer"].last_scenes[0].audio_path is None
    assert any("narration changed" in w for w in client.get(f"/api/renders/{job['id']}", headers=auth()).json()["warnings"])


def test_renders_are_private(client, db_session):
    import uuid
    assert client.get("/api/renders").status_code == 401
    assert client.get(f"/api/renders/{uuid.uuid4()}", headers=auth()).status_code == 404


# ---- thumbnails ----
def test_thumbnail_create_select_download_delete(client):
    pid = mkproject(client)
    ids = [client.post(f"/api/projects/{pid}/thumbnails", json={"text": f"Share folders {i}", "template": t, "brand": "TUTORIAL"}, headers=auth()).json()["id"]
           for i, t in enumerate(("bold_left", "centered"))]
    assert client.post(f"/api/thumbnails/{ids[0]}/select", headers=auth()).json()["selected"] is True
    client.post(f"/api/thumbnails/{ids[1]}/select", headers=auth())
    listed = {t["id"]: t["selected"] for t in client.get(f"/api/projects/{pid}/thumbnails", headers=auth()).json()}
    assert listed == {ids[0]: False, ids[1]: True}  # only one selected
    f = client.get(f"/api/thumbnails/{ids[0]}/file?download=true", headers=auth())
    assert f.content[:4] == b"\x89PNG" and "attachment" in f.headers["content-disposition"]
    assert client.delete(f"/api/thumbnails/{ids[0]}", headers=auth()).status_code == 204
    assert client.get(f"/api/thumbnails/{ids[0]}/file", headers=auth()).status_code == 404


def test_thumbnail_validation_and_foreign_screenshot(client):
    import uuid
    pid = mkproject(client)
    assert client.post(f"/api/projects/{pid}/thumbnails", json={"text": "x", "template": "nope"}, headers=auth()).status_code == 422
    assert client.post(f"/api/projects/{pid}/thumbnails", json={"text": ""}, headers=auth()).status_code == 422
    assert client.post(f"/api/projects/{pid}/thumbnails", json={"text": "x", "screenshot_id": str(uuid.uuid4())}, headers=auth()).status_code == 404
    assert client.post(f"/api/projects/{pid}/thumbnails", json={"text": "x", "accent": "red"}, headers=auth()).status_code == 422
