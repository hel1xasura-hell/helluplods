"""Deterministic claim checking against pages that were actually fetched.

This checks TEXT CORROBORATION only: does the claim's wording appear on the pages we visited? It does not
establish truth, and results are labelled accordingly."""
import re

STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "your", "you", "our", "is", "are",
        "it", "that", "this", "by", "as", "at", "from", "be", "can", "all", "more"}


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def check_claim(claim: str, pages: dict[str, str], threshold: float = 0.7) -> dict:
    """pages maps url -> visible text. A page corroborates when >= threshold of the claim's terms appear in it."""
    terms = _terms(claim)
    if not terms:
        return {"claim": claim, "status": "not_checkable", "pages": []}
    hits = []
    for url, text in pages.items():
        found = len(terms & _terms(text)) / len(terms)
        if found >= threshold:
            hits.append(url)
    status = "corroborated_on_multiple_pages" if len(hits) >= 2 else "found_on_one_page" if hits else "not_found_in_pages"
    return {"claim": claim, "status": status, "pages": hits, "method": "text_match", "proves_truth": False}
