"""Text helpers shared by every summarizer, so the word-limit guarantee is
enforced the same way for the extractive baseline and the future model."""

import re

ELLIPSIS = "…"
# Don't cut at a clause boundary that would throw away more than this
# share of the allowed words; fall back to a plain word boundary instead.
MIN_CLAUSE_KEEP_RATIO = 0.6


def count_words(text: str) -> int:
    return len(text.split())


def trim_to_words(text: str, max_words: int) -> str:
    """Return `text` with at most `max_words` words, ending cleanly.

    Prefers cutting at the last clause boundary (, ; :) inside the limit;
    otherwise cuts at a word boundary. A trimmed result ends with "…"
    attached to its last word, so the word count never exceeds the limit.
    """
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    if max_words <= 0:
        return ""

    kept = words[:max_words]
    clause_end = max(
        (i for i, word in enumerate(kept) if word[-1:] in ",;:"),
        default=-1,
    )
    if clause_end + 1 >= max_words * MIN_CLAUSE_KEEP_RATIO:
        kept = kept[: clause_end + 1]

    last = re.sub(r"[\s,;:\-–—(]+$", "", kept[-1]) or kept[-1]
    if last[-1:] not in ".!?":
        last += ELLIPSIS
    return " ".join([*kept[:-1], last])
