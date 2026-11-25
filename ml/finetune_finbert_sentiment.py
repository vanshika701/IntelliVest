"""Offline fine-tuning script for the news-sentiment model (Phase 5).

Run manually (same "training happens offline, the trained artifact is
saved and loaded by the backend service layer" pattern every ML phase in
this project follows):

    cd ml
    python3 finetune_finbert_sentiment.py

Paper/dataset grounding:
- Base model: ProsusAI/finbert (Araci, 2019) — already usable as-is via
  backend/app/services/sentiment_service.py with zero training (that's
  the default this project ships with, currently, for the reason
  documented in the "Domain-shift finding" section below). This script
  is the *optional* upgrade: fine-tuning FinBERT further on public
  datasets, and measuring what a lightweight compression technique does
  to it, per:
    "Towards Efficient FinBERT via Quantization and Coreset for
    Financial Sentiment Analysis" — FinNLP workshop, EMNLP-2025.
    https://aclanthology.org/2025.finnlp-2.6.pdf

Datasets (TWO, combined — see "Domain-shift finding" for why one wasn't
enough):
1. zeroshot/twitter-financial-news-sentiment (Hugging Face, MIT license,
   no gating) — 9,543 train / 2,388 validation TWEETS, 3 classes
   (0=Bearish, 1=Bullish, 2=Neutral). The paper's own reported full
   fine-tune baseline on this dataset alone: 83.4% accuracy / 0.833
   macro-F1.
2. Financial PhraseBank (Malo et al., 2014) via the
   warwickai/financial_phrasebank_mirror Hugging Face mirror — 4,846
   sentences from actual financial NEWS/ANALYST REPORTS, 3 classes
   (0=negative, 1=neutral, 2=positive; confirmed empirically against
   known per-class counts and spot-checked sentence content, not
   assumed from the dataset card). The original takala/financial_phrasebank
   repo uses a deprecated Hugging Face "loading script" format the
   installed `datasets` library version no longer supports — this
   mirror hosts the same data in a standard Parquet format. License:
   CC BY-NC-SA 3.0 — non-commercial only; fine for this portfolio
   project, but flagged here so it's never missed later.

Domain-shift finding (2026-09-29, see ml/log.md for the full
investigation): fine-tuning on the Twitter dataset ALONE scored 87.86%
on its own tweet validation split, but measured WORSE than the plain
pretrained checkpoint (73.3% vs. 83.3%) on realistic NEWS HEADLINES —
the actual text this app scores in production (see
news_service.py/sentiment_service.py). Tweets and news headlines share
financial vocabulary but differ structurally, and fine-tuning pulled the
model away from patterns the original FinBERT pretraining had already
learned for the closer, more formal Financial PhraseBank style. This
script now combines BOTH datasets — tweets for informal/social coverage,
Financial PhraseBank for the news/analyst-report style that actually
matches production — to fix that gap, rather than swapping one narrow
dataset for another. Labels are unified onto FinBERT's OWN
positive/negative/neutral scheme (not the Twitter dataset's
Bearish/Bullish/Neutral), so this fine-tuned model's output vocabulary
now matches the pretrained checkpoint's exactly — one less limitation
than the previous single-dataset version.

The realistic-news-headline stress test
(ml/evaluate_sentiment_on_realistic_news.py) that caught the original
problem now runs automatically at the end of this script, the same
"verify against realistic text every run" pattern Phase 3 established —
metrics.json's `realistic_news_stress_test` field is always current,
not a one-off manual check.

What this script does NOT replicate from the paper, and why (documented
here rather than silently glossed over, same honesty standard as Phase
3's DFTSen comparison):
- The paper's coreset selection (shrinking the training set before
  fine-tuning) matters most when the training set is large enough that
  training cost itself is the bottleneck — that was true of Phase 3's
  4.5M-row dataset, not this combined ~13k-row one. Skipped as
  unnecessary here, not because it's hard.
- The paper explores exotic bit-widths (down to 1-bit) via research-only
  quantization code. This script applies PyTorch's standard, widely-used
  *dynamic int8 quantization* (torch.ao.quantization.quantize_dynamic) —
  a real, reproducible technique anyone can run, not a literal
  replication of the paper's specific compression pipeline.

Outputs (to ml/models/sentiment_finbert/):
- config.json / model.safetensors / tokenizer files — the fine-tuned
  (full-precision) model, in standard Hugging Face format, loadable
  directly by transformers.pipeline().
- metrics.json — accuracy/F1 for both the full-precision and quantized
  variants (per dataset source AND combined), the realistic-news stress
  test result, dataset provenance, paper citation, and known limitations.

Whether this becomes the DEFAULT model sentiment_service.py loads
depends on what the realistic-news stress test says here — see that
module's docstring. Not assumed in advance.
"""

