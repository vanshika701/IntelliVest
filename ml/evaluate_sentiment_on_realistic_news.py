"""Domain-shift stress test for the news-sentiment model (Phase 5).

The fine-tuned model (ml/finetune_finbert_sentiment.py) was trained on
zeroshot/twitter-financial-news-sentiment — short, informal TWEETS. But
production actually scores NEWS ARTICLE headlines/descriptions from
NewsAPI (backend/app/services/news_service.py) — longer, more formal
text, structurally different from tweets. This is exactly the kind of
train/production distribution mismatch that hurt Phase 3 before its
realistic-text stress test caught it (see ml/log.md) — so it gets
checked here empirically instead of assumed away.

Hand-written, realistic financial news headlines (not tweets, not from
either training dataset), labeled by hand. Compares the off-the-shelf
pretrained checkpoint against the fine-tuned model on the SAME examples,
since the real question isn't "how good is the fine-tuned model in
isolation" (already measured on its own tweet validation split) but
"did fine-tuning on tweets help or hurt for the news-headline domain it
actually runs on in production."

Run directly:
    cd ml && python3 evaluate_sentiment_on_realistic_news.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

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


def main() -> None:
    from app.services import sentiment_service

    # Force-load the off-the-shelf pretrained checkpoint, bypassing the
    # fine-tuned model this machine has, for a genuine side-by-side.
    from transformers import pipeline

    print("Loading pretrained ProsusAI/finbert (bypassing local fine-tuned model)...")
    pretrained_pipe = pipeline("sentiment-analysis", model="ProsusAI/finbert")

    def predict_pretrained(text: str):
        result = pretrained_pipe(text, truncation=True, max_length=512)[0]
        return result["label"], float(result["score"])

    print("Loading fine-tuned model (ml/models/sentiment_finbert if present, else pretrained)...")

    def predict_current(text: str):
        result = sentiment_service.analyze_sentiment(text)
        if result is None:
            raise RuntimeError("Sentiment model unavailable")
        return result

    pretrained_eval = evaluate(predict_pretrained, _LABEL_EQUIVALENCE)
    current_eval = evaluate(predict_current, _LABEL_EQUIVALENCE)

    print(f"\n{'=' * 70}")
    print("Realistic financial NEWS HEADLINE stress test (not tweets)")
    print(f"{'=' * 70}")
    print(
        f"Off-the-shelf pretrained FinBERT: accuracy={pretrained_eval['accuracy']:.1%} "
        f"macro_f1={pretrained_eval['macro_f1']:.4f}"
    )
    print(
        f"Currently-loaded model (fine-tuned if present): accuracy={current_eval['accuracy']:.1%} "
        f"macro_f1={current_eval['macro_f1']:.4f}"
    )

    print("\nPretrained model misclassifications:")
    for m in pretrained_eval["misclassified"]:
        print(f"  {m['text']!r} -> got {m['predicted']!r} ({m['confidence']:.1%}), expected {m['expected']!r}")

    print("\nCurrent (fine-tuned) model misclassifications:")
    for m in current_eval["misclassified"]:
        print(f"  {m['text']!r} -> got {m['predicted']!r} ({m['confidence']:.1%}), expected {m['expected']!r}")


if __name__ == "__main__":
    main()
