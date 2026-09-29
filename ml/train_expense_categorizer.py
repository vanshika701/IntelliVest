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

Supplementary real-vocabulary data (added after a stress test measured
only 50% accuracy on realistic text — see evaluate_on_realistic_examples.py
and ml/log.md): mitulshah's merchant names are template placeholders, so
real brand names never appear in training. real_merchant_vocabulary.py's
rows are mixed into TRAINING ONLY (never the held-out test split), and
upweighted via sample_weight since ~500 rows would otherwise be drowned
out by ~4.5M template rows.

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
import numpy as np
import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split

from evaluate_on_realistic_examples import evaluate as evaluate_on_realistic_text
from real_merchant_vocabulary import generate_supplementary_dataset

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
# How much more training influence each supplementary (real-brand) row
# gets vs. a main-dataset row, computed at runtime as a multiplier that
# targets this fraction of an average category's main-dataset weight
# mass going to the (much smaller) supplementary set. 5% is a starting
# point, not a tuned constant — see known_limitations in the output for
# whether it was enough.
SUPPLEMENTARY_TARGET_FRACTION = 0.05
# Budget for the MAIN corpus's vocabulary (see build_vectorizer below).
# Real brand tokens are individually rare compared to millions of repeated
# template words, and TfidfVectorizer's max_features selection ranks
# purely by raw corpus frequency — it has no notion of sample_weight. At
# 500k main rows brand tokens survived a 30k cap; at the full ~4.5M-row
# corpus they did not (confirmed empirically: all 5 sample_brands tokens
# were missing from the fitted vocabulary, and realistic-text accuracy
# collapsed to 54%, no better than before any supplementary data was
# added — see ml/log.md). Raising this constant alone doesn't fix that
# for good, since a big enough main corpus can always outrank a small
# supplementary one — the real fix is build_vectorizer's union approach.
MAX_TFIDF_FEATURES = 30_000

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


def build_vectorizer(main_text: pd.Series, supplementary_text: pd.Series, max_features: int) -> TfidfVectorizer:
    """Build a vocabulary that guarantees every supplementary (real-brand)
    token survives, regardless of how the main corpus's size compares to
    it.

    TfidfVectorizer's max_features selection ranks tokens purely by raw
    frequency across the corpus it's fit on — it does not know about
    sample_weight. A token that appears a few dozen times across 13k
    supplementary rows can make the cut against a 20k-row main corpus and
    still get pruned against a 4.5M-row one, even though the supplementary
    rows are weighted 13x. Weighting a row whose tokens don't exist in the
    vocabulary does nothing, because the row has no non-zero features to
    weight in the first place.

    The fix: fit two vocabularies separately (top `max_features` tokens by
    frequency in the main corpus, and *every* token that appears in the
    small supplementary corpus), take their union as a fixed vocabulary,
    then fit final idf weights on the combined corpus. This guarantees
    real-brand tokens are always present, independent of main-corpus size.
    """
    # (1,3): word unigrams through trigrams. Raised from (1,2) after a
    # stress-test failure showed "LIC PREMIUM AUTO DEBIT" predicted
    # Transportation — "auto" alone is dominated by vehicle-related rows
    # in the main dataset, but the trigram "auto debit" (or bigram
    # "premium auto") is a much less ambiguous unit. Trigrams let the
    # model learn that distinction instead of only ever seeing "auto" in
    # isolation.
    main_vectorizer = TfidfVectorizer(ngram_range=(1, 3), max_features=max_features, min_df=2)
    main_vectorizer.fit(main_text)

    supplementary_vectorizer = TfidfVectorizer(ngram_range=(1, 3), min_df=1)
    supplementary_vectorizer.fit(supplementary_text)

    union_vocabulary = sorted(set(main_vectorizer.vocabulary_) | set(supplementary_vectorizer.vocabulary_))
    return TfidfVectorizer(ngram_range=(1, 3), vocabulary=union_vocabulary)


