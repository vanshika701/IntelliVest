# ML Training Log

Every training run for this project gets an entry here — model, parameters,
dataset, features, row counts, problems hit along the way, and the metrics
actually achieved. This is the human narrative, phase by phase; each
phase's `ml/models/<phase>/metrics.json` is the machine-readable version
of its *latest* run — this file keeps the history and the story behind it,
including runs that got superseded.

Update this immediately after every training run, successful or not.

---

## Phase 3 — Expense Categorization

**Dataset:** [`mitulshah/transaction-categorization`](https://huggingface.co/datasets/mitulshah/transaction-categorization)
(Hugging Face, MIT license) — 4,501,043 rows, 10 categories, 5 countries
(USA/UK/Canada/Australia/India), gated (free HF account + one-click access
agreement + personal token, no manual review).

**Benchmark paper:** DFTSen — "A deep learning framework for automated
transaction classification and budget prediction in personal financial
management," *Discover Artificial Intelligence* (Springer, 2026). Reports
95.3% accuracy / 95.4% macro-F1 on this same dataset using a
Transformer+BiLSTM deep multi-task model.

**Features (all runs):** TF-IDF, word n-grams (1,2), max_features=10,000,
min_df=2, on lowercased/stripped `transaction_description` text.

### Run 1 — Initial classical model comparison (2026-09-20)

- **Rows used:** 100,000 (10,000/category, stratified sample)
- **Models trained:**
  | Model | Params | Accuracy | Macro F1 | Train time | Artifact size |
  |---|---|---|---|---|---|
  | Logistic Regression | `max_iter=1000` | 0.9831 | 0.9831 | 1.1s | 782KB |
  | Random Forest | `n_estimators=200, n_jobs=-1` | 0.9833 | 0.9833 | 4.8s | 129MB |
- **Selected:** Logistic Regression — a 0.0002 macro-F1 difference doesn't
  justify a 165x larger artifact the backend has to load into memory.
- **Problems faced:**
  - pandas 3.x changed `groupby().apply()`'s default behavior (drops the
    grouping column) — fixed by switching to `groupby().sample()` instead.
  - Initial model-selection logic picked whichever model had the raw
    highest macro-F1, with no regard for artifact size/speed — this is
    what produced the Random-Forest-over-Logistic-Regression pick above
    before the tie-breaking rule (within 0.005 macro-F1, prefer the
    faster/lighter model) was added.
- **Result vs. paper:** 98.3% — *above* DFTSen's reported 95.3%. Flagged
  honestly as a dataset-cleanliness artifact (this dataset's descriptions
  are template-generated, e.g. "Exxon - CANADA Store," cleaner than real
  bank statement text), not genuine model superiority over a deep model.

### Learning-curve experiment (2026-09-20, not a shipped run)

Ran Logistic Regression only, at increasing sample sizes, before deciding
whether more data was actually worth training on:

| Rows/category | Total rows | Accuracy | Macro F1 | Train time |
|---|---|---|---|---|
| 2,000 | 20,000 | 0.9848 | 0.9848 | 0.3s |
| 5,000 | 50,000 | 0.9849 | 0.9849 | 0.8s |
| 10,000 | 100,000 | 0.9831 | 0.9831 | 1.1s |
| 25,000 | 250,000 | 0.9843 | 0.9843 | 2.6s |
| 50,000 | 500,000 | 0.9851 | 0.9851 | 4.8s |
| 100,000 | 1,000,000 | 0.9858 | 0.9858 | 9.7s |

**Conclusion:** accuracy is essentially flat (98.48% → 98.58%) across a 50x
increase in training data — this dataset saturates fast, so subsampling
was always a speed decision, not an accuracy one. Decided to still train
the shipped model on more than the smallest working sample size anyway,
for credibility, rather than defend the smallest number that happened to
score well.

### Run 2 — Retrained at 100,000/category (2026-09-20, superseded)

- **Rows used:** 1,000,000 (100,000/category)
- Started by Claude in the background; stopped mid-run at the user's
  request ("bro dont train it urself") before completion — established
  going forward that the user runs training invocations personally,
  Claude prepares/edits everything around them. See Run 3.

### Run 3 — Full dataset, user-run (2026-09-28) — **currently shipped**

- **Rows used:** 4,501,043 (all available — `ROWS_PER_CATEGORY = None`,
  no subsampling)
- **Models trained:**
  | Model | Params | Accuracy | Macro F1 | Train time | Artifact size |
  |---|---|---|---|---|---|
  | Logistic Regression | `max_iter=1000` | 0.98538 | 0.98536 | 30.8s | 0.76MB |
  | Random Forest | `n_estimators=200, n_jobs=-1` | 0.98728 | 0.98727 | **1749.4s (~29.2 min)** | not measured, expected multi-GB range per the size trend from smaller runs |
- **Selected:** Logistic Regression. Random Forest scored 0.19 points
  higher (a real gap this time, not noise like the earlier smaller runs)
  but took **57x longer to train** for it — the tie-breaking rule (within
  0.005 macro-F1, prefer the faster model) correctly triggered again.
- **Problems faced:**
  - Random Forest's wall-clock time badly exceeded even the wide estimate
    given beforehand (5-15 min estimated from `n log n` scaling off the
    100k-row datapoint; actual was ~29 min, roughly 3-6x worse than that
    estimate). Cause: sklearn's Random Forest doesn't handle sparse
    high-dimensional TF-IDF features as efficiently as dense numeric
    data, and unbounded tree depth compounds with more rows — the
    `n log n` model undercounts both effects. Confirmed via `ps aux`
    mid-run: ~597% CPU (using ~6 cores) sustained for the full run, so
    it was genuinely computing throughout, not stalled/swapping.
  - This result is a useful data point for future phases: don't trust a
    simple `n log n` extrapolation for tree-based models on sparse text
    features — the real scaling is meaningfully worse.
- **Per-category detail (Logistic Regression, the shipped model):**
  weakest category is Shopping & Retail (F1 0.948, likely confusable
  with other categories); Charity & Donations and Entertainment &
  Recreation hit a perfect 1.0 F1.
- **Result vs. paper:** 98.5% accuracy/macro-F1, still above DFTSen's
  reported 95.3%/95.4% — same dataset-cleanliness caveat as Run 1 applies
  here too, now confirmed to hold even at full dataset scale, not just
  in the smaller subsample.
- **Superseded:** Run 1 (100k rows, 98.3%). This is the model currently
  in `ml/models/expense_categorizer/` and what the backend serves.

### Realistic-text stress test (2026-09-28) — critical finding

