"""Small text helpers shared by the rename modules."""

from __future__ import annotations

from typing import List, Set

# Small words kept lowercase in Title Case (unless first word).
SMALL_WORDS: Set[str] = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "of", "to", "in", "on",
    "at", "by", "with", "vs", "from", "as", "into", "over", "per",
}


def title_case(text: str, enabled: bool = True) -> str:
    text = text.strip()
    if not text or not enabled:
        return text
    words = text.split(" ")
    out: List[str] = []
    for i, w in enumerate(words):
        if not w:
            continue
        lw = w.lower()
        if len(w) > 1 and w.isupper():
            out.append(w)  # keep acronyms like SWAT, FBI
        elif i != 0 and lw in SMALL_WORDS:
            out.append(lw)
        elif w[0].isalpha():
            out.append(w[0].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


def sentence_case(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    lowered = text.lower()
    for i, ch in enumerate(lowered):
        if ch.isalpha():
            return lowered[:i] + ch.upper() + lowered[i + 1:]
    return lowered
