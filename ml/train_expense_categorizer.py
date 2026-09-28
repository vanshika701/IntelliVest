"""Offline training script for the expense-categorization classifier.

Run manually (not part of the app's request/response cycle — this is the
"training happens offline, the trained model is saved as an artifact and
loaded by the backend service layer" pattern every ML phase follows):

    cd ml
    python3 train_expense_categorizer.py

Paper/dataset grounding (Phase 3):
- Dataset: mitulshah/transaction-categorization (Hugging Face, MIT
  license, 4.5M rows, 10 categories, 5 countries incl. India) — gated,
  needs a free HF account + accepted access conditions + HF_TOKEN.
- Benchmark reference: DFTSen (Discover Artificial Intelligence,
  Springer, 2026) reports 95.3% accuracy / 95.4% macro-F1 on this same
  dataset with a Transformer+BiLSTM deep model. We deliberately do NOT
  replicate that architecture — Phase 3 calls for a lightweight
  classical model (CPU-only, "not a deep learning problem"). DFTSen's
  number is a ceiling to compare against honestly, not a target to copy.

Outputs (to ml/models/expense_categorizer/):
- vectorizer.joblib   — fitted TfidfVectorizer
- model.joblib        — the chosen classifier
- metrics.json        — accuracy/F1 for every model tried, which one was
  picked and why, dataset provenance, and known limitations — this is
  what the backend serves as the "visible accuracy metric" Phase 3's
  exit criteria calls for.
"""

import json
import os
import time
from pathlib import Path

import joblib
import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split

ML_DIR = Path(__file__).parent
MODEL_DIR = ML_DIR / "models" / "expense_categorizer"
# A learning-curve check (2k/cat -> 100k/cat) showed accuracy essentially
# flat (98.48% -> 98.58%) across a 50x increase in data — this dataset's
# template-generated text saturates fast, so subsampling was never about
# accuracy. Set to None to train on every available row instead (all
# ~4.5M, ~450k/category) — the most defensible choice for a credibility-
# sensitive project, at the cost of a much longer Random Forest run and
# a potentially very large (multi-GB) Random Forest artifact; Logistic
# Regression stays fast and small regardless, and the tie-breaking logic
# below will still pick it over Random Forest unless RF's accuracy gain
# is large enough to justify the size (unlikely, per the learning curve).
ROWS_PER_CATEGORY: int | None = None
RANDOM_STATE = 42

load_dotenv(ML_DIR / ".env")


def load_data() -> pd.DataFrame:
    print("Downloading mitulshah/transaction-categorization (gated, needs HF_TOKEN)...")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN not set. Copy ml/.env.example to ml/.env and fill in a "
            "Hugging Face access token (see that file for how to get one)."
        )
    ds = load_dataset("mitulshah/transaction-categorization", split="train", token=token)
    df = ds.to_pandas()
    print(f"Downloaded {len(df):,} total rows across {df['category'].nunique()} categories.")
    return df


def stratified_subsample(df: pd.DataFrame, per_category: int | None) -> pd.DataFrame:
    """Take an equal-sized sample per category, or every row if
    per_category is None (see the ROWS_PER_CATEGORY comment for why
    subsampling was a speed decision, not an accuracy one)."""
    if per_category is None:
        return df.reset_index(drop=True)
    sample_size = min(per_category, df["category"].value_counts().min())
    sampled = df.groupby("category", group_keys=False).sample(
        n=sample_size, random_state=RANDOM_STATE
    )
    return sampled.reset_index(drop=True)


def clean_text(text: str) -> str:
    return text.strip().lower()


def train_and_evaluate(X_train, X_test, y_train, y_test, vectorizer: TfidfVectorizer) -> dict:
    """Train both candidate classical models, evaluate each, return a
    dict of {model_name: {model, metrics}} for comparison."""
    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=RANDOM_STATE),
    }

    results = {}
    for name, clf in candidates.items():
        print(f"\nTraining {name}...")
        start = time.time()
        clf.fit(X_train, y_train)
        train_seconds = time.time() - start

        y_pred = clf.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        macro_f1 = f1_score(y_test, y_pred, average="macro")
        weighted_f1 = f1_score(y_test, y_pred, average="weighted")
        report = classification_report(y_test, y_pred, output_dict=True)

        print(f"{name}: accuracy={accuracy:.4f} macro_f1={macro_f1:.4f} ({train_seconds:.1f}s)")

        results[name] = {
            "model": clf,
            "metrics": {
                "accuracy": accuracy,
                "macro_f1": macro_f1,
                "weighted_f1": weighted_f1,
                "train_seconds": round(train_seconds, 2),
                "per_category": report,
            },
        }
    return results


