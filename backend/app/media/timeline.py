"""Scene timing. Durations come from real narration audio when it exists, else from a words-per-minute estimate."""
from dataclasses import dataclass, field

WPM = 150
MIN_SCENE_SECONDS = 2.0
SCENE_GAP_SECONDS = 0.35


@dataclass
class SceneInput:
    id: str
    position: int
    narration: str = ""
    subtitle: str | None = None
    audio_path: str | None = None
    audio_seconds: float | None = None
    footage_path: str | None = None
    footage_seconds: float | None = None
    footage_actions: list[dict] = field(default_factory=list)
    footage_size: tuple[int, int] | None = None
    options: dict = field(default_factory=dict)  # trim_start, zoom{cx,cy,factor}, min_seconds


@dataclass
class PlannedScene:
    scene: SceneInput
    start: float
    duration: float
    duration_source: str  # audio | estimate | minimum


def estimate_seconds(text: str, wpm: int = WPM) -> float:
    words = len(text.split())
    return words * 60.0 / wpm


def plan(scenes: list[SceneInput]) -> list[PlannedScene]:
    out, t = [], 0.0
    for s in sorted(scenes, key=lambda x: x.position):
        if s.audio_seconds:
            dur, src = s.audio_seconds + SCENE_GAP_SECONDS, "audio"
        else:
            est = estimate_seconds(s.narration) + SCENE_GAP_SECONDS
            dur, src = (est, "estimate") if est >= MIN_SCENE_SECONDS else (MIN_SCENE_SECONDS, "minimum")
        dur = max(dur, float(s.options.get("min_seconds", 0) or 0))
        out.append(PlannedScene(s, round(t, 3), round(dur, 3), src))
        t += dur
    return out


def total_seconds(planned: list[PlannedScene], intro: float = 0.0, outro: float = 0.0) -> float:
    return round(intro + (planned[-1].start + planned[-1].duration if planned else 0.0) + outro, 3)


def chapters(planned: list[PlannedScene], titles: dict[str, str], intro: float = 0.0) -> list[dict]:
    """YouTube chapters from the real timeline. YouTube needs the first chapter at 0:00."""
    rows = []
    for i, p in enumerate(planned):
        start = 0.0 if i == 0 else p.start + intro
        title = titles.get(p.scene.id) or (p.scene.narration.split(".")[0][:60] or f"Part {i + 1}")
        rows.append({"start": round(start, 1), "title": title.strip()})
    return rows


def format_chapters(rows: list[dict]) -> str:
    def fmt(sec: float) -> str:
        sec = int(sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    return "\n".join(f"{fmt(r['start'])} {r['title']}" for r in rows)