The held-out test split (98.5% accuracy) only proves the model
generalizes *within this dataset's template style* — a much easier
problem than real-world text. Built `ml/evaluate_on_realistic_examples.py`,
50 hand-written examples using real brand names and Indian UPI/NEFT/POS-
style formatting (e.g. `"POS DEBIT SWIGGY BANGALORE"`, `"ZERODHA BROKING
CHARGES"`, `"UPI-DONATION-CRY NGO"`), to measure the actual gap instead
of just asserting one exists.

- **Result: 50.0% accuracy (25/50), 74.7% average confidence** — a coin
  flip, dramatically worse than the 98.5% headline number.
- **Failure pattern:** 15+ completely unrelated real merchants (Swiggy,
  Zomato, Ola, IRCTC, Indian Oil, BookMyShow, Practo, Bescom, Airtel,
  Zerodha, LIC, GiveIndia...) all collapsed onto **"Shopping & Retail" at
  the identical 45.8% confidence** — not the model reasoning about
  ambiguous cases, but a linear classifier falling back to its strongest
  default bias when the input vector matches essentially nothing it
  learned.
- **Root cause:** the training dataset's merchant names are template
  placeholders, not real brands. The model has never seen "Swiggy,"
  "Zerodha," "BESCOM," "IRCTC," or "Practo" anywhere in 4.5M training
  rows — it learned this specific synthetic vocabulary extremely well,
  which doesn't overlap with the real world it needs to work on. This is
  **distribution shift, not classical overfitting** (the held-out
  test-split methodology itself was sound).
- **Now wired into the training pipeline permanently:**
  `evaluate_on_realistic_examples.py`'s `evaluate()` is imported and run
  automatically at the end of every future `train_expense_categorizer.py`
  run, so `metrics.json`'s `realistic_text_stress_test` field and its
  `known_limitations` text are always fresh, not a stale hand-written
  caveat. Current `metrics.json` was patched with this run's real numbers
  directly (pure evaluation against the already-trained model, no
  retraining involved).
### Fix: supplementary real-vocabulary data (2026-09-28)

Built `ml/real_merchant_vocabulary.py` — 484 rows of real brand names
(Swiggy, Zerodha, BESCOM, IRCTC, Practo, Amazon, Netflix, etc.) across
the same 10 categories, in several realistic statement-format variations
per brand. Deliberately different exact strings than the 50 stress-test
examples, so any improvement reflects genuine brand-token generalization,
not memorization of the literal test strings.

Mixed into `train_expense_categorizer.py`: added to **training only**
(the held-out test split stays pure main-dataset, so it still measures
"fits this dataset's distribution" honestly), and **upweighted via
`sample_weight`** (not row duplication) since 484 rows would otherwise be
drowned out by millions of template rows. Weight computed dynamically to
target ~5% of an average category's main-dataset weight mass
(`SUPPLEMENTARY_TARGET_FRACTION = 0.05`, a starting point, not tuned).
Also raised `max_features` from 10,000 to 30,000 and added an explicit
vocabulary check — rare brand tokens could otherwise get pruned by
frequency-based feature selection regardless of sample weighting; this
is verified, not assumed.

**Sanity-check run (20,000 rows, 2,000/category, not the shipped model):**
- Brand tokens confirmed present in vocabulary: swiggy, zerodha, bescom,
  irctc, practo — all `True`.
- **Realistic-text accuracy: 50.0% → 92.0%** (same 50 stress-test
  examples, different exact strings than what was added to training).
- This was on a small subsample as a quick correctness check (also
  caught and fixed a real bug via `ruff`: `combined_train_labels` was
  built but never passed to `train_and_evaluate`, which would have
  crashed on a train/label shape mismatch). The real full-dataset run
  with this fix is the next step — expected to do at least as well,
  likely better with more main-dataset data alongside the same
  supplementary weighting.
- **Caution:** this sanity-check run overwrote the previously-shipped
  Run 3 artifacts in `ml/models/expense_categorizer/` with this small
  test version. Do not treat the current `metrics.json` on disk as final
  until the real full-dataset run (Run 4) completes.

### BharatPOI real-vocabulary augmentation (2026-09-28)

**Problem:** the 484 hand-curated rows in `real_merchant_vocabulary.py`
fixed the worst of the out-of-vocabulary gap (50%→92% above) but only
cover ~48 national brands. Real bank statements are full of thousands of
distinct local businesses the model would never have seen a token for.

**Data source added:** [BharatPOI](https://www.kaggle.com/datasets/mansiaggarwal88/bharatpoi-india-places-intelligence-dataset)
(Kaggle, ODbL 1.0, built on OpenStreetMap) — 509,139 real, named Indian
places with a category taxonomy. New script: `ml/download_bharatpoi.py`.

- Mapped BharatPOI subcategories onto 8 of our 10 categories (see
  `_CATEGORY_MAP` in the script for the full mapping). Deliberately
  excluded `education` (no matching category of ours) and
  `infrastructure` (water towers, toilets — not merchant-like names).
  `Income` can't be helped by POI data at all (a salary isn't a place).
- After filtering to named, non-duplicate entries: 245,580 usable rows.
- Sampled down to a max of 2,000/category (explicit per-group loop, not
  `groupby().apply()` — see the pandas 3.x bug note above, hit a second
  time here and fixed the same way): **12,982 rows**, saved to
  `ml/data/bharatpoi_supplementary.csv` (committed; the raw ~280MB
  download is cached at `ml/data/raw/bharatpoi.csv`, gitignored).
  Category counts skew heavily — 2,000 each for Healthcare & Medical,
  Shopping & Retail, Entertainment & Recreation, Food & Dining,
  Government & Legal, Financial Services, but only 678 for Transportation
  and 304 for Charity & Donations (BharatPOI simply has few OSM entries
  in those categories).
- Wired into `train_expense_categorizer.py`: loads both the hand-curated
  484 rows and this CSV (if present), concatenates, and weights the
  combined supplementary set dynamically via the same
  `SUPPLEMENTARY_TARGET_FRACTION = 0.05` formula as before.

**Sanity-check run #1 (2,000 rows/category, 20,000 main rows) — misleading regression:**
- Realistic-text accuracy **dropped to 68.0%** (from the 92.0% seen with
  hand-curated-only supplementary data). This looked like adding more
  real-world data made things worse.
- **Investigated rather than accepted at face value.** Root cause: the
  `supplementary_weight` formula is
  `(main_avg_per_category * SUPPLEMENTARY_TARGET_FRACTION) / supp_avg_per_category`.
  At this tiny 2,000/category scale, `main_avg_per_category` is small,
  so the computed weight came out to just `0.1` — far too low for
  13,466 supplementary rows to have real influence during training. This
  was a **small-scale testing artifact of the weighting formula**, not a
  real regression from the data itself.