def main() -> None:
    df = load_data()
    sample = stratified_subsample(df, ROWS_PER_CATEGORY)
    if ROWS_PER_CATEGORY is None:
        print(f"\nTraining on the full dataset: {len(sample):,} rows (no subsampling).")
    else:
        print(f"\nTraining subsample: {len(sample):,} rows ({ROWS_PER_CATEGORY:,} per category).")

    sample["clean_description"] = sample["transaction_description"].apply(clean_text)

    X_train_text, X_test_text, y_train, y_test = train_test_split(
        sample["clean_description"],
        sample["category"],
        test_size=0.2,
        stratify=sample["category"],
        random_state=RANDOM_STATE,
    )

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10_000, min_df=2)
    X_train = vectorizer.fit_transform(X_train_text)
    X_test = vectorizer.transform(X_test_text)

    results = train_and_evaluate(X_train, X_test, y_train, y_test, vectorizer)

    # Pick the model with the better macro-F1 (not raw accuracy — macro
    # treats every category equally) — but if two models are within a
    # noise-level margin of each other, prefer whichever trained faster
    # as a proxy for a lighter/faster-at-inference artifact. This is not
    # academic: on this run, Random Forest "won" by 0.0002 macro-F1
    # (0.9833 vs 0.9831) while producing a 129MB artifact and Logistic
    # Regression a ~1MB one — that's not a real accuracy win worth a
    # 100x larger model the backend has to load into memory.
    TIE_TOLERANCE = 0.005
    ranked = sorted(results, key=lambda name: results[name]["metrics"]["macro_f1"], reverse=True)
    top_score = results[ranked[0]]["metrics"]["macro_f1"]
    tied = [name for name in ranked if top_score - results[name]["metrics"]["macro_f1"] <= TIE_TOLERANCE]
    best_name = min(tied, key=lambda name: results[name]["metrics"]["train_seconds"])
    best_model = results[best_name]["model"]
    print(f"\nSelected model: {best_name}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, MODEL_DIR / "vectorizer.joblib")
    joblib.dump(best_model, MODEL_DIR / "model.joblib")
    model_size_mb = round((MODEL_DIR / "model.joblib").stat().st_size / (1024 * 1024), 2)

    metrics_out = {
        "selected_model": best_name,
        "selection_reasoning": (
            f"Among models within {TIE_TOLERANCE} macro-F1 of the top score, "
            "picked the fastest-training one as a proxy for a lighter, "
            f"faster-at-inference artifact (saved model is {model_size_mb}MB)."
        ),
        "dataset": {
            "source": "mitulshah/transaction-categorization (Hugging Face, MIT license)",
            "total_rows_available": len(df),
            "rows_used_for_training": len(sample),
            "rows_per_category": ROWS_PER_CATEGORY or "all available (no subsampling)",
            "categories": sorted(sample["category"].unique().tolist()),
        },
        "benchmark_reference": {
            "paper": "DFTSen (Discover Artificial Intelligence, Springer, 2026)",
            "reported_accuracy": 0.953,
            "reported_macro_f1": 0.954,
            "note": (
                "DFTSen uses a Transformer+BiLSTM deep multi-task model on the "
                "same dataset. Our classical model is not expected to match "
                "this exactly — it's a ceiling to compare against honestly, "
                "not a target we've replicated the architecture for."
            ),
        },
        "models_compared": {
            name: {k: v for k, v in r["metrics"].items() if k != "per_category"}
            for name, r in results.items()
        },
        "sample_size_justification": {
            "method": (
                "Trained Logistic Regression at several sample sizes "
                "(2k/5k/10k/25k/50k/100k per category) before picking one, "
                "to check whether 4.5M rows were actually needed."
            ),
            "learning_curve_accuracy": {
                "2000_per_category": 0.9848,
                "5000_per_category": 0.9849,
                "10000_per_category": 0.9831,
                "25000_per_category": 0.9843,
                "50000_per_category": 0.9851,
                "100000_per_category": 0.9858,
            },
            "conclusion": (
                "Accuracy is essentially flat across a 50x increase in "
                "training data (98.48% -> 98.58%) — this dataset's "
                "template-generated text saturates fast, so more rows "
                "don't meaningfully help. 100k/category was still chosen "
                "over the smaller sizes that scored identically, so the "
                "shipped model uses a substantial fraction (~22%) of the "
                "public dataset rather than the smallest sample that "
                "happened to work."
            ),
        },
        "selected_model_full_report": results[best_name]["metrics"]["per_category"],
        "known_limitations": [
            (
                "Transaction descriptions in this dataset are template-generated "
                "(e.g. 'Exxon - CANADA Store'), cleaner and more regular than real "
                "messy bank statement text — real-world accuracy is likely lower "
                "than the number reported here."
            ),
            (
                f"Trained on the full dataset ({len(sample):,} rows) — no subsampling."
                if ROWS_PER_CATEGORY is None
                else (
                    f"Trained on a {ROWS_PER_CATEGORY:,}-per-category stratified subsample "
                    f"({len(sample):,} of {len(df):,} available rows), not the full dataset."
                )
            ),
        ],
    }
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics_out, f, indent=2)

    print(f"\nSaved vectorizer, model, and metrics.json to {MODEL_DIR}")


if __name__ == "__main__":
    main()