import json
import time
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset, load_dataset
from evaluate_sentiment_on_realistic_news import _LABEL_EQUIVALENCE
from evaluate_sentiment_on_realistic_news import evaluate as evaluate_on_realistic_news
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

ML_DIR = Path(__file__).parent
MODEL_DIR = ML_DIR / "models" / "sentiment_finbert"
BASE_MODEL = "ProsusAI/finbert"
TWITTER_DATASET_NAME = "zeroshot/twitter-financial-news-sentiment"
PHRASEBANK_DATASET_NAME = "warwickai/financial_phrasebank_mirror"
RANDOM_STATE = 42
NUM_EPOCHS = 3
# Standard BERT fine-tuning learning rate — not tuned further, since the
# paper's own reported number is what we're comparing against, not
# chasing a higher one.
LEARNING_RATE = 2e-5
BATCH_SIZE = 16
# Pretrained FinBERT on the 30-headline stress test (see ml/log.md). Kept
# exact: a rounded 0.833 would make a 25/30 tie count as an improvement.
PRETRAINED_BASELINE_ACCURACY = 25 / 30

# FinBERT's OWN label scheme (confirmed via AutoConfig.from_pretrained,
# not assumed) — reusing it means the classification head we initialize
# from is semantically consistent with these label ids, not just
# numerically compatible.
ID2LABEL = {0: "positive", 1: "negative", 2: "neutral"}
LABEL2ID = {v: k for k, v in ID2LABEL.items()}

# Twitter dataset's own labels (0=Bearish, 1=Bullish, 2=Neutral) mapped
# onto the unified positive/negative/neutral scheme above.
_TWITTER_LABEL_MAP = {0: LABEL2ID["negative"], 1: LABEL2ID["positive"], 2: LABEL2ID["neutral"]}
# Financial PhraseBank's own labels (0=negative, 1=neutral, 2=positive —
# confirmed empirically: label 0 sentences describe layoffs/losses,
# label 2 sentences describe growth/profitability, matching the
# well-documented Malo et al. class-count distribution for this exact
# variant: negative=604, neutral=2879, positive=1363).
_PHRASEBANK_LABEL_MAP = {0: LABEL2ID["negative"], 1: LABEL2ID["neutral"], 2: LABEL2ID["positive"]}


def load_twitter_data():
    print(f"Downloading {TWITTER_DATASET_NAME} (public, MIT license, no gating needed)...")
    ds = load_dataset(TWITTER_DATASET_NAME)
    train = ds["train"].map(lambda ex: {"label": _TWITTER_LABEL_MAP[ex["label"]]})
    val = ds["validation"].map(lambda ex: {"label": _TWITTER_LABEL_MAP[ex["label"]]})
    print(f"Twitter: {len(train):,} train / {len(val):,} validation rows.")
    return train, val


def load_phrasebank_data():
    print(
        f"Downloading {PHRASEBANK_DATASET_NAME} (Financial PhraseBank mirror, "
        "CC BY-NC-SA 3.0 — non-commercial use only)..."
    )
    ds = load_dataset(PHRASEBANK_DATASET_NAME)["train"]
    ds = ds.rename_column("sentence", "text")
    ds = ds.map(lambda ex: {"label": _PHRASEBANK_LABEL_MAP[ex["label"]]})
    # No predefined validation split — carve one out ourselves, the same
    # 80/20 stratified split every other phase in this project uses.
    indices = list(range(len(ds)))
    train_idx, val_idx = train_test_split(
        indices, test_size=0.2, stratify=ds["label"], random_state=RANDOM_STATE
    )
    train, val = ds.select(train_idx), ds.select(val_idx)
    print(f"Financial PhraseBank: {len(train):,} train / {len(val):,} validation rows.")
    return train, val