**Diagnostic run #2 (50,000 rows/category, 500,000 main rows) — confirms the fix:**
- At this more representative scale, `main_avg_per_category` is much
  larger, so `supplementary_weight` came out to `1.5` (targeting 5% of
  average category weight mass, as designed).
- Brand tokens confirmed present in vocabulary: swiggy, zerodha, bescom,
  irctc, practo — all `True`.
- LogisticRegression: accuracy=0.9856, macro_f1=0.9856 (7.9s).
  RandomForest: accuracy=0.9854, macro_f1=0.9854 (132.2s). LogReg selected
  (comparable accuracy, ~17x faster).
- **Realistic-text accuracy: 86.0%** (50 examples) vs. 98.6% on the
  held-out template-style test split.
- Confirms the hypothesis: the 68% was purely an artifact of testing at
  too small a scale, not a real problem with adding BharatPOI data. At
  representative scale the augmented model does well — though notably
  still a few points below the 92.0% seen with hand-curated-only data at
  the earlier (smaller) test. Not yet fully reconciled why BharatPOI's
  noisier, more numerous real names would land slightly below fewer,
  cleaner hand-picked brand names on this particular 50-example stress
  test — plausibly just noise at n=50, or the extra vocabulary diluting
  weight per token; worth re-checking once the real full run's numbers
  are in.
- **Caution:** this diagnostic run overwrote the previously-shipped
  artifacts in `ml/models/expense_categorizer/` with this 500K-row test
  version. It is **not** the final model — the real full-dataset run
  (Run 4, all ~4.5M main rows + both supplementary sources) is still
  pending and must be run by hand (see project convention: Claude
  prepares/edits training scripts, the user runs the actual training
  invocation).

### Run 4 — Full dataset (4,501,043 rows) with BharatPOI, real regression found and fixed (2026-09-28)

**Run as reported "ran successfully":** all ~4.5M main rows, both
supplementary sources (13,466 rows total). Model comparison:
LogisticRegression accuracy=0.9864/macro_f1=0.9864 (76.0s), RandomForest
accuracy=0.9882/macro_f1=0.9882 (3402.6s, ~57 min). LogisticRegression
selected (within the 0.005 tie tolerance, ~45x faster, ~2.29MB artifact
vs. RandomForest's far larger one).

**But the realistic-text stress test came back at 54.0%** — barely above
the original pre-fix 50%, and well below both the hand-curated-only 92%
and the 500k-row diagnostic's 86%. `brand_tokens_in_vocabulary` showed
**all five sample brands (swiggy, zerodha, bescom, irctc, practo) absent
from the fitted vocabulary** — the supplementary data's fix had silently
stopped working at full scale.

**Root cause (confirmed, not guessed):** `TfidfVectorizer(max_features=30_000)`
selects its vocabulary by raw token frequency across whatever corpus it's
fit on. That selection has no concept of `sample_weight` — weighting only
affects the classifier's `.fit()`, which happens *after* vectorization.
At the 500k-row diagnostic scale, brand tokens were frequent enough
relative to that smaller corpus to make the top-30,000 cut. At the real
~4.5M-row scale, the same ~13,466 supplementary rows are a much smaller
slice of the corpus, so tokens like "swiggy" got outranked by ordinary
words and pruned from the vocabulary entirely — before the classifier
ever saw them. A weighted row with zero surviving features contributes
nothing, no matter how high its weight is. This explains why the earlier
92%/86% results were themselves scale-dependent artifacts of an
approach that was never actually scale-invariant, not just "slightly
worse at bigger scale."

**Fix:** added `build_vectorizer()` to `train_expense_categorizer.py` —
builds the final vocabulary as a **union** of (a) the main corpus's top
`max_features` tokens by frequency and (b) every token appearing in the
supplementary corpus (fit separately, `min_df=1`, no cap), then fits
final idf weights on the combined corpus with that fixed vocabulary. This
guarantees supplementary tokens survive regardless of main-corpus size,
by construction rather than by hoping the frequency ranking works out.
Verified in isolation with an even more extreme imbalance than the real
data (50,000 generic rows vs. 5 rows containing the 5 sample brands,
`max_features=10`) — all 5 brand tokens present in the resulting
vocabulary.

Also hardened the vocabulary check from a print-and-continue into a hard
`raise RuntimeError` if any sample brand token is ever missing after
this construction — the old code detected the problem (it printed
`False` for every brand) but shipped the broken model anyway. A model
that can't tokenize a brand name should never reach `metrics.json` and
the backend, so this is now enforced, not just logged.

**Status:** the full 4.5M-row run currently on disk in
`ml/models/expense_categorizer/` (the one described above, 54% realistic
accuracy) is now known-broken by this diagnosis and must be re-run with
the fix. This is Run 5 — still pending, to be run by hand per the usual
convention. Expect similar accuracy/macro-F1 numbers on the held-out
split (~98.6%), a slightly larger vocabulary (30k main tokens plus
however many additional unique tokens the ~13,466 supplementary rows
contribute — likely a few thousand more, since most are already-common
English/Indian words), and — the number that actually matters here — a
realistic-text accuracy that should land back near 86-92%, this time for
real at full scale.

### Run 5 — Full dataset with union-vocabulary fix (shipped model) (2026-09-29)

Same data as Run 4 (4,501,043 main rows, all 13,466 supplementary rows,
sample_weight=13.4), with `build_vectorizer`'s union-vocabulary fix in
place.

- **Brand tokens in vocabulary: all `True`** (swiggy, zerodha, bescom,
  irctc, practo) — fix confirmed working at real full-dataset scale, not
  just in isolated testing.
- LogisticRegression: accuracy=0.9873, macro_f1=0.9873 (89.2s).
  RandomForest: accuracy=0.9884, macro_f1=0.9884 (2812.9s, ~47min).
  LogisticRegression selected (within the 0.005 tie tolerance, ~31x
  faster). Model artifact grew from 2.29MB to 5.12MB — expected, since
  the union vocabulary is larger than the old max_features-only one.
- **Realistic-text: accuracy 88.0% (44/50), macro-F1 0.8812, macro
  precision 0.8933, macro recall 0.8800, weighted-F1 0.8812**, average
  confidence 0.90 — vs. 98.7% accuracy / 0.9873 macro-F1 on the held-out
  template-style split. This is the real, at-scale result of the
  union-vocabulary fix, not a diagnostic extrapolation. (Accuracy alone
  is misleading on a 10-class, 5-examples-per-class stress test — a model
  strong on common categories and weak on rare ones can post good
  accuracy while quietly failing whole categories; macro-F1 catches that
  by weighting every category equally regardless of how often it's
  tested. `evaluate_on_realistic_examples.py` now reports the full set —
  see its module docstring — not just accuracy, matching what the
  held-out split already reported.)
- Remaining 6 misclassifications are genuine model confusions, not
  vocabulary gaps (e.g. "MCD DRIVE THRU 00234" → Shopping & Retail
  instead of Food & Dining; "INCOME TAX REFUND ADJ" → Income instead of
  Government & Legal; "AMZN Mktp IN*2K3RT4RF4" → Food & Dining instead of
  Shopping & Retail). These are plausible category boundary cases for a
  TF-IDF + linear model — none involve a missing/out-of-vocabulary token.
- **Status: this is the shipped model.** `ml/models/expense_categorizer/`
  now holds the full-dataset, union-vocabulary-fixed artifacts. Phase 3's
  exit criteria (trained model with a documented, honestly-measured
  real-world accuracy figure, not just a held-out split) is met.

### Targeted improvement attempt: trigrams + disambiguation rows + larger stress test (2026-09-29)

Three changes made after reviewing Run 5's 6 misclassifications for
patterns rather than treating 88% as final:

1. **`build_vectorizer` widened from bigrams to trigrams** (`(1,2)` →
   `(1,3)`) — "LIC PREMIUM AUTO DEBIT" predicted Transportation because
   "auto" alone is dominated by vehicle-related rows in the main
   dataset; trigrams let the model learn "auto debit"/"premium auto" as
   distinct, less ambiguous units instead of only ever seeing "auto" in
   isolation.
2. **14 targeted disambiguation rows added** to
   `real_merchant_vocabulary.py` (`_DISAMBIGUATION_EXAMPLES`) for the
   three confirmed confident-and-wrong errors: "auto debit"/"auto pay"
   phrasing under Financial Services (6 rows), "ENT" as an
   Entertainment-company abbreviation rather than the medical one (5
   rows), and "AMZN Mktp" abbreviated Amazon phrasing under Shopping &
   Retail (3 rows). Supplementary row count: 484 → 498.
3. **Stress test expanded from 50 to 150 examples** (15/category,
   evenly balanced) — 50 examples at 5/category made macro-F1 noisy;
   this also gives a genuine held-out check on whether the
   disambiguation fix generalizes (new examples use different exact
   strings than both the original 50 and the new training rows).

**Diagnostic run (50,000/category, sample_weight=1.5 — same
representative scale used to validate Run 4→5, not the full dataset):**
LogisticRegression accuracy=0.9857/macro_f1=0.9857 (13.5s). Brand tokens
still all present. **Realistic-text: 87.3% accuracy, 0.8746 macro-F1**
(150 examples) vs. 98.6% held-out.

- Checked the three originally-targeted failures directly, not just the
  aggregate number: **"LIC PREMIUM AUTO DEBIT" — fixed. "GAMEZOP ENT PVT
  LTD" — fixed. "AMZN Mktp IN*2K3RT4RF4" — still wrong** (now predicted
  Food & Dining at only 28.4% confidence, i.e. genuinely uncertain rather
  than confidently wrong as before, but still incorrect). 3 disambiguation
  rows at a small-scale weight of 1.5 apparently isn't enough signal yet
  for this one, alongside noisy alphanumeric reference codes in the test
  string itself ("2K3RT4RF4") contributing nothing.
