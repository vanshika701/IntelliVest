"""Compare Hugging Face summarization models with the shipped extractive
summarizer (Phase 5).

    .venv/Scripts/python ml/compare_summarizers.py              # 100 articles
    .venv/Scripts/python ml/compare_summarizers.py --sample 20  # faster

Test set: kdave/Indian_Financial_News on Hugging Face (about 26,000
articles from Moneycontrol, Business Today, Financial Express and others,
each with a reference summary). A seeded random sample of articles is
used. The reference summaries look machine-written (lowercase, in the
style of CNN/DailyMail-trained models), so ROUGE against them favours
models of that style. The checks that need no reference count as much:

- rouge1/rouge2/rougeL: F1 against the reference, the project's own
  ROUGE (backend/app/services/summarization/evaluation.py), same for all.
- number_support: share of figures in the summary (12.5%, Rs 1.2 trillion,
  2020) that also appear in the article. A figure the article doesn't
  contain is made up, the worst error for financial news.
- unsupported_number_rate: share of summaries with at least one such figure.
- novel_bigrams: share of summary word pairs not in the article (0 means
  copied word for word, higher means rewritten).
- avg_words, word_limit_compliance (app limit, 100 words by default),
  seconds per article on this CPU, parameter count.

Every summary is passed through the app's trim_to_words, as the app
would. Output: ml/models/summarizer_comparison/metrics.json and
samples.json (three articles with every model's summary).
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from app.services.summarization.base import SummaryInput
from app.services.summarization.evaluation import (
    rouge_scores,
    rouge_tokens,
)
from app.services.summarization.extractive import ExtractiveSummarizer
from app.services.summarization.textutils import (
    count_words,
    trim_to_words,
)

CACHE = ML_DIR / "models" / "hf_cache"
OUT = ML_DIR / "models" / "summarizer_comparison"
MAX_WORDS = 100

# name -> (description, max input tokens, prefix for T5-style models)
MODELS = {
    "sshleifer/distilbart-cnn-12-6": ("DistilBART, CNN/DailyMail news", 1024, ""),
    "facebook/bart-large-cnn": ("BART-large, CNN/DailyMail news (Lewis et al. 2020)", 1024, ""),
    "human-centered-summarization/financial-summarization-pegasus": (
        "PEGASUS fine-tuned on financial news (Bloomberg)",
        512,
        "",
    ),
    "Falconsai/text_summarization": ("T5-small fine-tuned for summarization", 512, "summarize: "),
}

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def number_support(summary: str, article: str) -> tuple[float | None, bool]:
    found = numbers(summary)
    if not found:
        return None, False
    source = numbers(article)
    supported = sum(n in source for n in found)
    return supported / len(found), supported < len(found)


def novel_bigrams(summary: str, article: str) -> float:
    s, a = rouge_tokens(summary), rouge_tokens(article)
    pairs = list(zip(s, s[1:]))
    if not pairs:
        return 0.0
    source = set(zip(a, a[1:]))
    return sum(p not in source for p in pairs) / len(pairs)


def load_articles(sample: int, seed: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("kdave/Indian_Financial_News", split="train", cache_dir=str(CACHE / "datasets"))
    rng = np.random.default_rng(seed)
    out = []
    for i in rng.permutation(len(ds)):
        row = ds[int(i)]
        text, ref = (row.get("Content") or "").strip(), (row.get("Summary") or "").strip()
        # Skip stubs and pages where the scrape caught little text.
        if count_words(text) >= 120 and count_words(ref) >= 15:
            out.append({"url": row["URL"], "text": text, "reference": ref})
        if len(out) == sample:
            break
    return out


def hf_summarizer(name: str, max_input: int, prefix: str):
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(name, cache_dir=CACHE)
    model = AutoModelForSeq2SeqLM.from_pretrained(name, cache_dir=CACHE).eval()
    params = sum(p.numel() for p in model.parameters()) / 1e6

    def run(text: str) -> str:
        enc = tok(prefix + text, truncation=True, max_length=max_input, return_tensors="pt")
        with torch.no_grad():
            ids = model.generate(
                **enc, num_beams=4, max_new_tokens=160, min_new_tokens=30, no_repeat_ngram_size=3, early_stopping=True
            )
        return tok.decode(ids[0], skip_special_tokens=True).replace("<n>", " ")

    return run, params, model


def score(name: str, desc: str, params: float | None, run, articles: list[dict]) -> tuple[dict, list[str]]:
    rows, summaries = [], []
    for k, art in enumerate(articles):
        began = time.perf_counter()
        summary = trim_to_words(run(art["text"]), MAX_WORDS)
        seconds = time.perf_counter() - began
        support, unsupported = number_support(summary, art["text"])
        rows.append(
            {
                **rouge_scores(summary, art["reference"]),
                "support": support,
                "unsupported": unsupported,
                "novel": novel_bigrams(summary, art["text"]),
                "words": count_words(summary),
                "seconds": seconds,
            }
        )
        summaries.append(summary)
        if (k + 1) % 20 == 0:
            print(f"    {k + 1}/{len(articles)}", flush=True)
    supports = [r["support"] for r in rows if r["support"] is not None]
    result = {
        "description": desc,
        "parameters_millions": round(params, 1) if params else None,
        "articles": len(rows),
        **{m: float(np.mean([r[m] for r in rows])) for m in ("rouge1", "rouge2", "rougeL")},
        "number_support": float(np.mean(supports)) if supports else None,
        "summaries_with_numbers": len(supports),
        "unsupported_number_rate": float(np.mean([r["unsupported"] for r in rows])),
        "novel_bigrams": float(np.mean([r["novel"] for r in rows])),
        "avg_words": float(np.mean([r["words"] for r in rows])),
        "word_limit_compliance": float(np.mean([r["words"] <= MAX_WORDS for r in rows])),
        "seconds_per_article": float(np.mean([r["seconds"] for r in rows])),
    }
    print(
        f"  {name}: R1 {result['rouge1']:.3f} R2 {result['rouge2']:.3f} RL {result['rougeL']:.3f}"
        f" numbers ok {result['number_support'] if result['number_support'] is not None else float('nan'):.1%}"
        f" novel {result['novel_bigrams']:.1%} {result['avg_words']:.0f} words {result['seconds_per_article']:.2f}s",
        flush=True,
    )
    return result, summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--skip", nargs="*", default=[], help="model names to leave out")
    parser.add_argument(
        "--only", nargs="*", default=None, help="run only these Hugging Face models and merge into metrics.json"
    )
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    articles = load_articles(args.sample, args.seed)
    print(f"{len(articles)} articles, average {np.mean([count_words(a['text']) for a in articles]):.0f} words;"
          f" references average {np.mean([count_words(a['reference']) for a in articles]):.0f} words", flush=True)

    results, all_summaries = {}, {}
    if args.only is not None and (OUT / "metrics.json").exists():
        results = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))["models"]
        all_summaries = {
            m: [s["summaries"].get(m, "") for s in json.loads((OUT / "samples.json").read_text(encoding="utf-8"))]
            for m in results
        }
    extractive = ExtractiveSummarizer()

    def run_extractive(text: str) -> str:
        return extractive.summarize(SummaryInput(title="", text=text, max_words=MAX_WORDS)).summary

    def run_lead(text: str) -> str:
        return trim_to_words(text, 60)

    baselines = () if args.only is not None else (
        ("lead-60", "First 60 words of the article (standard news baseline)", None, run_lead),
        (extractive.method, "Shipped TF-IDF extractive summarizer", None, run_extractive),
    )
    for name, desc, params, run in baselines:
        print(f"\n{name}", flush=True)
        results[name], all_summaries[name] = score(name, desc, params, run, articles)
    for name, (desc, max_input, prefix) in MODELS.items():
        if name in args.skip or (args.only is not None and name not in args.only):
            continue
        print(f"\n{name}", flush=True)
        try:
            run, params, model = hf_summarizer(name, max_input, prefix)
        except Exception as exc:  # noqa: BLE001 — one model failing to load shouldn't stop the rest
            print(f"  could not load: {exc}")
            results[name] = {"description": desc, "error": str(exc)}
            continue
        results[name], all_summaries[name] = score(name, desc, params, run, articles)
        del run, model

    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "kdave/Indian_Financial_News (train split, seeded sample)",
        "sample": len(articles),
        "seed": args.seed,
        "max_words": MAX_WORDS,
        "generation": "beam search, 4 beams, 30-160 new tokens, no repeated trigrams",
        "torch_threads": args.threads,
        "models": results,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    samples = [
        {"url": a["url"], "reference": a["reference"], "summaries": {m: s[k] for m, s in all_summaries.items() if len(s) > k}}
        for k, a in enumerate(articles[:3])
    ]
    (OUT / "samples.json").write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
