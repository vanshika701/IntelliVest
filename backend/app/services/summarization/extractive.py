"""Classical extractive summarizer — the BASELINE for the final comparison
against our trained seq2seq model. No ML model, no external calls.

Pipeline (each step is its own function, tunables live in CONFIG):
 1. clean_text          strip HTML, boilerplate lines, extra whitespace
 2. split_sentences     abbreviation/decimal-aware sentence splitting
 3. tokenize            lowercase, drop stop words
 4. word_weights        TF-IDF-style weights; title + instrument words boosted
 5. score_sentence      length-normalised weight sum + position/number/name
                        bonuses, short/long/quote/boilerplate penalties
 6. select_sentences    greedy by score, skip near-duplicates, fit word limit
 7.                     re-order picks into original order
 8. trim_to_words       hard word limit, cut at a clause/word boundary
 9.                     short snippet -> trimmed snippet; nothing -> headline
"""

import hashlib
import html
import json
import math
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass

from app.services.summarization.base import Summarizer, SummaryInput, SummaryResult
from app.services.summarization.textutils import count_words, trim_to_words

# Bump whenever output can change: it is part of the summary cache key and
# is recorded with every logged summary.
ALGORITHM_VERSION = "1.1.0"


@dataclass(frozen=True)
class ExtractiveConfig:
    # Step 4 — word weights
    title_word_multiplier: float = 2.0
    instrument_word_multiplier: float = 2.5
    # Step 5 — sentence scoring
    length_norm_exponent: float = 0.7  # 1.0 = plain average, 0 = plain sum
    position_bonus: tuple[float, ...] = (0.30, 0.20, 0.10)  # sentences 1, 2, 3
    number_bonus: float = 0.10
    instrument_mention_bonus: float = 0.15
    min_sentence_words: int = 6
    max_sentence_words: int = 45
    short_sentence_multiplier: float = 0.5
    long_sentence_multiplier: float = 0.7
    quote_multiplier: float = 0.7
    boilerplate_multiplier: float = 0.1
    # Step 6 — selection
    duplicate_jaccard_threshold: float = 0.5
    min_relative_score: float = 0.3  # skip sentences scoring under 30% of the best
    max_sentences: int = 4


CONFIG = ExtractiveConfig()

STOP_WORDS = frozenset(
    """
    a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is it
    its itself just me more most my myself no nor not now of off on once only or other our ours
    ourselves out over own same she should so some such than that the their theirs them
    themselves then there these they this those through to too under until up very was we were
    what when where which while who whom why will with would you your yours yourself yourselves
    said says say new year years per cent according also one two may might us
    """.split()  # noqa: SIM905 — a word block is far easier to read and edit than a 150-item list
)

# Step 1: lines/sentences that are site furniture, not news.
_BOILERPLATE = re.compile(
    r"(cookie|subscribe|sign up|sign in|log in|newsletter|read more|also read|click here|"
    r"download (the|our) app|follow us|advertisement|sponsored|all rights reserved|©|"
    r"terms of (use|service)|privacy policy|share this|whatsapp channel|catch all the|"
    r"for more (news|updates)|stay updated|disclaimer:)",
    re.IGNORECASE,
)

# Step 2: abbreviations whose trailing dot never ends a sentence. Company
# suffixes (Ltd., Inc.) are not listed: they often do end a sentence, and
# when they don't, the next word is lowercase and won't trigger a split.
_ABBREVIATIONS = (
    "Rs", "Mr", "Mrs", "Ms", "Dr", "Prof", "Sr", "Jr", "St", "No", "Nos", "vs", "approx",
    "Govt", "Pvt", "Dept", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
    "Oct", "Nov", "Dec", "Fig", "Rev", "Gen", "Col", "Lt", "Capt", "Hon",
)
_DOT = "․"  # placeholder for protected dots, restored after splitting
_ABBREV_RE = re.compile(r"\b(" + "|".join(_ABBREVIATIONS) + r")\.", re.IGNORECASE)
_MULTI_DOT_ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|a\.m|p\.m|U\.S|U\.K|U\.A\.E|etc)\.", re.IGNORECASE)
_INITIAL_RE = re.compile(r"\b([A-Z])\.(?=\s*[A-Z])")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9₹$])")

_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_ENDS_SENTENCE = re.compile(r"[.!?:;\"'”’)]$")

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.'’][a-z0-9]+)*")
_NUMBER_RE = re.compile(r"(\d|₹|\brs\b|%|\bcrore\b|\blakh\b|\bbillion\b|\bmillion\b)", re.IGNORECASE)
_QUOTE_RE = re.compile(r"[\"“”]")


# --- Step 1 -----------------------------------------------------------------

def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    if "<" in text:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    text = _URL_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    kept = [line for line in lines if line and not (_BOILERPLATE.search(line) and count_words(line) < 30)]
    # A line without closing punctuation is a heading or caption; end it so
    # it becomes its own (short, low-scoring) sentence instead of merging
    # into the next one.
    if len(kept) > 1:
        kept = [line if _ENDS_SENTENCE.search(line) else f"{line}." for line in kept]
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


# --- Step 2 -----------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    protected = _MULTI_DOT_ABBREV_RE.sub(lambda m: m.group(0).replace(".", _DOT), text)
    protected = _ABBREV_RE.sub(lambda m: m.group(1) + _DOT, protected)
    protected = _INITIAL_RE.sub(lambda m: m.group(1) + _DOT, protected)
    # Decimals ("7.5%") never match: the boundary needs whitespace after the dot.
    parts = _SENTENCE_BOUNDARY.split(protected)
    return [part.replace(_DOT, ".").strip() for part in parts if part.strip()]