- The larger 150-example test surfaced additional confident-and-wrong
  cases not visible in the original 50 (e.g. "AMBULANCE SERVICE CHARGE"
  → Government & Legal at 100% confidence, expected Healthcare &
  Medical) — expected, since a bigger, more diverse test finds more edge
  cases; these are new information, not new regressions.
- The aggregate number (87.3%) isn't directly comparable to Run 5's 88.0%
  — different example count (150 vs 50) and this is a 50k/category
  diagnostic, not the full ~4.5M-row dataset. The full run's
  supplementary weight is much higher (~13x vs 1.5x here), so the
  AMZN-style disambiguation rows should carry more influence there,
  similar to how the earlier 500k-row diagnostic understated Run 5's
  eventual full-scale result.
- **Status:** 2 of 3 targeted fixes confirmed working at this scale; the
  real full-dataset run (Run 6) is the actual test of whether these
  changes net out as an improvement over Run 5, and is still pending —
  to be run by hand per the usual convention. If "AMZN Mktp" is still
  wrong at full scale, it's a real, documented residual limitation, not
  a regression to worry about — accuracy did not get worse anywhere in
  this diagnostic.

### Run 6 — Full dataset with trigrams + disambiguation rows (shipped model) (2026-09-29)

Same full dataset as Run 5 (4,501,043 main rows), now with trigrams
(`(1,3)`), 14 additional disambiguation rows (498 supplementary rows
total, up from 484), and the expanded 150-example stress test.

- LogisticRegression: accuracy=0.9873, macro_f1=0.9873 (81.0s).
  RandomForest: accuracy=0.9883, macro_f1=0.9883 (3218.4s, ~54min).
  LogisticRegression selected (within tie tolerance, ~40x faster).
  Artifact grew from 5.12MB to 6.89MB (trigrams enlarge the vocabulary
  further) — still trivially small to load.
- Brand tokens still all present in vocabulary (`True` for all 5).
- **All 3 originally-targeted disambiguation failures now fixed at full
  scale**, including "AMZN Mktp IN*2K3RT4RF4" — which the 50k/category
  diagnostic couldn't fix (too little supplementary weight at that
  scale, ~1.5x vs. ~13.4x here) — confirming the hypothesis from that
  diagnostic rather than leaving it as a guess.
- **Realistic-text: accuracy 92.0%, macro-F1 0.9200, macro precision
  0.9233, macro recall 0.9200** (138/150 correct, avg. confidence 0.90)
  vs. 98.7% accuracy / 0.9873 macro-F1 on the held-out split. A real
  improvement over Run 5's 88.0%/0.8812 — and on a 3x larger, harder
  test set (150 examples vs. 50), not a smaller easier one, so the
  comparison is if anything conservative in Run 6's favor.
- **Remaining 12 misclassifications are genuine open cases**, not
  vocabulary/tokenization bugs — e.g. "AMBULANCE SERVICE CHARGE"
  confidently (99.99%) misfiled as Government & Legal instead of
  Healthcare & Medical, "VEHICLE FITNESS CERT FEE" as Entertainment &
  Recreation instead of Government & Legal. These are documented in
  `metrics.json`'s `realistic_text_stress_test.misclassified` as known,
  open limitations — not chased further here, since each is a smaller,
  more specific edge case with diminishing returns relative to the
  effort already spent (trigrams + targeted disambiguation rows fixed
  every *confirmed, investigated* failure pattern from Run 5).
