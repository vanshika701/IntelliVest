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

### Run 3 — Full dataset, user-run (started 2026-09-28)

- **Rows used:** 4,501,043 (all available — `ROWS_PER_CATEGORY = None`,
  no subsampling)
- **Logistic Regression:** accuracy 0.9854, macro F1 0.9854, trained in
  30.8s
- **Random Forest:** in progress at time of writing — estimated 5-15
  minutes based on the Run 1 timing and how Random Forest's cost scales
  with data size (see chat for the full reasoning); pending completion.
- _To be completed once the run finishes — final selected model, artifact
  sizes, and the shipped `metrics.json` numbers go here._
