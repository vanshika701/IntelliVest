"""Time every app summarizer the way the news digest calls it (Phase 5).

    .venv/Scripts/python ml/time_summarizers.py             # 10 articles each
    .venv/Scripts/python ml/time_summarizers.py --sample 5

ml/compare_summarizers.py measures quality, but its timings ran while
other jobs shared the CPU. This runs each summarizer in
backend/app/services/summarization/factory.py alone, one after another,
on the same articles from kdave/Indian_Financial_News, through the app's
own Summarizer classes. The first article per model is a warm-up (model
load) and is left out. Output: ml/models/summarizer_comparison/timing.json.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import torch

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from compare_summarizers import OUT, load_articles  # noqa: E402

from app.services.summarization.base import SummaryInput  # noqa: E402
from app.services.summarization.factory import SUMMARIZERS, get_summarizer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=10)
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    articles = load_articles(args.sample + 1, seed=7)
    results = {}
    for key in SUMMARIZERS:
        summarizer = get_summarizer(key)
        seconds = []
        for k, article in enumerate(articles):
            began = time.perf_counter()
            summarizer.summarize(SummaryInput(title="", text=article["text"], max_words=100))
            if k:  # the first call loads the model
                seconds.append(time.perf_counter() - began)
        results[key] = {
            "median_seconds": statistics.median(seconds),
            "mean_seconds": statistics.fmean(seconds),
            "max_seconds": max(seconds),
            "articles": len(seconds),
        }
        print(f"{key:20} median {results[key]['median_seconds']:.2f}s  max {results[key]['max_seconds']:.2f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "timing.json").write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "torch_threads": args.threads,
                "cpu_note": "AMD Ryzen 5 5500U laptop, nothing else running",
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