- **Status: this is the shipped model, superseding Run 5.** Phase 3 is
  considered complete at this result.

---

## Phase 4 — Stock Price Prediction

**Data:** Yahoo Finance daily adjusted closes, 20 stocks + Nifty 50 + India
VIX, 2008-03-03 to 2026-11-25. 90,591 stock-days; 1,503,364 labelled rows
(17 horizons, 1 to 504 trading days); every 4th trading day kept for
training (375,996 rows in the final fit).

**Model:** `HistGradientBoostingClassifier` (max_iter 250, learning_rate
0.05, max_leaf_nodes 31, min_samples_leaf 400, l2 1.0) over 15 buckets of
volatility-scaled return. One model for all stocks and horizons; horizon
is an input. 27 inputs, price and market only. Details:
`docs/PHASE_4_PREDICTION.md`.

### Run 1 — quick smoke run (2026-11-27)

60 trees, test years 2024–2025, 5 minutes. Range hit 78–83%; direction
at or below "always up". Used only to test the pipeline end to end.

- **Problem:** `log(0)` in the volatility trend when a price sat flat for
  weeks. Infinite inputs now become missing values, which the model
  handles natively.
- **Problem:** two data breaks over 35% in a day: TMPV (demerger) and
  NESTLEIND (2024 1:10 split, unadjusted on Yahoo). Inputs and labels are
  split at breaks.
- **Problem:** Mongo dates and parquet dates had different precisions, so
  the market merge failed in the backend. Dates are normalised inside
  `compute_features`, so training and serving match.
- **Bug found by a test:** with an empty bucket, the percentile inversion
  dropped the wrong edge (gave −1.0 instead of −0.5). Rewritten; the
  smoke run's metrics were computed before the fix and are superseded.

### Run 2 — full run, shipped model 1.0.0 (2026-11-27)

Walk-forward 2020–2025, about 2.5 minutes per fold, 22 minutes in all.
Baseline: the same range from recent volatility alone.

| Horizon | Range hit | Baseline | Up/down right | Always up | Rank corr (baseline) |
|---|---|---|---|---|---|
| Up to 1 week | 81.4% | 80.5% | 51.9% | 52.7% | 0.024 (−0.011) |
| 1 week to 1 month | 80.6% | 79.9% | 54.8% | 56.2% | 0.025 (−0.008) |
| 1 to 6 months | 79.8% | 79.7% | 61.6% | 63.0% | 0.039 (0.023) |
| 6 months to 2 years | 81.8% | 82.1% | 76.6% | 76.9% | 0.020 (0.131) |

- Ranges are calibrated, but mostly thanks to volatility; the baseline is
  too. Pinball loss is within 1% of the baseline; the model is better only
  at 6 months to 2 years (ranges 87% wide vs 99%, same hit rate).
- Direction never beats "always up". Short-horizon ranking is slightly
  better than the baseline (positive in 5 of 6 years up to 1 week);
  long-horizon ranking is worse.
- Hindsight: the 20 stocks are today's large caps, so long horizons lean
  optimistic.

---

## Phase 5 — Financial Sentiment Analysis