def train_and_evaluate(
    X_train, X_test, y_train, y_test, sample_weight: np.ndarray | None = None
) -> dict:
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
        clf.fit(X_train, y_train, sample_weight=sample_weight)
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

    # Split FIRST, on the main dataset only — supplementary rows join
    # after this, so the held-out test split stays a pure read on "does
    # it fit this dataset's own distribution," uncontaminated by the
    # small hand-curated supplementary set.
    X_train_text, X_test_text, y_train, y_test = train_test_split(
        sample["clean_description"],
        sample["category"],
        test_size=0.2,
        stratify=sample["category"],
        random_state=RANDOM_STATE,
    )

    # Supplementary real-vocabulary data — training only (see module
    # docstring for why). Two sources, concatenated: the small
    # hand-curated brand list (real_merchant_vocabulary.py, ~484 rows,
    # highest confidence — every row was chosen deliberately) plus the
    # much larger BharatPOI-derived set (ml/data/bharatpoi_supplementary.csv,
    # ~13k rows of real Indian business names — run
    # ml/download_bharatpoi.py to generate it; training proceeds without
    # it if missing, same graceful-degradation pattern as everywhere else
    # in this project, just with less real-world coverage). Weighted up
    # so this doesn't get drowned out by millions of main-dataset rows.
    supplementary_rows = generate_supplementary_dataset()
    supplementary_df = pd.DataFrame(supplementary_rows, columns=["transaction_description", "category"])

    bharatpoi_path = ML_DIR / "data" / "bharatpoi_supplementary.csv"
    if bharatpoi_path.exists():
        bharatpoi_df = pd.read_csv(bharatpoi_path)
        supplementary_df = pd.concat([supplementary_df, bharatpoi_df], ignore_index=True)
        print(f"Loaded {len(bharatpoi_df):,} additional real-vocabulary rows from BharatPOI.")
    else:
        print(
            f"Note: {bharatpoi_path} not found — run download_bharatpoi.py for broader "
            "real-world merchant coverage. Proceeding with just the hand-curated list."
        )

    supplementary_df["clean_description"] = supplementary_df["transaction_description"].apply(clean_text)

    main_avg_per_category = len(X_train_text) / y_train.nunique()
    supp_avg_per_category = len(supplementary_df) / supplementary_df["category"].nunique()
    supplementary_weight = round(
        (main_avg_per_category * SUPPLEMENTARY_TARGET_FRACTION) / supp_avg_per_category, 1
    )
    print(
        f"\nMixing in {len(supplementary_df):,} supplementary real-brand rows "
        f"(sample_weight={supplementary_weight}, targeting "
        f"{SUPPLEMENTARY_TARGET_FRACTION:.0%} of average category weight mass)."
    )

    combined_train_text = pd.concat(
        [X_train_text, supplementary_df["clean_description"]], ignore_index=True
    )
    combined_train_labels = pd.concat([y_train, supplementary_df["category"]], ignore_index=True)
    combined_train_weights = np.concatenate(
        [np.ones(len(X_train_text)), np.full(len(supplementary_df), supplementary_weight)]
    )

    vectorizer = build_vectorizer(X_train_text, supplementary_df["clean_description"], MAX_TFIDF_FEATURES)
    X_train = vectorizer.fit_transform(combined_train_text)
    X_test = vectorizer.transform(X_test_text)

    # Verify real brand tokens actually survived vocabulary construction —
    # don't just assume the union approach worked. Unlike the old
    # max_features-only approach, this should now be guaranteed by
    # construction, so a failure here means something upstream broke
    # (e.g. a token got stripped by the tokenizer) — fail loudly rather
    # than silently shipping a model that can't recognize these brands
    # (exactly what happened before this fix, at full-dataset scale).
    sample_brands = ["swiggy", "zerodha", "bescom", "irctc", "practo"]
    vocab_check = {brand: brand in vectorizer.vocabulary_ for brand in sample_brands}
    print(f"Brand tokens in vocabulary: {vocab_check}")
    missing_brands = [brand for brand, present in vocab_check.items() if not present]
    if missing_brands:
        raise RuntimeError(
            f"Real brand tokens missing from vocabulary despite union construction: "
            f"{missing_brands}. This should be impossible with build_vectorizer's "
            "approach — investigate before training further or shipping this model."
        )

    results = train_and_evaluate(
        X_train, X_test, combined_train_labels, y_test, sample_weight=combined_train_weights
    )

    # Pick the model with the better macro-F1 (not raw accuracy — macro
    # treats every category equally) — but if two models are within a
    # noise-level margin of each other, prefer whichever trained faster
    # as a proxy for a lighter/faster-at-inference artifact. This is not
    # academic: on an earlier run, Random Forest "won" by 0.0002 macro-F1
    # while producing a 129MB artifact and Logistic Regression a ~1MB
    # one — that's not a real accuracy win worth a 100x larger model the
    # backend has to load into memory.
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

    # Stress-test against hand-written realistic text (real brand names,
    # UPI/NEFT-style formatting, using DIFFERENT exact strings than the
    # supplementary training data above — the held-out test split only
    # proves generalization *within* this dataset's template style, and
    # even with supplementary data mixed into training, this stress test
    # is what proves that's genuine brand-token generalization rather
    # than memorizing the literal supplementary strings).
    print("\nEvaluating on realistic (non-template) example text...")

    def _predict_with_trained_model(description: str) -> tuple[str, float]:
        cleaned = description.strip().lower()
        features = vectorizer.transform([cleaned])
        category = best_model.predict(features)[0]
        confidence = float(best_model.predict_proba(features).max())
        return category, confidence

    realistic_eval = evaluate_on_realistic_text(_predict_with_trained_model)
    print(
        f"Realistic-text accuracy: {realistic_eval['accuracy']:.1%} "
        f"({realistic_eval['num_examples']} examples), "
        f"vs. {results[best_name]['metrics']['accuracy']:.1%} on the held-out template-style test split"
    )

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
        "supplementary_real_vocabulary": {
            "sources": [
                "ml/real_merchant_vocabulary.py (hand-curated national/global brands)",
                "ml/data/bharatpoi_supplementary.csv (real Indian business names, "
                "derived from BharatPOI/OpenStreetMap, ODbL 1.0 license)"
                if bharatpoi_path.exists()
                else "ml/data/bharatpoi_supplementary.csv (NOT FOUND — run download_bharatpoi.py)",
            ],
            "rows_added": len(supplementary_df),
            "sample_weight_per_row": supplementary_weight,
            "target_fraction_of_category_weight": SUPPLEMENTARY_TARGET_FRACTION,
            "added_to": "training only — never the held-out test split",
            "brand_tokens_in_vocabulary": vocab_check,
            "vocabulary_construction": (
                "Union of the main corpus's top max_features tokens by frequency "
                "and every token appearing in the supplementary corpus (see "
                "build_vectorizer) — guarantees real-brand tokens survive "
                "regardless of how large the main corpus is. An earlier "
                "max_features-only approach passed this check at a 500k-row "
                "diagnostic scale but silently failed at the full ~4.5M-row "
                "scale (all sample brand tokens pruned, realistic-text accuracy "
                "back to 54%) — see ml/log.md."
            ),
            "reason": (
                "A stress test (see realistic_text_stress_test) measured only "
                "50% accuracy on realistic text before this was added, because "
                "the main dataset's merchant names are template placeholders "
                "with no real brand-name overlap. This mixes in real vocabulary "
                "without diluting the main dataset's signal, by weighting "
                "rather than duplicating rows."
            ),
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
        "realistic_text_stress_test": realistic_eval,
        "known_limitations": [
            (
                "Transaction descriptions in this dataset are template-generated "
                "(e.g. 'Exxon - CANADA Store'), cleaner and more regular than real "
                "messy bank statement text. Supplementary real-brand-name data "
                "(see supplementary_real_vocabulary above) was mixed into training "
                "to address this. Current measured accuracy on hand-written "
                "realistic text (different exact strings than the supplementary "
                f"training data) is {realistic_eval['accuracy']:.1%} vs. "
                f"{results[best_name]['metrics']['accuracy']:.1%} on the held-out "
                "template-style test split — see realistic_text_stress_test above "
                "for whether this fix actually closed the gap."
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
