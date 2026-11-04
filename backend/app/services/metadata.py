"""YouTube metadata validation. Deterministic checks that the metadata matches what the script actually says."""
import re

from app.media.timeline import PlannedScene, chapters, format_chapters

MAX_TITLE, MAX_DESC, MAX_TAGS_CHARS = 100, 5000, 500


def validate_metadata(meta: dict) -> list[str]:
    """Hard errors (block saving)."""
    errs = []
    if len(meta.get("title", "")) > MAX_TITLE:
        errs.append(f"Title must be {MAX_TITLE} characters or fewer")
    if len(meta.get("description", "")) > MAX_DESC:
        errs.append(f"Description must be {MAX_DESC} characters or fewer")
    if any(ch in meta.get("title", "") + meta.get("description", "") for ch in "<>"):
        errs.append("YouTube does not allow < or > in titles or descriptions")
    tags = meta.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errs.append("Tags must be a list of text values")
    elif sum(len(t) + 1 for t in tags) > MAX_TAGS_CHARS:
        errs.append(f"Tags are limited to {MAX_TAGS_CHARS} characters in total")
    return errs


def accuracy_warnings(meta: dict, script_text: str, extra_known: list[str]) -> list[str]:
    """Warn about capitalised names and numbers in title/description that never appear in the script or research."""
    known = (script_text + " " + " ".join(extra_known)).lower()
    text = f"{meta.get('title', '')} {meta.get('description', '')}"
    warns = []
    for token in sorted(set(re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", text))):
        if token.lower() not in known and token.lower() not in {"how", "the", "this", "you", "what", "why", "learn"}:
            warns.append(f"'{token}' appears in the metadata but not in the script or research")
    for num in sorted(set(re.findall(r"\b\d[\d,.]*\b", text))):
        if num not in known:
            warns.append(f"The number {num} appears in the metadata but not in the script or research")
    return warns[:12]


def chapter_block(planned: list[PlannedScene], titles: dict[str, str], intro: float) -> str:
    return format_chapters(chapters(planned, titles, intro))
