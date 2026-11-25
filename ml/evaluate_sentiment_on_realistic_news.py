"""Domain-shift stress test for the news-sentiment model (Phase 5).

The first fine-tuned model (ml/finetune_finbert_sentiment.py) was trained
on zeroshot/twitter-financial-news-sentiment — short, informal TWEETS. But
production actually scores NEWS ARTICLE headlines/descriptions from
RSS feeds (backend/app/services/news_service.py) — longer, more formal
text, structurally different from tweets. This is exactly the kind of
train/production distribution mismatch that hurt Phase 3 before its
realistic-text stress test caught it (see ml/log.md) — so it gets
checked here empirically instead of assumed away.

Hand-written, realistic financial news headlines (not tweets, not from
either training dataset), labeled by hand. Compares the model the
app serves against the local fine-tuned model on the SAME examples,
since the real question isn't "how good is the fine-tuned model in
isolation" (already measured on its own tweet validation split) but
"did fine-tuning on tweets help or hurt for the news-headline domain it
actually runs on in production."

Run directly:
    cd ml && python3 evaluate_sentiment_on_realistic_news.py
"""

import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
FINETUNED_MODEL_DIR = ML_DIR / "models" / "sentiment_finbert"

sys.path.insert(0, str(ML_DIR.parent / "backend"))

# Bearish/Bullish/Neutral (fine-tuned model) <-> positive/negative/neutral
# (pretrained model) — a reasonable, honest mapping for stock-market
# sentiment purposes: Bearish=negative, Bullish=positive, Neutral=neutral.
_LABEL_EQUIVALENCE = {
    "Bearish": "negative",
    "Bullish": "positive",
    "Neutral": "neutral",
    "negative": "negative",
    "positive": "positive",
    "neutral": "neutral",
}

# Realistic financial news headlines — not tweets, not from either
# training dataset. Deliberately includes headlines styled like the ones
# actually seen in production (Sensex/Nifty movement reports, earnings,
# M&A, macro news) at varying difficulty, including some genuinely
# ambiguous ones (mixed/neutral calls), same as Phase 3's stress test
# design — not cherry-picked to be easy.
REALISTIC_NEWS_HEADLINES = [
    ("Sensex jumps 500 points, Nifty tops 24,000 as IT stocks rally", "positive"),
    ("Sensex tumbles 800 points on weak global cues, Nifty below 23,000", "negative"),
    ("Nifty ends flat as gains in banking offset losses in auto stocks", "neutral"),
    ("Reliance Industries posts record quarterly profit, beats estimates", "positive"),
    ("Infosys shares slide 6% after cutting full-year revenue guidance", "negative"),
    ("TCS board approves ₹18,000 crore share buyback", "positive"),
    ("Wipro shares hit 52-week low amid weak deal pipeline concerns", "negative"),
    ("RBI keeps repo rate unchanged at 6.5% for sixth consecutive time", "neutral"),
    ("Adani Group stocks crash after short-seller report alleges fraud", "negative"),
    ("HDFC Bank reports 20% jump in net profit, asset quality improves", "positive"),
    ("Government announces new PLI scheme to boost electronics manufacturing", "positive"),
    ("Crude oil prices surge past $95 a barrel on Middle East tensions", "negative"),
    ("Maruti Suzuki recalls 100,000 vehicles over airbag defect", "negative"),
    ("Zomato shares soar 15% after first-ever quarterly profit", "positive"),
    ("Paytm faces regulatory scrutiny as RBI restricts new deposits", "negative"),
    ("Tata Motors unveils new electric SUV, shares rise 4%", "positive"),
    ("Markets to remain shut Monday on account of a public holiday", "neutral"),
    ("Foreign investors pull out ₹12,000 crore from Indian equities in September", "negative"),
    ("Gold prices hit all-time high as investors seek safe-haven assets", "neutral"),
    ("Startup layoffs continue as funding winter drags into third year", "negative"),
    ("SEBI proposes new disclosure norms for related-party transactions", "neutral"),
    ("Bajaj Finance shares rally after strong loan growth in Q2", "positive"),
    ("Vodafone Idea shares plunge on fears of further stake dilution", "negative"),
    ("IT sector outlook remains uncertain amid client budget cuts in the US", "negative"),
    ("India's GDP growth seen at 7.2% for the fiscal year, says report", "positive"),
    ("Cement stocks under pressure as demand remains sluggish", "negative"),
    ("L&T wins ₹5,000 crore order for infrastructure project in Middle East", "positive"),
    ("Rupee weakens past 84 against the dollar on strong greenback demand", "negative"),
    ("Quarterly results season kicks off next week with IT majors reporting first", "neutral"),
    ("ITC shares gain after strong festive season demand for cigarettes and FMCG", "positive"),
]


