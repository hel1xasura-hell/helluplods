"""Subtitle cues and SRT/VTT import/export (pure Python, no dependencies)."""
import re
from dataclasses import dataclass


@dataclass
class Cue:
    start: float
    end: float
    text: str


def wrap_text(text: str, max_chars: int = 42, max_lines: int = 2) -> list[str]:
    """Greedy word wrap into at most max_lines per cue; returns a list of cue texts (lines joined by newline)."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return ["\n".join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]


def cues_for_scene(text: str, start: float, end: float, max_chars: int = 42) -> list[Cue]:
    """Split one scene's subtitle text into timed cues proportional to their length."""
    chunks = wrap_text(" ".join(text.split()), max_chars)
    if not chunks or end <= start:
        return []
    weights = [max(len(c.replace("\n", " ")), 1) for c in chunks]
    total, t, out = sum(weights), start, []
    for chunk, w in zip(chunks, weights):
        dur = (end - start) * w / total
        out.append(Cue(round(t, 3), round(t + dur, 3), chunk))
        t += dur
    out[-1].end = round(end, 3)
    return out


def _ts(sec: float, comma: bool) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    return "".join(f"{i}\n{_ts(c.start, True)} --> {_ts(c.end, True)}\n{c.text}\n\n" for i, c in enumerate(cues, 1))


def to_vtt(cues: list[Cue]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_ts(c.start, False)} --> {_ts(c.end, False)}\n{c.text}\n\n" for c in cues)


_TS = r"(\d+):(\d{2}):(\d{2})[,.](\d{3})"
_RANGE = re.compile(rf"{_TS}\s*-->\s*{_TS}")


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT (or VTT-style) text so edited subtitles can be imported back. Ignores malformed blocks."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [l for l in block.split("\n") if l.strip() != ""]
        for i, line in enumerate(lines):
            m = _RANGE.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                body = "\n".join(lines[i + 1:])
                if end > start and body:
                    cues.append(Cue(start, end, body))
                break
    return cues


def to_ass(cues: list[Cue], width: int, height: int, font: str = "DejaVu Sans") -> str:
    """ASS file whose PlayRes equals the output size, so font size and margins are real pixels."""
    size = max(18, height // 24)
    outline = max(2, height // 360)
    side, bottom = width // 12, height // 12

    def t(sec: float) -> str:
        cs = int(round(sec * 100))
        h, rem = divmod(cs, 360000)
        m, rem = divmod(rem, 6000)
        s, c = divmod(rem, 100)
        return f"{h}:{m:02d}:{s:02d}.{c:02d}"

    def clean(text: str) -> str:
        return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")

    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{outline},0,2,{side},{side},{bottom},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return head + "".join(f"Dialogue: 0,{t(c.start)},{t(c.end)},Default,,0,0,0,,{clean(c.text)}\n" for c in cues)