def compute_metrics(eval_pred) -> dict:
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, predictions),
        "macro_f1": f1_score(labels, predictions, average="macro"),
    }


def evaluate_full_report(model, tokenizer, dataset, device: str) -> dict:
    """Run inference in plain batches (not via Trainer) so this same
    function can evaluate both the full-precision model (on device) and
    the quantized model (forced to CPU — PyTorch's dynamic quantization
    backend only supports CPU inference)."""
    model.eval()
    all_preds, all_labels = [], []
    texts = dataset["text"]
    labels = dataset["label"]
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch_texts = texts[i : i + BATCH_SIZE]
            batch_labels = labels[i : i + BATCH_SIZE]
            inputs = tokenizer(
                batch_texts, truncation=True, padding=True, max_length=128, return_tensors="pt"
            ).to(device)
            logits = model(**inputs).logits
            all_preds.extend(logits.argmax(dim=-1).cpu().tolist())
            all_labels.extend(batch_labels)

    report = classification_report(
        all_labels,
        all_preds,
        labels=sorted(ID2LABEL),
        target_names=[ID2LABEL[i] for i in sorted(ID2LABEL)],
        output_dict=True,
        zero_division=0,
    )
    return {
        "accuracy": accuracy_score(all_labels, all_preds),
        "macro_f1": f1_score(all_labels, all_preds, average="macro"),
        "per_category": report,
    }


