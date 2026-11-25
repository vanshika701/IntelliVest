"""Text helpers shared by every summarizer, so the word-limit guarantee is
enforced the same way for the extractive baseline and the future model."""

import re

ELLIPSIS = "…"
# Don't cut at a clause boundary that would throw away more than this
# share of the allowed words; fall back to a plain word boundary instead.
MIN_CLAUSE_KEEP_RATIO = 0.6

_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*(?=\s)|\n")


_COMPLETE_SENTENCE_END = re.compile(
    r"(?<!\bRs)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bNo)(?<!\bCo)(?<!\bvs)(?<!\bLtd)(?<!\bInc)(?<!\bMrs)(?<!\bPvt)"
    r"(?<!\.)[.!?](?!\.)[\"'”’)\]]*(?=\s|$)"
)


def complete_sentences(text: str) -> str:
    """`text` without a trailing unfinished sentence ("...prices of its cars
    and SUVs ..."). Empty when it contains no complete sentence."""
    ends = [m.end() for m in _COMPLETE_SENTENCE_END.finditer(text)]
    return text[: ends[-1]].strip() if ends else ""


def count_words(text: str) -> int:
    return len(text.split())


def first_words(text: str, max_words: int) -> str:
    """At most the first `max_words` words of a summarizer *input*. Keeps
    line breaks (they mark headings) and drops a trailing cut-off sentence
    unless that would lose more than half of the text."""
    words = list(re.finditer(r"\S+", text))
    if len(words) <= max_words:
        return text
    if max_words <= 0:
        return ""
    end = words[max_words - 1].end()
    # One extra character, so a sentence ending exactly at the cut is seen.
    ends = [m.end() for m in _SENTENCE_END.finditer(text[: end + 1])]
    if ends and ends[-1] >= end / 2:
        end = min(end, ends[-1])
    return text[:end].rstrip()


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