def evaluate(predict_fn, label_map: dict) -> dict:
    """label_map normalizes a model's raw output label to
    positive/negative/neutral for fair comparison."""
    from sklearn.metrics import classification_report

    results = []
    for text, expected in REALISTIC_NEWS_HEADLINES:
        label, confidence = predict_fn(text)
        normalized = label_map.get(label, label)
        results.append((text, expected, normalized, confidence))

    y_true = [r[1] for r in results]
    y_pred = [r[2] for r in results]
    report = classification_report(
        y_true, y_pred, labels=["negative", "neutral", "positive"], output_dict=True, zero_division=0
    )
    accuracy = sum(1 for _, e, p, _ in results if e == p) / len(results)
    misclassified = [
        {"text": t, "expected": e, "predicted": p, "confidence": c}
        for t, e, p, c in results
        if e != p
    ]
    return {
        "num_examples": len(results),
        "accuracy": accuracy,
        "macro_f1": report["macro avg"]["f1-score"],
        "misclassified": misclassified,
    }


def predict_production(text: str) -> tuple[str, float]:
    """Score one headline through the backend's own entry point, so this
    measures what the app actually serves (settings.sentiment_model).

    score_texts() silently falls back to a keyword lexicon when FinBERT
    can't be loaded. That is fine for the app, but would put a lexicon
    score under a model's name here, so it is treated as an error.
    """
    from app.services.sentiment_service import score_texts

    probabilities, engine = score_texts([text])
    if engine == "lexicon":
        raise RuntimeError("Sentiment model could not be loaded (score_texts fell back to the lexicon).")
    label = max(probabilities[0], key=probabilities[0].get)
    return label, probabilities[0][label]


def load_finetuned_predictor():
    """Return a predict function for the local fine-tuned model, or None
    if its weights (gitignored) aren't on this machine."""
    if not (FINETUNED_MODEL_DIR / "model.safetensors").exists():
        return None

    from transformers import pipeline

    classifier = pipeline("text-classification", model=str(FINETUNED_MODEL_DIR))

    def predict(text: str) -> tuple[str, float]:
        result = classifier(text, truncation=True, max_length=512)[0]
        return result["label"], float(result["score"])

    return predict


def print_report(name: str, result: dict) -> None:
    correct = result["num_examples"] - len(result["misclassified"])
    print(f"\n{'=' * 70}\n{name}")
    print(
        f"accuracy={result['accuracy']:.1%} ({correct}/{result['num_examples']}) "
        f"macro_f1={result['macro_f1']:.4f}"
    )
    for m in result["misclassified"]:
        print(f"  {m['text']!r} -> got {m['predicted']!r} ({m['confidence']:.1%}), expected {m['expected']!r}")


def main() -> None:
    from app.core.config import settings

    print_report(
        f"Production model: {settings.sentiment_model}",
        evaluate(predict_production, _LABEL_EQUIVALENCE),
    )

    predict_finetuned = load_finetuned_predictor()
    if predict_finetuned is None:
        print(f"\nNo fine-tuned weights in {FINETUNED_MODEL_DIR}; skipping the comparison.")
        return
    print_report("Local fine-tuned model", evaluate(predict_finetuned, _LABEL_EQUIVALENCE))


if __name__ == "__main__":
    main()