def main() -> None:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device} (Apple Silicon MPS acceleration)" if device == "mps" else f"Using device: {device}")

    twitter_train, twitter_val = load_twitter_data()
    phrasebank_train, phrasebank_val = load_phrasebank_data()

    combined_train = Dataset.from_dict(
        {
            "text": list(twitter_train["text"]) + list(phrasebank_train["text"]),
            "label": list(twitter_train["label"]) + list(phrasebank_train["label"]),
        }
    )
    combined_val = Dataset.from_dict(
        {
            "text": list(twitter_val["text"]) + list(phrasebank_val["text"]),
            "label": list(twitter_val["label"]) + list(phrasebank_val["label"]),
        }
    )
    print(f"\nCombined: {len(combined_train):,} train / {len(combined_val):,} validation rows.")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=128)

    tokenized_train = combined_train.map(tokenize, batched=True)
    tokenized_val = combined_val.map(tokenize, batched=True)
    tokenized_train = tokenized_train.rename_column("label", "labels")
    tokenized_val = tokenized_val.rename_column("label", "labels")
    tokenized_train.set_format("torch", columns=["input_ids", "attention_mask", "labels"])
    tokenized_val.set_format("torch", columns=["input_ids", "attention_mask", "labels"])

    # num_labels=3 already matches FinBERT's own head shape, and
    # ID2LABEL above reuses FinBERT's own label semantics — this is
    # continued fine-tuning of an already-relevant head, not a fresh
    # random one.
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=3, ignore_mismatched_sizes=True
    )
    model.config.id2label = ID2LABEL
    model.config.label2id = LABEL2ID

    training_args = TrainingArguments(
        output_dir=str(ML_DIR / "_finetune_checkpoints"),
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        logging_steps=50,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=compute_metrics,
    )

    print(
        f"\nFine-tuning {BASE_MODEL} on combined Twitter + Financial PhraseBank "
        f"data ({NUM_EPOCHS} epochs)..."
    )
    start = time.time()
    trainer.train()
    train_seconds = time.time() - start
    print(f"Fine-tuning finished in {train_seconds:.1f}s")

    full_precision_model = trainer.model.to(device)

    combined_report = evaluate_full_report(full_precision_model, tokenizer, combined_val, device)
    twitter_only_report = evaluate_full_report(full_precision_model, tokenizer, twitter_val, device)
    phrasebank_only_report = evaluate_full_report(full_precision_model, tokenizer, phrasebank_val, device)
    print(
        f"\nFull-precision (combined validation): accuracy={combined_report['accuracy']:.4f} "
        f"macro_f1={combined_report['macro_f1']:.4f}"
    )
    print(
        f"  - Twitter-only validation: accuracy={twitter_only_report['accuracy']:.4f} "
        f"macro_f1={twitter_only_report['macro_f1']:.4f}"
    )
    print(
        f"  - Financial PhraseBank-only validation: accuracy={phrasebank_only_report['accuracy']:.4f} "
        f"macro_f1={phrasebank_only_report['macro_f1']:.4f}"
    )

    # The real question: does this actually help the DOMAIN it's used
    # in, not just its own held-out split — see module docstring.
    print("\nEvaluating on realistic (non-training) NEWS HEADLINE text...")

    def predict_finetuned(text: str) -> tuple[str, float]:
        cleaned = text.strip()
        inputs = tokenizer(cleaned, truncation=True, max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            logits = full_precision_model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        pred_id = int(probs.argmax())
        return ID2LABEL[pred_id], float(probs[pred_id])

    realistic_news_eval = evaluate_on_realistic_news(predict_finetuned, _LABEL_EQUIVALENCE)
    print(
        f"Realistic-news-headline accuracy: {realistic_news_eval['accuracy']:.1%} "
        f"({realistic_news_eval['num_examples']} examples), macro_f1={realistic_news_eval['macro_f1']:.4f}"
    )
    print(
        "(For reference: pretrained-only measured 83.3% accuracy / 0.7855 macro-F1 "
        "on this same test — see ml/log.md for that run.)"
    )

    # Dynamic int8 quantization — CPU-only technique (PyTorch's dynamic
    # quantization backend doesn't support MPS/CUDA), applied to a CPU
    # copy so the full-precision model on `device` is untouched. The
    # quantization *engine* is also platform-specific: fbgemm (x86) isn't
    # available on Apple Silicon — only qnnpack is (verified empirically,
    # not assumed).
    print("\nApplying dynamic int8 quantization (measurement only, not the shipped artifact)...")
    if "qnnpack" in torch.backends.quantized.supported_engines:
        torch.backends.quantized.engine = "qnnpack"
    cpu_model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=3)
    cpu_model.load_state_dict(trainer.model.to("cpu").state_dict())
    trainer.model.to(device)  # move back — we still need it for saving below
    quantized_model = torch.ao.quantization.quantize_dynamic(
        cpu_model, {torch.nn.Linear}, dtype=torch.qint8
    )
    quantized_report = evaluate_full_report(quantized_model, tokenizer, combined_val, "cpu")
    print(
        f"Quantized (int8, combined validation): accuracy={quantized_report['accuracy']:.4f} "
        f"macro_f1={quantized_report['macro_f1']:.4f}"
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    trainer.model.to("cpu").save_pretrained(MODEL_DIR)
    tokenizer.save_pretrained(MODEL_DIR)

    full_size_mb = sum(f.stat().st_size for f in MODEL_DIR.glob("*.safetensors")) / (1024 * 1024)
    quantized_size_mb = sum(
        p.numel() * (1 if p.dtype == torch.qint8 else p.element_size())
        for p in quantized_model.state_dict().values()
        if hasattr(p, "numel")
    ) / (1024 * 1024)

    beats_pretrained_on_real_task = realistic_news_eval["accuracy"] > PRETRAINED_BASELINE_ACCURACY

    metrics_out = {
        "base_model": BASE_MODEL,
        "dataset": {
            "sources": [
                f"{TWITTER_DATASET_NAME} (Hugging Face, MIT license) — {len(twitter_train):,} train / {len(twitter_val):,} val tweets",
                (
                    f"{PHRASEBANK_DATASET_NAME} (Financial PhraseBank mirror, CC BY-NC-SA 3.0, "
                    f"non-commercial only) — {len(phrasebank_train):,} train / {len(phrasebank_val):,} val "
                    "news/analyst-report sentences"
                ),
            ],
            "combined_train_rows": len(combined_train),
            "combined_validation_rows": len(combined_val),
            "labels": ID2LABEL,
            "why_two_datasets": (
                "A single-dataset (Twitter-only) fine-tune scored 87.86% on its own "
                "validation split but measured WORSE than the plain pretrained "
                "checkpoint (73.3% vs 83.3%) on realistic news headlines — the actual "
                "production domain. Financial PhraseBank (news/analyst-report style) "
                "was added specifically to close that domain gap. See ml/log.md."
            ),
        },
        "paper_reference": {
            "citation": (
                "Towards Efficient FinBERT via Quantization and Coreset for "
                "Financial Sentiment Analysis, FinNLP workshop, EMNLP-2025"
            ),
            "url": "https://aclanthology.org/2025.finnlp-2.6.pdf",
            "note": (
                "Coreset selection is not replicated (small dataset, not a training-"
                "cost bottleneck). Quantization uses PyTorch's standard dynamic int8 "
                "quantization, not the paper's specific multi-bit scheme."
            ),
        },
        "training": {
            "epochs": NUM_EPOCHS,
            "learning_rate": LEARNING_RATE,
            "batch_size": BATCH_SIZE,
            "device": device,
            "train_seconds": round(train_seconds, 1),
        },
        "models_compared": {
            "full_precision": {
                "combined_validation": {
                    "accuracy": combined_report["accuracy"],
                    "macro_f1": combined_report["macro_f1"],
                    "per_category": combined_report["per_category"],
                },
                "twitter_only_validation": {
                    "accuracy": twitter_only_report["accuracy"],
                    "macro_f1": twitter_only_report["macro_f1"],
                },
                "phrasebank_only_validation": {
                    "accuracy": phrasebank_only_report["accuracy"],
                    "macro_f1": phrasebank_only_report["macro_f1"],
                },
                "size_mb": round(full_size_mb, 2),
            },
            "quantized_int8": {
                "combined_validation": {
                    "accuracy": quantized_report["accuracy"],
                    "macro_f1": quantized_report["macro_f1"],
                },
                "size_mb": round(quantized_size_mb, 2),
            },
        },
        "realistic_news_stress_test": {
            **realistic_news_eval,
            "pretrained_baseline_for_comparison": {
                "accuracy": PRETRAINED_BASELINE_ACCURACY,
                "macro_f1": 0.7855,
                "note": "See ml/log.md — measured on the same 30-headline test.",
            },
            "beats_pretrained_baseline": beats_pretrained_on_real_task,
        },
        "selected_model": "full_precision",
        "selection_reasoning": (
            "The full-precision fine-tuned model is what's shipped (saved to this "
            "directory) because it round-trips through standard Hugging Face "
            "save/load with zero extra glue code; the quantized variant's tradeoff "
            "is measured above for comparison. Whether sentiment_service.py actually "
            "DEFAULTS to this model instead of the pretrained checkpoint depends on "
            "beats_pretrained_baseline above — see backend/app/core/config.py's "
            "sentiment_model setting and ml/log.md for the decision."
        ),
        "known_limitations": [
            (
                "Financial PhraseBank sentences (Malo et al., 2014) are from 2010s-era "
                "financial news, and the mirror used here is a third-party, unofficial "
                "re-hosting (the original takala/financial_phrasebank repo uses a "
                "deprecated Hugging Face loading-script format that current tooling "
                "rejects) — labels were verified empirically against known class "
                "counts and spot-checked sentence content, not just trusted from the "
                "dataset card."
            ),
            "Financial PhraseBank is CC BY-NC-SA 3.0 — non-commercial use only.",
        ],
    }
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics_out, f, indent=2, default=str)

    print(f"\nSaved fine-tuned model and metrics.json to {MODEL_DIR}")
    print(
        f"\n{'BEATS' if beats_pretrained_on_real_task else 'DOES NOT beat'} the "
        "pretrained checkpoint's 83.3% accuracy on realistic news headlines."
    )


if __name__ == "__main__":
    main()
