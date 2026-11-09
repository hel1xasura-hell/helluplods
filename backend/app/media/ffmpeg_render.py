"""FFmpeg rendering. Real footage (recordings) + narration audio + subtitles -> MP4.

Never invents footage: a scene with no recording becomes a plain text card, and quality control flags it."""
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.media.subtitles import Cue, cues_for_scene, to_ass, to_srt, to_vtt, wrap_text
from app.media.timeline import PlannedScene, SceneInput, plan, total_seconds

PRESETS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CARD_SECONDS = 2.5


class RenderError(Exception):
    pass


class RenderCancelled(Exception):
    pass


def default_font() -> str:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    raise RenderError("No usable font found. Install fonts-dejavu-core or set a font path.")


@dataclass
class RenderSettings:
    aspect_ratio: str = "16:9"
    width: int | None = None
    height: int | None = None
    fps: int = 30
    burn_subtitles: bool = False
    intro_text: str | None = None
    outro_text: str | None = None
    accent: str = "#8d6bff"
    background: str = "#0f0e13"
    font_path: str | None = None
    music_path: str | None = None
    music_volume: float = 0.12
    cursor_highlight: bool = True
    crf: int = 20

    def size(self) -> tuple[int, int]:
        if self.width and self.height:
            return self.width, self.height
        return PRESETS[self.aspect_ratio]

    def validate(self) -> None:
        if self.aspect_ratio not in PRESETS:
            raise RenderError(f"Unsupported aspect ratio {self.aspect_ratio}")
        w, h = self.size()
        if not (320 <= w <= 3840 and 320 <= h <= 3840) or w % 2 or h % 2:
            raise RenderError("Width and height must be even numbers between 320 and 3840")
        if not 12 <= self.fps <= 60:
            raise RenderError("FPS must be between 12 and 60")
        if not (HEX.match(self.accent) and HEX.match(self.background)):
            raise RenderError("Colours must look like #aabbcc")
        if not 0 <= self.music_volume <= 1:
            raise RenderError("Music volume must be between 0 and 1")
        if not 10 <= self.crf <= 35:
            raise RenderError("CRF must be between 10 and 35")


@dataclass
class RenderResult:
    path: Path
    duration: float
    srt: str
    vtt: str
    planned: list[PlannedScene]
    cues: list[Cue]
    warnings: list[str] = field(default_factory=list)
    intro_seconds: float = 0.0
    outro_seconds: float = 0.0


def _color(hex_: str) -> str:
    return "0x" + hex_.lstrip("#")


def _run(cmd: list[str], cwd: Path, should_stop: Callable[[], bool] | None, timeout: float = 900) -> None:
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start = time.monotonic()
    while True:
        try:
            _, err = proc.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if should_stop and should_stop():
                proc.kill()
                proc.communicate()
                raise RenderCancelled()
            if time.monotonic() - start > timeout:
                proc.kill()
                proc.communicate()
                raise RenderError("FFmpeg timed out")
    if proc.returncode != 0:
        raise RenderError(f"FFmpeg failed: {(err or '').strip()[-600:]}")


