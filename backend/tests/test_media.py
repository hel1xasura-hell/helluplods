"""Media pipeline tests. The render tests run real FFmpeg and are skipped when FFmpeg/Pillow are missing."""
import shutil
import subprocess

import pytest

from app.media.ffmpeg_render import RenderCancelled, RenderError, RenderSettings, probe, quality_check, render
from app.media.subtitles import cues_for_scene, parse_srt, to_ass, to_srt, to_vtt, wrap_text
from app.media.thumbnail import TEMPLATES, render_thumbnail
from app.media.timeline import SceneInput, chapters, format_chapters, plan, total_seconds
from app.services import metadata as meta

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def test_wrap_and_cues_cover_the_whole_scene():
    cues = cues_for_scene("Open the app and tap Shared folders to create a new folder for your team, then invite members.", 2.0, 8.0)
    assert cues[0].start == 2.0 and cues[-1].end == 8.0
    assert all(b.start == pytest.approx(a.end, abs=0.01) for a, b in zip(cues, cues[1:]))
    assert all(len(line) <= 42 for c in cues for line in c.text.split("\n"))
    assert wrap_text("") == []


def test_srt_vtt_roundtrip_and_malformed_input_ignored():
    cues = cues_for_scene("Hello there, this is a subtitle for testing the round trip.", 0, 5)
    back = parse_srt(to_srt(cues))
    assert len(back) == len(cues) and back[0].text == cues[0].text
    assert to_vtt(cues).startswith("WEBVTT")
    assert parse_srt("nonsense\n\n1\n00:00:01,000 --> 00:00:00,500\nend before start") == []


def test_ass_uses_output_resolution_and_escapes_braces():
    cues = cues_for_scene("Press {Ctrl} and C", 0, 2)
    ass = to_ass(cues, 1080, 1920)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass and "{Ctrl}" not in ass


def test_timeline_prefers_real_audio_duration():
    scenes = [SceneInput("a", 1, "Hello there.", audio_seconds=4.0), SceneInput("b", 2, "Short."),
              SceneInput("c", 3, "word " * 60, options={"min_seconds": 40})]
    p = plan(scenes)
    assert p[0].duration_source == "audio" and p[0].duration == pytest.approx(4.35)
    assert p[1].duration_source == "minimum" and p[1].duration == 2.0
    assert p[2].duration >= 40
    assert total_seconds(p, 2.5, 2.5) == pytest.approx(p[-1].start + p[-1].duration + 5)


def test_chapters_start_at_zero_and_format():
    p = plan([SceneInput("a", 1, "x " * 40), SceneInput("b", 2, "y " * 40), SceneInput("c", 3, "z " * 40)])
    rows = chapters(p, {"b": "Second part"}, intro=2.5)
    assert rows[0]["start"] == 0 and rows[1]["title"] == "Second part"
    assert format_chapters(rows).startswith("0:00 ")


def test_render_settings_validation():
    for bad in (RenderSettings(fps=500), RenderSettings(aspect_ratio="4:3"), RenderSettings(width=1001, height=1000),
                RenderSettings(accent="purple"), RenderSettings(music_volume=3), RenderSettings(crf=2)):
        with pytest.raises(RenderError):
            bad.validate()
    assert RenderSettings(aspect_ratio="9:16").size() == (1080, 1920)
    assert RenderSettings(aspect_ratio="1:1").size() == (1080, 1080)


def test_metadata_validation_and_accuracy_warnings():
    assert meta.validate_metadata({"title": "x" * 101})
    assert meta.validate_metadata({"tags": ["a" * 300, "b" * 300]})
    assert not meta.validate_metadata({"title": "ok", "tags": ["notes"]})
    warns = meta.accuracy_warnings({"title": "Acme Notes in 5 minutes", "description": "Works with Dropbox"},
                                   "Welcome to Acme Notes. Share folders.", [])
    assert any("Dropbox" in w for w in warns) and any("5" in w for w in warns)
    assert not meta.accuracy_warnings({"title": "Acme Notes"}, "Welcome to Acme Notes", [])


def test_thumbnail_templates_render_png_and_validate():
    for t in TEMPLATES:
        png = render_thumbnail("How to share folders in Acme Notes", t, brand="TUTORIAL")
        assert png[:4] == b"\x89PNG"
    with pytest.raises(ValueError):
        render_thumbnail("   ")
    with pytest.raises(ValueError):
        render_thumbnail("x", "nope")


def _make_footage(path, seconds=5):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc=size=1280x720:rate=25:duration={seconds}", "-c:v", "libvpx", "-b:v", "1M", str(path)], check=True)


def _make_tone(path, seconds, freq):  # TEST FIXTURE ONLY: a tone standing in for narration audio
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={seconds}", "-ar", "44100", str(path)], check=True)


def _scenes(tmp_path):
    footage, tone = tmp_path / "f.webm", tmp_path / "n.wav"
    _make_footage(footage)
    _make_tone(tone, 2.5, 220)
    actions = [{"t": 0.5, "type": "mouse", "x": 300, "y": 300}, {"t": 1.5, "type": "mouse", "x": 900, "y": 400}]
    return [
        SceneInput("s1", 1, "Welcome to the tutorial.", audio_path=str(tone), audio_seconds=2.5, footage_path=str(footage),
                   footage_seconds=5, footage_actions=actions, footage_size=(1280, 720),
                   options={"zoom": {"factor": 1.5, "cx": 0.3, "cy": 0.3}}),
        SceneInput("s2", 2, "This scene has no recording yet."),
    ]


@needs_ffmpeg
@pytest.mark.parametrize("ratio,size", [("16:9", (1920, 1080)), ("9:16", (1080, 1920)), ("1:1", (1080, 1080))])
def test_real_render_all_aspect_ratios(tmp_path, ratio, size):
    scenes = _scenes(tmp_path)
    st = RenderSettings(aspect_ratio=ratio, fps=24, burn_subtitles=(ratio == "16:9"), intro_text="Intro", outro_text="Outro")
    progress = []
    res = render(scenes, st, tmp_path / "out.mp4", progress=progress.append, workdir=tmp_path / "w")
    info = probe(res.path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (int(v["width"]), int(v["height"])) == size
    assert {s["codec_type"] for s in info["streams"]} >= {"video", "audio"}
    assert progress[-1] == 1.0 and res.cues
    checks = {c["name"]: c for c in quality_check(res, st, scenes)}
    assert checks["resolution"]["status"] == "pass" and checks["video_stream"]["status"] == "pass"
    assert checks["real_footage"]["status"] == "warn"  # scene 2 is a text card, and QC says so
    assert any("no footage" in w for w in res.warnings)


@needs_ffmpeg
def test_render_can_be_cancelled(tmp_path):
    with pytest.raises(RenderCancelled):
        render(_scenes(tmp_path), RenderSettings(), tmp_path / "o.mp4", should_stop=lambda: True, workdir=tmp_path / "w")


def test_render_rejects_empty_script(tmp_path):
    with pytest.raises(RenderError):
        render([], RenderSettings(), tmp_path / "o.mp4")
