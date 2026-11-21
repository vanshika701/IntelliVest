"""Evaluate a Summarizer implementation over logged articles.

Run from backend/ with the venv active, e.g.:

    python -m scripts.eval_summarizer                       # extractive baseline
    python -m scripts.eval_summarizer --provider ml         # our trained model, later
    python -m scripts.eval_summarizer --references refs.jsonl --input-kind full_text --out report.json

Inputs come from data/summarization_log.jsonl, collected by running the
app with LOG_SUMMARIES=true. References are optional JSONL lines of
{"url": ..., "reference": "<human-written summary>"}; without them,
ROUGE is skipped. Run the same sample (same --seed) for every model you
compare.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from app.core.config import settings
from app.services.news_summary_service import _log_path
from app.services.summarization import get_summarizer
from app.services.summarization.evaluation import evaluate


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default=None, help="extractive | ml (default: SUMMARIZER_PROVIDER)")
    parser.add_argument("--log", type=Path, default=None, help="logged articles JSONL (default: SUMMARY_LOG_PATH)")
    parser.add_argument("--references", type=Path, default=None, help='JSONL of {"url", "reference"}')
    parser.add_argument("--sample", type=int, default=50, help="max articles to evaluate")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-words", type=int, default=settings.summarizer_max_words)
    parser.add_argument("--input-kind", choices=["full_text", "snippet", "headline"], default=None)
    parser.add_argument("--out", type=Path, default=None, help="also write the report as JSON")
    args = parser.parse_args()

    log_path = args.log or _log_path()
    if not log_path.exists():
        print(f"No log at {log_path}. Run the app with LOG_SUMMARIES=true and open some instruments first.")
        return 1

    # Latest entry per article, optionally one input kind only.
    latest: dict[str, dict] = {}
    for record in load_jsonl(log_path):
        if args.input_kind is None or record.get("input_kind") == args.input_kind:
            latest[record["url"]] = record
    records = sorted(latest.values(), key=lambda r: r["url"])
    random.Random(args.seed).shuffle(records)
    records = records[: args.sample]
    if not records:
        print("No matching logged articles.")
        return 1

    references = None
    if args.references:
        references = {r["url"]: r["reference"] for r in load_jsonl(args.references)}

    report = evaluate(get_summarizer(args.provider), records, args.max_words, references)
    report.update({"log": str(log_path), "seed": args.seed, "input_kind": args.input_kind or "all"})

    width = max(len(k) for k in report)
    for key, value in report.items():
        shown = f"{value:.4f}" if isinstance(value, float) else value
        print(f"{key:<{width}}  {shown}")
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.out}")
    return 0 if report["failures"] < report["items"] else 2


if __name__ == "__main__":
    sys.exit(main())