def probe(path: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RenderError("ffprobe is not installed")
    out = subprocess.run([exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RenderError("Could not read the media file")
    return json.loads(out.stdout)


def _piecewise(points: list[tuple[float, float]]) -> str:
    """Linear interpolation expression over time t, built from nested if() (commas escaped for filtergraphs)."""
    if not points:
        return "0"
    expr = f"{points[-1][1]:.2f}"
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        span = max(t1 - t0, 0.001)
        expr = f"if(lt(t,{t1:.3f}),{v0:.2f}+({v1:.2f}-{v0:.2f})*(t-{t0:.3f})/{span:.3f},{expr})"
    expr = f"if(lt(t,{points[0][0]:.3f}),{points[0][1]:.2f},{expr})"
    return expr.replace(",", "\\,")


def make_cursor_png(path: Path, radius: int, color: str) -> None:
    from PIL import Image, ImageDraw

    d = radius * 2
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r, g, b = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    draw.ellipse([2, 2, d - 3, d - 3], fill=(r, g, b, 130), outline=(r, g, b, 255), width=max(2, radius // 8))
    img.save(path)


def _card(work: Path, name: str, text: str, seconds: float, st: RenderSettings, big: bool) -> Path:
    """A plain text card (intro/outro/no-footage scene). Clearly a card, never fake footage."""
    w, h = st.size()
    font = st.font_path or default_font()
    wrapped = "\n".join(wrap_text(text, 24 if big else 40, 99)[0].split("\n")) if text else ""
    (work / f"{name}.txt").write_text(wrapped or " ")
    size = int(h * (0.075 if big else 0.042))
    out = work / f"{name}.mp4"
    vf = (f"drawbox=x=0:y=ih*0.82:w=iw:h=ih*0.012:color={_color(st.accent)}:t=fill,"
          f"drawtext=fontfile='{font}':textfile={name}.txt:fontsize={size}:fontcolor=white:line_spacing=12:"
          f"x=(w-text_w)/2:y=(h-text_h)/2,fade=t=in:d=0.3,fade=t=out:st={max(seconds - 0.3, 0):.2f}:d=0.3,format=yuv420p")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c={_color(st.background)}:s={w}x{h}:r={st.fps}:d={seconds:.3f}",
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-vf", vf, "-t", f"{seconds:.3f}", "-af", f"afade=t=in:d=0.2,afade=t=out:st={max(seconds - 0.3, 0):.2f}:d=0.3",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(st.crf), "-pix_fmt", "yuv420p", "-r", str(st.fps),
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", str(out)]
    return out, cmd


def build_scene_cmd(p: PlannedScene, idx: int, st: RenderSettings, work: Path) -> tuple[Path, list[str], list[str]]:
    """Returns (clip_path, command, warnings)."""
    s, w_h, warns = p.scene, st.size(), []
    W, H = w_h
    D = p.duration
    out = work / f"scene_{idx:03d}.mp4"
    fade_out = max(D - 0.3, 0)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    n_in = 0
    if s.footage_path:
        trim = float(s.options.get("trim_start", 0) or 0)
        if trim:
            cmd += ["-ss", f"{trim:.3f}"]
        cmd += ["-i", s.footage_path]
        v_idx, n_in = 0, 1
        fw, fh = s.footage_size or (1280, 720)
        scale = min(W / fw, H / fh)
        ox, oy = (W - fw * scale) / 2, (H - fh * scale) / 2
        chain = [f"[{v_idx}:v]fps={st.fps}", f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos",
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={_color(st.background)}",
                 f"tpad=stop_mode=clone:stop_duration={D:.3f}", f"trim=duration={D:.3f}", "setpts=PTS-STARTPTS", "setsar=1"]
        label = "[base]"
        parts = [",".join(chain) + label]
        pts = [(a["t"] - trim, a["x"], a["y"]) for a in s.footage_actions if a.get("type") == "mouse" and "x" in a]
        pts = [(t, x, y) for t, x, y in pts if t >= -0.01]
        if st.cursor_highlight and pts:
            radius = max(18, int(min(W, H) * 0.034))
            png = work / "cursor.png"
            if not png.exists():
                make_cursor_png(png, radius, st.accent)
            cmd += ["-loop", "1", "-i", str(png)]
            c_idx, n_in = n_in, n_in + 1
            xs = _piecewise([(t, ox + x * scale - radius) for t, x, y in pts])
            ys = _piecewise([(t, oy + y * scale - radius) for t, x, y in pts])
            parts.append(f"{label}[{c_idx}:v]overlay=x='{xs}':y='{ys}':shortest=1[cur]")
            label = "[cur]"
        zoom = s.options.get("zoom")
        if zoom:
            f = max(1.0, min(float(zoom.get("factor", 1.4)), 3.0))
            cx, cy = float(zoom.get("cx", 0.5)), float(zoom.get("cy", 0.5))
            z = f"(1+({f}-1)*min(t/1\\,1))"
            parts.append(f"{label}scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,"
                         f"crop={W}:{H}:'(iw-{W})*{cx}':'(ih-{H})*{cy}'[zm]")
            label = "[zm]"
        parts.append(f"{label}fade=t=in:d=0.3,fade=t=out:st={fade_out:.2f}:d=0.3,format=yuv420p[v]")
        fc = ";".join(parts)
    else:
        warns.append(f"Scene {s.position} has no footage; rendered as a text card.")
        card_path, card_cmd = _card(work, f"card_{idx:03d}", s.subtitle or s.narration, D, st, big=False)
        return card_path, card_cmd, warns

    if s.audio_path:
        cmd += ["-i", s.audio_path]
        a_idx = n_in
        afilt = (f"[{a_idx}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={D:.3f},"
                 f"atrim=0:{D:.3f},afade=t=in:d=0.15,afade=t=out:st={fade_out:.2f}:d=0.3[a]")
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        a_idx = n_in
        afilt = f"[{a_idx}:a]atrim=0:{D:.3f}[a]"
    cmd += ["-filter_complex", fc + ";" + afilt, "-map", "[v]", "-map", "[a]", "-t", f"{D:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(st.crf), "-pix_fmt", "yuv420p", "-r", str(st.fps),
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(out)]
    return out, cmd, warns


def render(scenes: list[SceneInput], st: RenderSettings, out_path: Path,
           progress: Callable[[float], None] | None = None, should_stop: Callable[[], bool] | None = None,
           workdir: Path | None = None) -> RenderResult:
    st.validate()
    if not scenes:
        raise RenderError("The script has no scenes")
    if not shutil.which("ffmpeg"):
        raise RenderError("ffmpeg is not installed")
    own = workdir is None
    work = Path(tempfile.mkdtemp(prefix="render_")) if own else workdir
    work.mkdir(parents=True, exist_ok=True)
    try:
        planned = plan(scenes)
        clips, warnings = [], []
        steps = len(planned) + 2
        done = 0

        def tick():
            nonlocal done
            done += 1
            if progress:
                progress(min(0.95, done / steps))

        intro = CARD_SECONDS if st.intro_text else 0.0
        outro = CARD_SECONDS if st.outro_text else 0.0
        if st.intro_text:
            path, cmd = _card(work, "intro", st.intro_text, intro, st, big=True)
            _run(cmd, work, should_stop)
            clips.append(path)
        for i, p in enumerate(planned):
            path, cmd, w = build_scene_cmd(p, i, st, work)
            warnings += w
            _run(cmd, work, should_stop)
            clips.append(path)
            tick()
        if st.outro_text:
            path, cmd = _card(work, "outro", st.outro_text, outro, st, big=True)
            _run(cmd, work, should_stop)
            clips.append(path)

        (work / "list.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
              "-c", "copy", "joined.mp4"], work, should_stop)
        tick()

        cues: list[Cue] = []
        for p in planned:
            text = p.scene.subtitle if p.scene.subtitle is not None else p.scene.narration
            cues += cues_for_scene(text, p.start + intro, p.start + intro + p.duration - 0.2)
        (work / "subs.srt").write_text(to_srt(cues))

        final = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", "joined.mp4"]
        loud = "loudnorm=I=-16:TP=-1.5:LRA=11"
        music = st.music_path
        if music:
            final += ["-stream_loop", "-1", "-i", music]
            afc = (f"[1:a]volume={st.music_volume}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,{loud}[a]")
        else:
            afc = f"[0:a]{loud}[a]"
        if cues and not st.burn_subtitles:
            final += ["-i", "subs.srt"]
        vchain = "[0:v]null[v]"
        if st.burn_subtitles and cues:
            sw, sh = st.size()
            (work / "subs.ass").write_text(to_ass(cues, sw, sh))
            vchain = "[0:v]subtitles=subs.ass[v]"
        final += ["-filter_complex", f"{vchain};{afc}", "-map", "[v]", "-map", "[a]"]
        if cues and not st.burn_subtitles:
            sub_idx = 2 if music else 1
            final += ["-map", f"{sub_idx}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
        final += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(st.crf), "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_path.resolve())]
        _run(final, work, should_stop)
        if progress:
            progress(1.0)
        info = probe(out_path)
        return RenderResult(out_path, float(info["format"]["duration"]), to_srt(cues), to_vtt(cues), planned, cues,
                            warnings, intro, outro)
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)


def measure_loudness(path: Path) -> float | None:
    """Integrated loudness (LUFS) via FFmpeg's loudnorm analysis; None if it cannot be measured."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                           "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=300)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.DOTALL)
    try:
        val = float(json.loads(m.group(0))["input_i"]) if m else None
    except (ValueError, KeyError):
        return None
    return val if val is not None and val > -70 else None


def quality_check(result: RenderResult, st: RenderSettings, scenes: list[SceneInput]) -> list[dict]:
    """Objective checks on the rendered file and the script. Statuses: pass | warn | fail."""
    checks: list[dict] = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    info = probe(result.path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    W, H = st.size()
    add("video_stream", "pass" if v else "fail", "Video stream present" if v else "No video stream")
    add("audio_stream", "pass" if a else "fail", "Audio stream present" if a else "No audio stream")
    if v:
        ok = int(v["width"]) == W and int(v["height"]) == H
        add("resolution", "pass" if ok else "fail", f"{v['width']}x{v['height']} (expected {W}x{H})")
    expected = total_seconds(result.planned, result.intro_seconds, result.outro_seconds)
    drift = abs(result.duration - expected)
    add("duration", "pass" if drift <= 1.0 else "warn", f"{result.duration:.1f}s rendered vs {expected:.1f}s planned")
    no_footage = [s.position for s in scenes if not s.footage_path]
    add("real_footage", "pass" if not no_footage else "warn",
        "Every scene uses a real recording" if not no_footage else f"Scenes without footage (text cards): {no_footage}")
    no_voice = [s.position for s in scenes if not s.audio_path]
    add("narration", "pass" if not no_voice else "warn",
        "Every scene has narration audio" if not no_voice else f"Scenes without narration audio: {no_voice}")
    add("subtitles", "pass" if result.cues else "warn", f"{len(result.cues)} subtitle cues")
    lufs = measure_loudness(result.path) if a else None
    if lufs is None:
        add("loudness", "warn", "Loudness could not be measured (silent or no audio)")
    else:
        add("loudness", "pass" if -19 <= lufs <= -13 else "warn", f"{lufs:.1f} LUFS (target about -16)")
    return checks