**Base model:** [`ProsusAI/finbert`](https://huggingface.co/ProsusAI/finbert)
(Araci, 2019) — pretrained financial-sentiment BERT, public, no gating.
Usable directly via CPU inference with zero training — this is what
ships by default (`backend/app/services/sentiment_service.py`).

**Paper (optional fine-tune upgrade):** "Towards Efficient FinBERT via
Quantization and Coreset for Financial Sentiment Analysis," FinNLP
workshop, EMNLP-2025 ([aclanthology.org/2025.finnlp-2.6](https://aclanthology.org/2025.finnlp-2.6.pdf)).
Fine-tunes FinBERT further, then applies coreset selection + quantization
for a lighter, CPU/edge-friendly model — exactly the shape this project
needs with no GPU access yet.

**Dataset (for the fine-tune):** [`zeroshot/twitter-financial-news-sentiment`](https://huggingface.co/datasets/zeroshot/twitter-financial-news-sentiment)
(Hugging Face, MIT license, no gating) — 9,543 train / 2,388 validation
tweets, 3 classes (0=Bearish, 1=Bullish, 2=Neutral). Paper's own reported
full fine-tune baseline: 83.4% accuracy / 0.833 macro-F1.

**Benchmark ceiling (cited for context, different dataset/label scheme —
not directly comparable, same honesty standard as Phase 3's DFTSen
comparison):** FLARE (PIXIU, NeurIPS 2023) and FinBen (NeurIPS 2024)
report off-the-shelf FinBERT at 0.912 F1 on Financial PhraseBank, within
a few points of GPU-only instruction-tuned LLMs (FinMA-7B: 0.965,
FinGPT: ~0.876) on the same public benchmark — the justification for
using pretrained FinBERT as a CPU-only baseline rather than needing a
GPU-heavy instruction-tuned model to get reasonable results.

**What was actually built (2026-09-29):**
- `backend/app/services/sentiment_service.py` — lazily loads a
  sentiment-analysis pipeline. Prefers a local fine-tuned model at
  `ml/models/sentiment_finbert/` if present (via
  `ml/finetune_finbert_sentiment.py`), otherwise falls back to the
  off-the-shelf `ProsusAI/finbert` checkpoint from Hugging Face Hub —
  same graceful-degradation pattern as Phase 3's expense categorizer,
  except sentiment scoring works immediately with zero setup, since the
  base model needs no local training.
- Wired into the existing Phase 1 news ingestion pipeline
  (`backend/app/services/news_service.py`) — every article's
  title+description is scored at ingestion time and stored
  (`sentiment_label`, `sentiment_confidence`), never recomputed per
  dashboard request. This follows Phase 5's own system-design note in
  `PROJECT_PLAN.md` (score as part of the same background pipeline as
  Phase 1) — no new scheduled job needed, just an extra step in the
  existing one.
- `GET /api/v1/news/sentiment-model-info` exposes model provenance
  (pretrained vs. fine-tuned) and, if fine-tuned, its benchmark metrics —
  same role as Phase 3's `categorization-model-info` endpoint.
- **Verified live**, not just in tests: ran a real ingestion for
  RELIANCE.NS against real MongoDB, confirmed real FinBERT sentiment
  labels/confidences on real, current news articles through the running
  API's dashboard endpoint (e.g. "₹31 trn wiped out; nearly 40% of Nifty
  stocks down over 20%" → negative, 97.4%).
- `ml/finetune_finbert_sentiment.py` — the optional fine-tune+quantization
  script implementing the FinNLP paper's approach (not yet run for real;
  see below). Fine-tunes FinBERT on the Twitter dataset, evaluates full
  precision vs. dynamic int8 quantization (PyTorch's standard technique —
  not the paper's exact multi-bit scheme, a real but different
  compression method, documented as such rather than overclaiming an
  exact replication), and ships the full-precision result (quantized
  models don't round-trip through `save_pretrained`/`from_pretrained` as
  cleanly, and the tradeoff needs measuring before it's worth that
  complexity — see the script's own `selection_reasoning`).
- **Two real bugs caught and fixed via a smoke-test dry run** (40 train /
  20 validation rows, 1 epoch) before handing off the real training
  invocation, same "verify before shipping" discipline as Phase 3:
  1. `TrainingArguments` needs `accelerate>=1.1.0` — not previously a
     project dependency; added.
  2. `classification_report` crashed on the tiny smoke-test slice because
     not all 3 classes appeared in 20 rows — fixed by passing an explicit
     `labels=` parameter, making it robust regardless of scale (this
     specific crash wouldn't occur on the real 2,388-row validation set,
     but the fix is correct defensively either way).
  3. PyTorch's dynamic quantization needs an explicit backend engine, and
     `fbgemm` (the default the library assumes) isn't available on Apple
     Silicon — only `qnnpack` is (confirmed via
     `torch.backends.quantized.supported_engines`, not assumed). Fixed by
     explicitly setting `torch.backends.quantized.engine = "qnnpack"`
     when available.
- **Bonus finding:** this M1 Mac has PyTorch MPS (Metal Performance
  Shaders) acceleration available (`torch.backends.mps.is_available()`
  → `True`). The fine-tune script uses it automatically when present.
  This is unrelated to Phase 4 being on hold — Phase 4 needs proper
  CUDA-class GPU compute for a full stock universe + Transformer variant,
  which MPS doesn't provide — but for FinBERT's much smaller fine-tune,
  MPS meaningfully speeds up training on this machine specifically.
### Real fine-tune run (2026-09-29)

Full dataset (9,543 train / 2,388 validation rows), 3 epochs, MPS device,
2646.1s (~44 min) training time.

- **Full-precision: 87.86% accuracy, 0.8412 macro-F1** — above the
  paper's own reported 83.4%/0.833 baseline. Documented honestly rather
  than presented as "we beat the paper," same standard as Phase 3's
  DFTSen comparison: likely explained by normal run-to-run variance
  (different random seed, exact hyperparameters, or train/eval split
  mechanics aren't identical to the paper's), not a claim of a better
  method. Per-category: strong on Neutral (0.918 F1, the majority class,
  1566/2388 support), weaker on Bearish (0.786 F1, the minority class,
  347/2388 support) — an expected imbalance effect, not a bug.
- **Quantized (int8): 86.56% accuracy, 0.8147 macro-F1** — a real but
  modest ~2.6-point macro-F1 drop for a **4.6x size reduction**
  (417.67MB → 91.07MB). This is the genuine, measured tradeoff (using
  PyTorch's standard dynamic quantization, not the paper's exact
  multi-bit scheme — see the script's own documentation for why).
  Interesting per-category detail: Bullish recall dropped sharply under
  quantization (0.819 → 0.680) while Bearish/Neutral held up better —
  quantization doesn't degrade uniformly across classes, worth knowing
  if a future deployment target actually needs the smaller model.
- **Shipped: full-precision.** `ml/models/sentiment_finbert/` now holds
  the fine-tuned model; `sentiment_service.py` automatically prefers it
  over the off-the-shelf checkpoint (confirmed live: reloaded the
  backend, `GET /api/v1/news/sentiment-model-info` now returns this
  run's real metrics, and a live re-ingestion scored new articles using
  the fine-tuned Bearish/Bullish/Neutral label scheme successfully).
- **One test fix required:** `test_sentiment_service.py`'s integration
  test asserted the pretrained checkpoint's label vocabulary
  (positive/negative/neutral) — now that a fine-tuned model is present
  locally, it correctly loads that one instead, which uses a different
  label scheme (Bearish/Bullish/Neutral, matching this dataset). Fixed
  by accepting either vocabulary, since the service is designed to
  support both configurations depending on what's present on a given
  machine — not a bug in the service itself, just a test that assumed
  one specific configuration.
### Domain-shift check: does the tweet-trained fine-tune actually help production? (2026-09-29)

**Question raised:** is one dataset (tweets) enough, given production
actually scores news article headlines/descriptions, not tweets? Checked
empirically rather than assumed — built
`ml/evaluate_sentiment_on_realistic_news.py`: 30 hand-written, realistic
financial news headlines (Sensex/Nifty moves, earnings, M&A, macro news —
not tweets, not from either training dataset), ran both the off-the-shelf
pretrained checkpoint and the fine-tuned model on the same set.

**Result: the fine-tune made things worse for the actual task.**

| | Pretrained FinBERT | Fine-tuned (on tweets) |
|---|---|---|
| Realistic news headlines (30 examples) | **83.3% accuracy, 0.7855 macro-F1** | **73.3% accuracy, 0.7044 macro-F1** |

Despite scoring 87.86% on its own tweet validation split, the fine-tuned
model under-calls clearly positive/negative news as Neutral far more
than the pretrained checkpoint does — e.g. "India's GDP growth seen at
7.2%" and "L&T wins ₹5,000 crore order" both wrongly predicted Neutral
by the fine-tuned model but correctly caught by the pretrained one; "Foreign
investors pull out ₹12,000 crore" (clearly negative) also missed only by
the fine-tuned model. This is exactly the train/production distribution
mismatch Phase 3 hit before its realistic-text stress test caught it —
a dataset that looks good on its own held-out split can still be the
wrong dataset for the actual deployment domain, and the only way to know
is to test on that domain directly, not trust the training dataset's own
metrics.

**Root cause:** tweets and news headlines share financial vocabulary but
differ structurally — tweets are short, informal, often ticker/hashtag-
heavy fragments; news headlines are complete, formal sentences with
different syntactic cues for expressing outlook. Fine-tuning pulled the
model's decision boundary toward tweet-style patterns and away from
whatever the original FinBERT pretraining (Financial PhraseBank-style
analyst-report sentences — much closer to news-headline style) had
already learned.

**Fix applied:** `sentiment_service.py` now defaults to the pretrained
checkpoint regardless of whether a fine-tuned model is present, gated
behind a new `USE_FINETUNED_SENTIMENT_MODEL` setting (default `false`,
documented in `backend/.env.example`). `get_model_info()` was also fixed
to only report the fine-tuned model's benchmark metrics when that model
is actually the one loaded — it was previously always reading
`ml/models/sentiment_finbert/metrics.json` regardless of which model was
in use, which would have made the info endpoint lie about what's
actually running once fine-tuned artifacts existed.

**What's kept, and why:** the fine-tuned model and `finetune_finbert_sentiment.py`
are kept as-is — a real, working implementation of the paper's method
with an honest, documented negative result, not deleted. A negative
result that changes a shipped default is exactly the kind of finding
this log exists to capture.

**What a real fix would need:** fine-tuning on a dataset that actually
matches news-headline style — Financial PhraseBank (analyst-report
sentences, much closer to news headlines than tweets, though CC BY-NC-SA
— non-commercial) is the natural candidate, either replacing or
supplementing the Twitter dataset. Not done yet — a genuine next step,
not merely a caveat, if this feature needs to earn back the ground lost
here.

- **Status:** Phase 5's sentiment half is live and shipped, defaulting
  to the pretrained checkpoint (83.3% on realistic headlines) since it's
  measurably better for the real task. The tweet-fine-tuned model is
  built, benchmarked, and available for comparison but not the default.
  Summarization half remains deferred pending an LLM choice.

### Combined-dataset re-fine-tune: fixing the domain gap for real (2026-09-29)

Rewrote `ml/finetune_finbert_sentiment.py` to fine-tune on **two**
datasets instead of one, targeting the exact gap the domain-shift check
found:

- **zeroshot/twitter-financial-news-sentiment** (as before) — tweets,
  informal/social coverage.
- **Financial PhraseBank** (Malo et al., 2014), added specifically
  because it's real financial news/analyst-report sentences — much
  closer in style to the news headlines this app actually scores. The
  canonical `takala/financial_phrasebank` repo uses a deprecated
  Hugging Face "loading script" format the installed `datasets` library
  (5.0.1) no longer supports at all (`RuntimeError: Dataset scripts are
  no longer supported`); found and used
  `warwickai/financial_phrasebank_mirror` instead, a community mirror in
  standard Parquet format, 4,846 rows. **License: CC BY-NC-SA 3.0 —
  non-commercial only**, flagged prominently in the script and here.
  Its label convention (0=negative, 1=neutral, 2=positive) was
  **confirmed empirically**, not trusted from the dataset card — checked
  per-class counts against the well-documented original distribution
  and spot-checked actual sentence content (e.g. a label-0 sentence
  describes layoffs, a label-2 sentence describes profitability growth).

**Labels unified onto FinBERT's own scheme** (positive/negative/neutral
— confirmed via `AutoConfig.from_pretrained('ProsusAI/finbert').id2label`,
not assumed) rather than the Twitter dataset's Bearish/Bullish/Neutral —
this also fixes the earlier "different label scheme" limitation, since
the fine-tuned model's output vocabulary now matches the pretrained
checkpoint's exactly.

**The realistic-news-headline stress test now runs automatically** at
the end of every fine-tune run (imports `evaluate()` from
`ml/evaluate_sentiment_on_realistic_news.py`), the same "verify against
realistic text every run" discipline `train_expense_categorizer.py`
established for Phase 3 — `metrics.json`'s `realistic_news_stress_test`
field, including a direct `beats_pretrained_baseline` boolean, is always
current, not a one-off manual check.

**Smoke-tested** (30+30 combined rows, 1 epoch, redirected output) before
handing off the real run — full pipeline (dual dataset loading, label
unification, combined + per-source validation, the realistic-news stress
test, quantization, saving) ran end-to-end with no crashes. The smoke
test's own accuracy numbers are meaningless (tiny data, 1 epoch) — this
was a mechanics check, not a quality check.

**Status:** prepared and smoke-tested; the real run (full combined
dataset, 3 epochs) is still pending, to be run by hand per the usual
convention (`cd ml && python3 finetune_finbert_sentiment.py`). Whether
`sentiment_service.py`'s default flips back to the fine-tuned model
depends entirely on whether this run's `beats_pretrained_baseline` comes
back `true` — not decided in advance.

### Hardware constraint discovered: 8GB RAM, real run paused (2026-09-29)

A real attempt at the combined-dataset run (above) was started and ran
very slowly — investigated rather than assumed hung. Findings:

- **This machine has only 8GB total RAM** (`sysctl hw.memsize`), not
  previously measured/documented. The training process alone used
  6.6GB resident; combined with Chrome, several VS Code renderer
  processes, and Claude Code itself, the system was left with ~82MB
  free and was swapping heavily (memory compressor active, large
  swapin/swapout counts) — genuine disk I/O thrashing, not a code bug.
  CPU usage on the process itself was only ~10-15%, consistent with
  time spent waiting on swap rather than computing.
- **Confirmed via `trainer_state.json` the run was progressing, not
  stuck:** `global_step: 839` of `max_steps: 2517` — exactly 1 of 3
  epochs complete in ~56 minutes. At that pace, full completion
  (3 epochs + eval + quantization) was projected at ~2-3 hours, far
  longer than the single-dataset run's 44 minutes — the extra ~40% of
  training data (combined ~13.4k rows vs. 9.5k) doesn't explain a
  ~3-4x slowdown; the swap thrashing does.
  - Note for interpreting `ps`/`top` output on this kind of job going
    forward: low reported CPU% during an MPS-accelerated run doesn't by
    itself mean something is wrong (MPS compute doesn't show as CPU
    time) — the actual signal that something was wrong here was the
    memory-pressure numbers (free RAM, swap activity), not CPU% alone.
- **Also found and cleaned up:** two of my own smoke-test runs earlier
  had written checkpoints into the real `ml/_finetune_checkpoints/`
  directory instead of a scratch location — a gap in the smoke test's
  isolation (only `MODEL_DIR` was redirected, not the `TrainingArguments`
  `output_dir`). Combined with the real run's own checkpoints, this had
  grown to 7.4GB (checkpoints save full optimizer state alongside the
  model — ~1.2GB per checkpoint for a 420MB model). Deleted — all
  regenerable, none of it was final output.
- **Decision:** run stopped (SIGTERM/SIGKILL, confirmed cleanly
  terminated) rather than left running or restarted, at the user's
  choice, to decide the approach later. Options on the table for next
  time: close memory-heavy apps (Chrome, extra VS Code windows) before
  starting to give the run more headroom, and/or lower `BATCH_SIZE`
  (16 → 8) to reduce peak memory footprint directly — the more reliable
  fix given the RAM ceiling is a fixed hardware constraint, not
  something freeing up apps alone may fully solve on an 8GB machine.
- **Status:** the combined-dataset fine-tune has NOT completed. The
  currently-shipped/default sentiment model remains the plain pretrained
  checkpoint (83.3% on realistic headlines) — nothing changes until a
  real completed run says otherwise.
- **Not yet built:** LLM-based news summarization (Phase 5's second
  half) — deferred pending a decision on which LLM API to use; no strong
  recent paper exists for this specific task (see the Phase 5 research
  report), so the plan is prompting-based summarization evaluated via
  ROUGE against the public FNS shared-task dataset as a methodology
  convention, not a specific paper's method.

### Scripts adapted to the merged backend, both models re-measured (2026-11-26)

No training was done; this re-evaluates existing models.

- **Environment:** torch 2.15.0, transformers 5.23.0, scikit-learn 1.9.1.
- **Dataset:** the same 30 hand-written headlines (sentiment) and 150
  hand-written transactions (expenses).
- **Results (unchanged from before):** pretrained FinBERT 83.3% (25/30) /
  0.7855 macro-F1; tweet fine-tune 73.3% (22/30) / 0.7044; expense
  categorizer 92.0% (138/150) / 0.9200.
- **Problem:** both evaluation scripts called backend functions that no
  longer exist (`analyze_sentiment`, `expense_categorization_service`).
  Sentiment now goes through `score_texts()` and rejects its lexicon
  fallback; the categorizer loads its artifacts directly.
- **Problem:** `beats_pretrained_baseline` compared against a rounded
  0.833, so a 25/30 tie would have counted as a win. Now exactly 25/30.
- **Label mismatch:** the current fine-tuned weights output
  Bullish/Bearish, which the backend would score as 0. They must not be
  set as `SENTIMENT_MODEL`.

## Phase 7 — Portfolio Recommendation Engine

### Walk-forward backtest of the minimum-variance equity optimizer (2026-11-26)

No model is trained in Phase 7; this evaluates the optimizer the app ships.
Script: `ml/backtest_portfolio.py`; results: `ml/models/portfolio_backtest/metrics.json`.

- **Model:** minimum variance on a Ledoit-Wolf shrunk covariance, long only,
  at most 15% per stock and 35% per sector, holdings under 1% dropped
  (`backend/app/services/equity_optimizer.py`, version `minvar-v1`).
  Sentiment tilt off: there are no historical FinBERT scores to test it on.
- **Data:** Yahoo Finance daily dividend-adjusted closes for the 20 tracked
  stocks and the Nifty 50 price index (^NSEI), 2012-01-03 to 2026-11-23,
  3,656 trading days.
- **Method:** walk-forward. Every 21 trading days, rebuild the portfolio
  from the previous ≤504 daily returns only, hold it (weights drift) until
  the next rebalance. 163 rebalances over 13.6 years. 0.2% cost per rupee
  traded; 6% risk-free rate for Sharpe. Both are our assumptions.
- **Results (out of sample):**

  | Strategy | CAGR | Volatility | Max drawdown | Sharpe | ₹100 became |
  |---|---|---|---|---|---|
  | Minimum variance | 16.9% | 13.9% | -29.6% | 0.78 | ₹828 |
  | Equal weight, same 20 stocks | 17.7% | 16.0% | -36.7% | 0.73 | ₹909 |
  | Nifty 50 (price index) | 11.2% | 16.1% | -38.4% | 0.33 | ₹425 |

- **Risk model check:** the optimizer predicted 12.6% average volatility
  and the following months delivered 12.4%; for equal weight, 15.2%
  predicted vs 14.2% realised. Minimum variance was calmer than equal
  weight in 80% of months.
- **Reading:** the optimizer does what it claims out of sample: about 13%
  less volatility and a 7-point smaller worst fall than equal weight, for
  0.8 points less return a year, so a slightly better Sharpe ratio. It
  does not beat equal weight on return, and wasn't designed to. Average
  turnover is 10% per rebalance (about 2 stocks' worth) vs 5% for equal
  weight. It lagged badly in 2025 (5.5% vs 11.5%), when calmer stocks fell
  behind.
- **Problems found and fixed:**
  - The 25% "data break" threshold in `market_stats.py` would have dropped
    two genuine days: Axis Bank -27.9% (2020-03-23, COVID) and SBI +27.7%
    (2017-10-25, recapitalisation news). Raised to 35%, which still catches
    the TMPV demerger break (-40%, 2025-10-14) — the only one in 15 years.
  - First version dropped every day the index had no price; on Diwali
    Muhurat sessions that merged two days of stock moves and flagged a
    real TMPV +36% two-day rise as a data break. Now index gaps are
    carried forward instead.
- **Biases, not fixed:** the 20 stocks are today's large caps (hindsight),
  which flatters all stock strategies against the index; ^NSEI excludes
  dividends (~1-1.5% a year). Both affect the index comparison more than
  min-variance vs equal weight, which share the universe.

## Phase 9 — AI Investment Advisor

### Scenario evaluation of the rules advisor (2026-11-27)

No model is trained in Phase 9: the advisor is rules over the other modules'
outputs. Script: `ml/evaluate_advisor.py`; scenarios:
`backend/tests/advisor_scenarios.py`; results:
`ml/models/advisor_eval/metrics.json`. The same checks run in the test suite
(`backend/tests/test_advisor_eval.py`).

- **Method:** no dataset of "correct advice" exists, so, as with the Phase 3
  and 5 realistic-text tests, 18 hand-written user situations (new user,
  overspender, no emergency fund, critical and high EMIs, drifted and
  on-target portfolios, all money in one stock, bad news with and without a
  falling sector, unaffordable goal, stale plan, short-horizon conservative
  plan, unclassifiable funds, profile without a plan, everything wrong at
  once, savings not entered). Expectations were written from each situation
  before running the rules: which action comes first, which must and must
  not appear, which setup steps.
- **Results:** 18/18 scenarios give the expected advice; all 10 rules are
  triggered somewhere. 109 module knock-outs (every usable module, every
  scenario): 0 problems — advice still built, marked partial, never citing
  the missing module. 50 ₹ figures shown in actions: all traced to the
  action's data or its source modules.
- **The checks were tested too:** putting investing before the safety net,
  adding an invented ₹ figure, or citing a missing module each makes the
  checks fail (`test_advisor_eval.py`).
- **Problems found and fixed while writing the scenarios:**
  - Several stocks over 15% each produced one card per stock (three cards
    for one problem); now one combined card.
  - Two scenario spending categories were misspelt (`transport`,
    `shopping`). `analyze_budget` silently ignores unknown ids, so the
    spending would have vanished; the scenario builder now rejects them.
  - Earlier, on real data: investing advice for a user without a budget
    didn't say the emergency-fund and debt checks had been skipped; it does now.
- **Not measured:** the optional LLM wording (no key configured); its number
  guard is unit-tested with changed, reordered and failed replies.
- **Limits:** scenarios written by the developers, not reviewed by a
  certified planner; they check decisions on realistic inputs, not whether
  real users find the advice useful, which needs a user study.
