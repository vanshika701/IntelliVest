"""ROUGE-1/2/L (F1) without extra dependencies, for comparing the extractive
baseline with our trained model. Standard definitions over lowercase
alphanumeric tokens, no stemming — use the same settings for every model
being compared."""

import re
from collections import Counter

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