# --- Step 3 -----------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOP_WORDS and len(t) > 1]


# --- Step 4 -----------------------------------------------------------------

def word_weights(
    sentence_tokens: list[list[str]],
    title_tokens: set[str],
    instrument_tokens: set[str],
    config: ExtractiveConfig = CONFIG,
) -> dict[str, float]:
    """TF (within the article) × IDF (across the article's sentences),
    boosted for title and instrument-name words, scaled to max 1.0."""
    n = len(sentence_tokens)
    if n == 0:
        return {}
    tf = Counter(t for tokens in sentence_tokens for t in tokens)
    df = Counter(t for tokens in sentence_tokens for t in set(tokens))
    weights = {}
    for word, freq in tf.items():
        weight = freq * math.log(1 + n / df[word])
        if word in title_tokens:
            weight *= config.title_word_multiplier
        if word in instrument_tokens:
            weight *= config.instrument_word_multiplier
        weights[word] = weight
    top = max(weights.values(), default=0) or 1.0
    return {word: weight / top for word, weight in weights.items()}


# --- Step 5 -----------------------------------------------------------------

def score_sentence(
    index: int,
    sentence: str,
    tokens: list[str],
    weights: dict[str, float],
    instrument_tokens: set[str],
    config: ExtractiveConfig = CONFIG,
) -> float:
    if not tokens:
        return 0.0
    score = sum(weights.get(t, 0.0) for t in tokens) / (len(tokens) ** config.length_norm_exponent)

    if index < len(config.position_bonus):
        score += config.position_bonus[index]
    if _NUMBER_RE.search(sentence):
        score += config.number_bonus
    if instrument_tokens and instrument_tokens & set(tokens):
        score += config.instrument_mention_bonus

    words = count_words(sentence)
    if words < config.min_sentence_words:
        score *= config.short_sentence_multiplier
    elif words > config.max_sentence_words:
        score *= config.long_sentence_multiplier
    if _QUOTE_RE.search(sentence):
        score *= config.quote_multiplier
    if _BOILERPLATE.search(sentence):
        score *= config.boilerplate_multiplier
    return score


# --- Step 6 & 7 ---------------------------------------------------------------

def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def select_sentences(
    sentences: list[str],
    scores: list[float],
    token_sets: list[set[str]],
    max_words: int,
    config: ExtractiveConfig = CONFIG,
) -> list[int]:
    """Greedy: best score first, skip weak sentences, near-duplicates of
    anything already chosen, and anything that would break the word limit.
    Returns indices in original (reading) order."""
    if not sentences:
        return []
    floor = max(scores) * config.min_relative_score
    chosen: list[int] = []
    used_words = 0
    for i in sorted(range(len(sentences)), key=lambda k: scores[k], reverse=True):
        if len(chosen) >= config.max_sentences or scores[i] < floor or scores[i] <= 0:
            continue
        words = count_words(sentences[i])
        if used_words + words > max_words:
            continue
        if any(jaccard(token_sets[i], token_sets[j]) >= config.duplicate_jaccard_threshold for j in chosen):
            continue
        chosen.append(i)
        used_words += words
    return sorted(chosen)


# --- The summarizer -------------------------------------------------------------

class ExtractiveSummarizer(Summarizer):
    provider = "extractive"

    def __init__(self, config: ExtractiveConfig = CONFIG) -> None:
        self.config = config
        self.method = f"tfidf-extractive@{ALGORITHM_VERSION}"

    def cache_fingerprint(self) -> str:
        config_hash = hashlib.sha256(json.dumps(asdict(self.config), sort_keys=True).encode()).hexdigest()[:12]
        return f"{self.method}:{config_hash}"

    def summarize(self, item: SummaryInput) -> SummaryResult:
        started = time.perf_counter()
        summary = self._summarize_text(item)
        return SummaryResult(
            summary=summary,
            word_count=count_words(summary),
            provider=self.provider,
            method=self.method,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def _summarize_text(self, item: SummaryInput) -> str:
        max_words = item.max_words
        title = clean_text(item.title)
        body = clean_text(item.text)

        # Boilerplate can hide inside a paragraph, so filter per sentence too.
        sentences = [s for s in split_sentences(body) if not _BOILERPLATE.search(s)]
        # Step 9: nothing usable -> headline. A short snippet still goes
        # through selection (drops duplicates) and comes out ~unchanged.
        if not sentences:
            return trim_to_words(title, max_words)

        sentence_tokens = [tokenize(s) for s in sentences]
        token_sets = [set(t) for t in sentence_tokens]
        instrument_tokens = set(tokenize(item.instrument_name or ""))
        weights = word_weights(sentence_tokens, set(tokenize(title)), instrument_tokens, self.config)
        scores = [
            score_sentence(i, s, sentence_tokens[i], weights, instrument_tokens, self.config)
            for i, s in enumerate(sentences)
        ]

        picked = select_sentences(sentences, scores, token_sets, max_words, self.config)
        if not picked:
            # Every sentence alone is over the limit: trim the best one (step 8).
            best = max(range(len(sentences)), key=lambda k: scores[k])
            return trim_to_words(sentences[best], max_words)
        # Step 8: the selection already fits, but enforce the limit in code regardless.
        return trim_to_words(" ".join(sentences[i] for i in picked), max_words)
