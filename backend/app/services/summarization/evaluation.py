"""ROUGE-1/2/L (F1) without extra dependencies, for comparing the extractive
baseline with our trained model. Standard definitions over lowercase
alphanumeric tokens, no stemming — use the same settings for every model
being compared."""

import re
from collections import Counter

from app.services.summarization.base import Summarizer, SummaryFailure, SummaryInput
from app.services.summarization.textutils import count_words

_TOKEN = re.compile(r"[a-z0-9]+")


def rouge_tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _f1(overlap: int, candidate_total: int, reference_total: int) -> float:
    if overlap == 0 or candidate_total == 0 or reference_total == 0:
        return 0.0
    precision = overlap / candidate_total
    recall = overlap / reference_total
    return 2 * precision * recall / (precision + recall)


def rouge_n(candidate: str, reference: str, n: int) -> float:
    def ngrams(tokens: list[str]) -> Counter:
        return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))

    cand, ref = ngrams(rouge_tokens(candidate)), ngrams(rouge_tokens(reference))
    overlap = sum((cand & ref).values())
    return _f1(overlap, sum(cand.values()), sum(ref.values()))


def _lcs_length(a: list[str], b: list[str]) -> int:
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if x == y else max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def rouge_l(candidate: str, reference: str) -> float:
    cand, ref = rouge_tokens(candidate), rouge_tokens(reference)
    return _f1(_lcs_length(cand, ref), len(cand), len(ref))


def rouge_scores(candidate: str, reference: str) -> dict[str, float]:
    return {
        "rouge1": rouge_n(candidate, reference, 1),
        "rouge2": rouge_n(candidate, reference, 2),
        "rougeL": rouge_l(candidate, reference),
    }


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def evaluate(
    summarizer: Summarizer, records: list[dict], max_words: int, references: dict[str, str] | None = None
) -> dict:
    """Run `summarizer` over logged records ({title, article_text, url}) and
    report word-limit compliance, latency, compression and — when
    reference summaries are given (by url) — mean ROUGE F1."""
    inputs = [
        SummaryInput(title=r.get("title") or "", text=r.get("article_text") or "", max_words=max_words, url=r.get("url"))
        for r in records
    ]
    results = summarizer.summarize_batch(inputs)
    ok = [(item, result) for item, result in zip(inputs, results, strict=True) if not isinstance(result, SummaryFailure)]

    report: dict = {
        "provider": summarizer.provider,
        "method": summarizer.method,
        "max_words": max_words,
        "items": len(inputs),
        "failures": len(inputs) - len(ok),
    }
    if not ok:
        return report

    latencies = [r.latency_ms for _, r in ok]
    ratios = [r.word_count / count_words(i.text) for i, r in ok if count_words(i.text) > 0]
    report.update(
        {
            "word_limit_compliance": sum(r.word_count <= max_words for _, r in ok) / len(ok),
            "avg_summary_words": sum(r.word_count for _, r in ok) / len(ok),
            "latency_ms_avg": sum(latencies) / len(latencies),
            "latency_ms_p95": _percentile(latencies, 95),
            "compression_ratio_avg": sum(ratios) / len(ratios) if ratios else None,
        }
    )
    if references:
        scored = [rouge_scores(r.summary, references[i.url]) for i, r in ok if i.url in references]
        if scored:
            report["rouge_items"] = len(scored)
            for metric in ("rouge1", "rouge2", "rougeL"):
                report[metric] = sum(s[metric] for s in scored) / len(scored)
    return report
