"""Compare Hugging Face sentiment models against the shipped FinBERT (Phase 5).

    .venv/Scripts/python ml/compare_sentiment_models.py
    .venv/Scripts/python ml/compare_sentiment_models.py --sample 200   # faster

Every model is scored on the same three test sets, all mapped to
positive / negative / neutral:

1. realistic_headlines: the 30 hand-labelled Indian market headlines from
   evaluate_sentiment_on_realistic_news.py. Closest to what the app scores
   (news headlines and descriptions) and seen by no model.
2. twitter_validation: zeroshot/twitter-financial-news-sentiment, the
   validation split (Bearish/Bullish/Neutral). Short financial tweets;
   none of the models below were trained on it.
3. phrasebank: Financial PhraseBank (Malo et al. 2014, warwickai mirror,
   CC BY-NC-SA 3.0). WARNING: ProsusAI/finbert, the distilroberta model
   and FinancialBERT were trained on PhraseBank, so their scores there are
   partly memory, not skill. It is reported because it is the standard
   benchmark, but the other two sets decide.

Measured per model: accuracy, macro precision/recall/F1, weighted F1,
precision/recall/F1 per class, the confusion matrix, texts per second
(CPU, batch 32), parameter count. Output: ml/models/sentiment_comparison/
metrics.json.
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
from evaluate_sentiment_on_realistic_news import REALISTIC_NEWS_HEADLINES

CACHE = ML_DIR / "models" / "hf_cache"
OUT = ML_DIR / "models" / "sentiment_comparison"
LABELS = ["negative", "neutral", "positive"]

# name -> (description, label override when the config has none, trained on PhraseBank?)
MODELS = {
    "ProsusAI/finbert": ("FinBERT (Araci 2019), shipped now", None, True),
    "yiyanghkust/finbert-tone": (
        "FinBERT-tone (Huang, Wang & Yang 2023), analyst-report sentences",
        {0: "neutral", 1: "positive", 2: "negative"},
        False,
    ),
    "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis": (
        "DistilRoBERTa fine-tuned on Financial PhraseBank",
        None,
        True,
    ),
    "ahmedrachid/FinancialBERT-Sentiment-Analysis": (
        "FinancialBERT (Hazourli 2022), fine-tuned on Financial PhraseBank",
        None,
        True,
    ),
    "cardiffnlp/twitter-roberta-base-sentiment-latest": (
        "General (non-financial) tweet sentiment RoBERTa, as a control",
        None,
        False,
    ),
}
NORMALISE = {"bearish": "negative", "bullish": "positive"}


def datasets_for(sample: int, seed: int) -> dict[str, tuple[list[str], list[str]]]:
    from datasets import load_dataset

    rng = np.random.default_rng(seed)
    sets = {
        "realistic_headlines": (
            [t for t, _ in REALISTIC_NEWS_HEADLINES],
            [label for _, label in REALISTIC_NEWS_HEADLINES],
        )
    }
    tw = load_dataset("zeroshot/twitter-financial-news-sentiment", split="validation", cache_dir=str(CACHE / "datasets"))
    tw_map = {0: "negative", 1: "positive", 2: "neutral"}
    idx = rng.choice(len(tw), min(sample, len(tw)), replace=False)
    sets["twitter_validation"] = ([tw[int(i)]["text"] for i in idx], [tw_map[tw[int(i)]["label"]] for i in idx])
    fpb = load_dataset("warwickai/financial_phrasebank_mirror", split="train", cache_dir=str(CACHE / "datasets"))
    fpb_map = {0: "negative", 1: "neutral", 2: "positive"}
    idx = rng.choice(len(fpb), min(sample, len(fpb)), replace=False)
    sets["phrasebank"] = ([fpb[int(i)]["sentence"] for i in idx], [fpb_map[fpb[int(i)]["label"]] for i in idx])
    return sets


def load(name: str, override: dict | None):
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        BertForSequenceClassification,
        BertTokenizer,
    )

    if name == "yiyanghkust/finbert-tone":
        # Its config predates `model_type`, so the Auto classes can't read it.
        tok = BertTokenizer.from_pretrained(name, cache_dir=CACHE)
        model = BertForSequenceClassification.from_pretrained(name, cache_dir=CACHE)
    else:
        tok = AutoTokenizer.from_pretrained(name, cache_dir=CACHE)
        model = AutoModelForSequenceClassification.from_pretrained(name, cache_dir=CACHE)
    id2label = override or {int(k): v for k, v in model.config.id2label.items()}
    id2label = {k: NORMALISE.get(v.lower(), v.lower()) for k, v in id2label.items()}
    assert set(id2label.values()) == set(LABELS), (name, id2label)
    return tok, model.eval(), id2label


def predict(tok, model, id2label, texts: list[str]) -> tuple[list[str], float]:
    out, began = [], time.perf_counter()
    with torch.no_grad():
        for s in range(0, len(texts), 32):
            enc = tok(texts[s : s + 32], padding=True, truncation=True, max_length=256, return_tensors="pt")
            logits = model(**enc).logits
            out.extend(id2label[int(i)] for i in logits.argmax(-1))
    return out, len(texts) / (time.perf_counter() - began)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=1000, help="rows per public dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    sets = datasets_for(args.sample, args.seed)
    results = {}
    for name, (desc, override, saw_fpb) in MODELS.items():
        print(f"\n{name}", flush=True)
        tok, model, id2label = load(name, override)
        entry = {
            "description": desc,
            "parameters_millions": round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
            "trained_on_phrasebank": saw_fpb,
            "sets": {},
        }
        for set_name, (texts, gold) in sets.items():
            pred, speed = predict(tok, model, id2label, texts)
            rep = classification_report(gold, pred, labels=LABELS, output_dict=True, zero_division=0)
            entry["sets"][set_name] = {
                "n": len(gold),
                "accuracy": accuracy_score(gold, pred),
                "macro_f1": f1_score(gold, pred, labels=LABELS, average="macro", zero_division=0),
                "macro_precision": rep["macro avg"]["precision"],
                "macro_recall": rep["macro avg"]["recall"],
                "weighted_f1": rep["weighted avg"]["f1-score"],
                "f1_per_class": {k: rep[k]["f1-score"] for k in LABELS},
                "precision_per_class": {k: rep[k]["precision"] for k in LABELS},
                "recall_per_class": {k: rep[k]["recall"] for k in LABELS},
                "support_per_class": {k: int(rep[k]["support"]) for k in LABELS},
                # rows: true label, columns: predicted, both in LABELS order
                "confusion_matrix": confusion_matrix(gold, pred, labels=LABELS).tolist(),
                "texts_per_second": round(speed, 1),
            }
            if set_name == "realistic_headlines":
                entry["sets"][set_name]["misclassified"] = [
                    {"text": t, "expected": g, "predicted": p} for t, g, p in zip(texts, gold, pred, strict=True) if g != p
                ]
            s = entry["sets"][set_name]
            print(f"  {set_name:20} acc {s['accuracy']:.1%}  macro-F1 {s['macro_f1']:.3f}  {s['texts_per_second']:.0f} texts/s", flush=True)
        results[name] = entry
        del model, tok

    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sample_per_public_set": args.sample,
        "seed": args.seed,
        "torch_threads": args.threads,
        "note": "phrasebank scores are inflated for models trained on it (trained_on_phrasebank)",
        "models": results,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {OUT / 'metrics.json'}")


if __name__ == "__main__":
    main()
