# IntelliVest AI

An AI-powered investment advisor + budgeting/watchlist platform. See
[`PROJECT_PLAN.md`](./PROJECT_PLAN.md) for the full phased build roadmap.

## Repo structure

```
backend/     FastAPI service (layered: api / services / data / core)
frontend/    React + TypeScript + Tailwind app (Vite)
ml/          Model training notebooks/scripts and saved artifacts
blockchain/  Mode 2 AI + user-owned vault contracts (Phase 10 — contracts built, not connected yet)
docs/        Written docs/evaluation reports produced as phases complete
```

## Prerequisites

- Python 3.12 (pinned in `.python-version`)
- Node 24 (pinned in `.nvmrc`)
- Docker Desktop, for MongoDB: `docker compose up -d` from the repo root
  starts MongoDB 8.0 on `localhost:27017`, with data kept in a Docker
  volume across restarts (`docker compose down` stops it)

## Backend setup

```bash
python3 -m venv .venv          # once, from the repo root (Windows: py -3.12 -m venv .venv)
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd backend
cp .env.example .env           # JWT_SECRET_KEY works out of the box for local dev;
                                # fill in API keys as later phases need them
uvicorn app.main:app --reload --port 8000
```

Check it's alive: `curl http://localhost:8000/api/v1/health` should return
`{"status": "ok", "database": "connected"}` (MongoDB must be running for
`database` to say `connected`).

Run backend tests and lint:

```bash
cd backend
pytest
ruff check .
```

### Data ingestion (Phase 1)

Three pipelines pull real data into MongoDB — market data (yfinance, no
key needed), news (Indian financial RSS feeds, no key needed), and Reddit (asyncpraw). Each has a manual
entry point for one-off runs, and all three also run automatically on a
schedule (daily for prices, hourly for news/Reddit) whenever the backend
is running. Prices missed while it was off are fetched at the next start.
Stock pages, the watchlist and alerts use Yahoo quotes (about 15 minutes
delayed), falling back to the last stored close. Scheduling is in `app/core/scheduler.py` (which also runs price-alert
evaluation every 5 minutes, for Phase 2's watchlist alerts):

```bash
cd backend
python -m scripts.ingest_market_data   # works immediately, no API key
python -m scripts.ingest_news          # works immediately, no API key
python -m scripts.ingest_reddit        # needs REDDIT_CLIENT_ID/SECRET/USER_AGENT in .env
```

News comes from Economic Times and Livemint market feeds (headlines are
matched to tickers via `TICKER_ALIASES` in `app/core/constants.py`) plus
one Google News search per company. Moneycontrol and Business Standard
are not used: their feeds return 403 to automated requests. Reddit logs a
warning and exits cleanly if its credentials aren't set yet.

**Reddit is currently blocked on Reddit's own approval process**, not on
anything in this codebase. Since November 2025, new API apps require
manual approval under Reddit's
["Responsible Builder Policy"](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
before you get credentials — `/prefs/apps` no longer issues them
instantly. Submit that request whenever you get to it; the ingestion
code is already built and tested, so once Reddit approves you and hands
over `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT`,
nothing else needs to change.

### News sentiment (Phase 5)

Every news article is scored with
[DistilRoBERTa fine-tuned on financial news](https://huggingface.co/mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis)
(the default, best in our comparison, see "ML models" below) and with
[FinBERT](https://huggingface.co/ProsusAI/finbert), which users can pick
instead (pretrained, inference only, runs on CPU). Scoring runs
automatically right after each hourly news ingestion, and stores a
`sentiment` field (`label`, `score` from -1 to 1, class `probabilities`,
`model`, `scored_at`) on the article itself for the default model, and
`sentiments.<model>` for the others. For a one-off run:

```bash
cd backend
python -m scripts.score_sentiment      # first run downloads both models (~750 MB) into ml/models/hf_cache/
```

Read endpoints (login required): `GET /api/v1/sentiment` (every tracked
stock) and `GET /api/v1/sentiment/{ticker}` — label counts, average
score, overall label and the latest articles over the last `days`
(default 7). To change the default, set `SENTIMENT_MODEL` in
`backend/.env` to a Hugging Face id or local path; the next run
re-scores every article with it. `SENTIMENT_EXTRA_MODELS` lists the
others users can pick.

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                    # http://localhost:5173
```

Other frontend commands: `npm run build`, `npm run lint`, `npm run test`.

## Environment variables & secrets

Every real secret lives in a `.env` (backend) / `.env.local` (frontend)
file — both are gitignored. Only the corresponding `.env.example` files
are committed, and they must be kept up to date whenever a new variable is
added, so the other person can `cp` it and know exactly what to fill in.
Never commit a real API key, even temporarily.

## Git workflow

Two people, one `main` branch — to avoid stepping on each other:

- `main` stays deployable; don't commit directly to it for anything beyond trivial docs fixes.
- Branch per phase/feature: `phase-<n>-<short-description>` (e.g. `phase-1-market-data-ingestion`) or `fix-<short-description>` for bugfixes.
- Open a PR into `main` even solo — it's a natural point for the other person to skim the diff, and gives you a review trail.
- Commit messages: short imperative summary line (`Add Mongo health check to backend`), body if the "why" isn't obvious from the diff.
- Pull `main` before starting a new branch so you're not building on stale code, especially once you're both touching overlapping phases (e.g. Phase 9 depends on Phases 3–8).

## ML models: comparisons and model choice

For stock prediction, news sentiment and news summaries we compared
several models on the same test data. The best one is the default, and
users can pick any of the others on the instrument page (a "model"
drop-down in the Predict panel and in the News & sentiment section; the
choice is remembered in the browser).

| Feature | Default (best tested) | Other options | Set the default with |
|---|---|---|---|
| Stock prediction | **LSTM + LightGBM average** (4.0.0) | LightGBM (3.0.0) | `PREDICTION_MODEL` |
| News sentiment | **DistilRoBERTa** fine-tuned on financial news | FinBERT | `SENTIMENT_MODEL`, `SENTIMENT_EXTRA_MODELS` |
| News summary | **T5-small** | Extractive (TF-IDF), DistilBART, BART-large, PEGASUS (financial) | `SUMMARIZER_PROVIDER` |

API: `GET /api/v1/models` lists the options per feature (with which is
the default); `/instruments/{id}/prediction`, `/sentiment` and
`/news-summary` take `?model=<key>` (`/news-summary` also
`?sentiment_model=` for its article tags). Without it, the default is
used. Full write-ups, problems found and fixed: `ml/log.md` (Phase 4 Run 5,
Phase 5 comparisons).

### Stock prediction models compared: LSTM + LightGBM

**Papers:** Tian et al., "Stock price prediction based on LSTM and
LightGBM hybrid model", *J. Supercomputing* 2022
([doi:10.1007/s11227-022-04326-5](https://doi.org/10.1007/s11227-022-04326-5));
Huang, "Stock Price Prediction Based on LSTM-LightGBM Fusion Model",
AEMSS 2025 ([Atlantis Press](https://www.atlantis-press.com/proceedings/aemss-25/126011968));
Yu et al., "Gradient Boosting Decision Tree with LSTM for Investment
Prediction" ([arXiv:2505.23084](https://arxiv.org/abs/2505.23084)). They
combine the two models either by **stacking** (LSTM outputs become
LightGBM inputs) or as an **ensemble** (average the predictions); we
tried both.

**Task:** how a stock does against the Nifty 50 over 1 to 504 trading
days: a range (10th–90th percentile) and a chance of beating the index.
**Data:** 173 NSE stocks of every size (the 20 tracked + 153 random,
seed 42), daily prices 2008/2012–2026. **Test:** walk-forward by
calendar year 2020–2025 (each year predicted by models trained only on
earlier data), every 8th trading day, 534,237 test rows; identical rows
for every model. The LSTM reads the last 64 days of 7 daily inputs; it
was trained walk-forward too, so its outputs used by the stacked model
are out of sample. Script: `ml/train_hybrid_lstm_lightgbm.py`; results:
`ml/models/stock_predictor_hybrid/metrics.json`.

**Metrics:** *Pinball loss* (lower is better) scores the whole predicted
range. *Range hit* is how often the real result fell inside the 80%
range (aim: 80%). *Brier* (lower is better) scores the chance of beating
the Nifty. *Beat/lag accuracy* treats "chance above 50%" as a beat call,
and precision, recall and F1 are for that call ("beat"), with macro F1
averaging the beat and lag classes. *Rank corr* is the Spearman
correlation between predicted and real results across stocks on the
same day (higher is better). *Top 5 − bottom 5* is the average real
return gap between the five stocks ranked highest and lowest.

| Horizon | Model | Pinball loss ↓ | Range hit (aim 80%) | Brier ↓ | Beat/lag accuracy | Beat precision | Beat recall | Beat F1 | Macro F1 | Rank corr ↑ | Top 5 − bottom 5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Up to 1 week | **LSTM + LightGBM average (default, 4.0.0)** | 0.00935 | 80.1% | 0.2494 | 52.3% | 0.490 | 0.213 | 0.297 | 0.468 | 0.054 | +0.53% |
| Up to 1 week | LightGBM (option, ≡ 3.0.0) | 0.00938 | 80.7% | 0.2509 | 51.6% | 0.483 | 0.344 | 0.402 | 0.498 | 0.052 | +0.68% |
| Up to 1 week | LSTM alone | 0.00939 | 78.9% | 0.2493 | 52.5% | 0.490 | 0.148 | 0.228 | 0.442 | 0.046 | +0.06% |
| Up to 1 week | Stacked (LSTM outputs into LightGBM) | 0.00947 | 80.7% | 0.2528 | 51.1% | 0.479 | 0.402 | 0.437 | 0.502 | 0.050 | +0.88% |
| Up to 1 week | LightGBM, stacked's shorter history | 0.00947 | 80.8% | 0.2525 | 51.2% | 0.481 | 0.407 | 0.441 | 0.504 | 0.053 | +1.13% |
| Up to 1 week | Volatility only (baseline) | 0.00945 | 79.9% | 0.2493 | 52.8% (always the majority call) | | | | | 0.044 | +0.39% |
| 1 week to 1 month | **LSTM + LightGBM average (default, 4.0.0)** | 0.02133 | 79.8% | 0.2505 | 51.8% | 0.507 | 0.353 | 0.416 | 0.503 | 0.043 | +2.13% |
| 1 week to 1 month | LightGBM (option, ≡ 3.0.0) | 0.02139 | 80.1% | 0.2518 | 51.3% | 0.500 | 0.440 | 0.468 | 0.509 | 0.039 | +2.24% |
| 1 week to 1 month | LSTM alone | 0.02144 | 78.9% | 0.2506 | 51.7% | 0.507 | 0.297 | 0.374 | 0.490 | 0.035 | +0.77% |
| 1 week to 1 month | Stacked (LSTM outputs into LightGBM) | 0.02170 | 80.8% | 0.2549 | 50.3% | 0.490 | 0.504 | 0.497 | 0.502 | 0.030 | +2.06% |
| 1 week to 1 month | LightGBM, stacked's shorter history | 0.02168 | 80.5% | 0.2549 | 50.3% | 0.490 | 0.517 | 0.503 | 0.503 | 0.034 | +1.99% |
| 1 week to 1 month | Volatility only (baseline) | 0.02149 | 79.6% | 0.2499 | 51.3% (always the majority call) | | | | | 0.038 | -0.29% |
| 1 to 6 months | **LSTM + LightGBM average (default, 4.0.0)** | 0.04992 | 79.6% | 0.2507 | 51.6% | 0.537 | 0.491 | 0.513 | 0.516 | 0.029 | +4.93% |
| 1 to 6 months | LightGBM (option, ≡ 3.0.0) | 0.05001 | 80.2% | 0.2522 | 51.5% | 0.530 | 0.572 | 0.550 | 0.511 | 0.021 | +5.51% |
| 1 to 6 months | LSTM alone | 0.05047 | 78.3% | 0.2518 | 50.6% | 0.533 | 0.403 | 0.459 | 0.502 | 0.027 | +1.33% |
| 1 to 6 months | Stacked (LSTM outputs into LightGBM) | 0.05014 | 80.5% | 0.2547 | 50.9% | 0.523 | 0.630 | 0.571 | 0.499 | 0.011 | +1.57% |
| 1 to 6 months | LightGBM, stacked's shorter history | 0.05034 | 80.3% | 0.2558 | 50.7% | 0.520 | 0.657 | 0.580 | 0.491 | 0.020 | +3.14% |
| 1 to 6 months | Volatility only (baseline) | 0.05030 | 79.5% | 0.2502 | 51.9% (always the majority call) | | | | | -0.003 | +2.79% |
| 6 months to 2 years | **LSTM + LightGBM average (default, 4.0.0)** | 0.11444 | 80.9% | 0.2546 | 49.8% | 0.593 | 0.503 | 0.544 | 0.493 | -0.023 | -6.21% |
| 6 months to 2 years | LightGBM (option, ≡ 3.0.0) | 0.11416 | 81.6% | 0.2547 | 51.3% | 0.584 | 0.632 | 0.607 | 0.483 | -0.027 | -10.94% |
| 6 months to 2 years | LSTM alone | 0.11699 | 79.3% | 0.2591 | 48.3% | 0.594 | 0.416 | 0.489 | 0.483 | -0.038 | -2.90% |
| 6 months to 2 years | Stacked (LSTM outputs into LightGBM) | 0.11143 | 80.9% | 0.2489 | 54.8% | 0.589 | 0.800 | 0.679 | 0.460 | -0.018 | -10.08% |
| 6 months to 2 years | LightGBM, stacked's shorter history | 0.11375 | 81.2% | 0.2542 | 53.4% | 0.587 | 0.730 | 0.651 | 0.475 | -0.012 | -9.36% |
| 6 months to 2 years | Volatility only (baseline) | 0.11246 | 82.0% | 0.2456 | 59.6% (always the majority call) | | | | | 0.145 | +70.75% |

**What we found:**
- **The average of LSTM and LightGBM is the best model up to 6 months**:
  lowest pinball loss, better Brier than either tree model and the best
  ranking of stocks (rank correlation 0.054 / 0.043 / 0.029 vs LightGBM's
  0.052 / 0.039 / 0.021). So it is the default. The gain is small:
  about 0.2–0.3% lower pinball loss, and its ranges are a little narrow
  (79.6–80.1% hit vs 80%).
- **Stacking (LSTM outputs as LightGBM inputs) was worse up to 6 months**
  and only helped from 6 months to 2 years, where it is the only model
  to beat the volatility-only pinball loss.
- **No model calls beat or lag reliably**: 48–55% right everywhere, about
  the same as always making the more common call. The averaged model
  calls "beat" less often (beat recall 0.21–0.50), which lowers its beat
  F1 below LightGBM's at every horizon even though its probabilities are
  better (Brier).
- The papers report 10–15% gains on next-day *price levels*, an easy
  target because tomorrow's price is close to today's. On the harder
  target here (excess return over the Nifty) the LSTM adds a few percent
  to a weak signal.
- The volatility-only baseline ranks best from 6 months to 2 years
  (+70.75%) because the more volatile stocks happened to rise most in
  2020–2025; no model learned that.

### Sentiment models compared

**Test sets** (all mapped to negative / neutral / positive):
1. **30 hand-written Indian market headlines**
   (`ml/evaluate_sentiment_on_realistic_news.py`): closest to what the app
   scores; no model saw them.
2. **1,000 financial tweets**, a random sample of the
   `zeroshot/twitter-financial-news-sentiment` validation split; no model
   was trained on it.
3. **1,000 Financial PhraseBank sentences** (Malo et al. 2014). † marks
   models that were trained on PhraseBank, so their scores there are
   inflated; this set is shown because it is the standard benchmark, but
   sets 1 and 2 decide.

Models: `ProsusAI/finbert` (FinBERT, Araci 2019; the previous default),
`mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis`,
`yiyanghkust/finbert-tone`, `ahmedrachid/FinancialBERT-Sentiment-Analysis`,
and `cardiffnlp/twitter-roberta-base-sentiment-latest` (general, not
financial, as a control). Parameters: DistilRoBERTa 82M, the BERT models
110M, Twitter RoBERTa 125M. Speed is texts per second on a laptop CPU (4
threads, batch 32). Script: `ml/compare_sentiment_models.py`; results,
including confusion matrices: `ml/models/sentiment_comparison/metrics.json`.

**30 Indian market headlines**

| Model | Accuracy | Macro precision | Macro recall | Macro F1 | Weighted F1 | F1 neg / neu / pos | Precision neg / neu / pos | Recall neg / neu / pos | Texts/s |
|---|---|---|---|---|---|---|---|---|---|
| FinBERT (option) | 83.3% | 0.814 | 0.777 | 0.785 | 0.826 | 0.92 / 0.60 / 0.83 | 0.92 / 0.75 / 0.77 | 0.92 / 0.50 / 0.91 | 24 |
| FinBERT-tone | 76.7% | 0.769 | 0.781 | 0.756 | 0.775 | 0.82 / 0.67 / 0.78 | 1.00 / 0.56 / 0.75 | 0.69 / 0.83 / 0.82 | 13 |
| **DistilRoBERTa (default)** | 86.7% | 0.852 | 0.833 | 0.840 | 0.864 | 0.92 / 0.73 / 0.87 | 0.92 / 0.80 / 0.83 | 0.92 / 0.67 / 0.91 | 47 |
| FinancialBERT | 73.3% | 0.738 | 0.730 | 0.711 | 0.738 | 0.76 / 0.57 / 0.80 | 1.00 / 0.50 / 0.71 | 0.62 / 0.67 / 0.91 | 12 |
| Twitter RoBERTa (general) | 70.0% | 0.800 | 0.755 | 0.705 | 0.726 | 0.70 / 0.57 / 0.84 | 1.00 / 0.40 / 1.00 | 0.54 / 1.00 / 0.73 | 13 |

**1,000 financial tweets**

| Model | Accuracy | Macro precision | Macro recall | Macro F1 | Weighted F1 | F1 neg / neu / pos | Precision neg / neu / pos | Recall neg / neu / pos | Texts/s |
|---|---|---|---|---|---|---|---|---|---|
| FinBERT (option) | 72.7% | 0.666 | 0.713 | 0.675 | 0.735 | 0.60 / 0.80 / 0.63 | 0.48 / 0.85 / 0.66 | 0.79 / 0.75 / 0.59 | 9 |
| FinBERT-tone | 73.4% | 0.669 | 0.634 | 0.648 | 0.729 | 0.53 / 0.81 / 0.60 | 0.55 / 0.79 / 0.68 | 0.52 / 0.84 / 0.54 | 9 |
| **DistilRoBERTa (default)** | 75.7% | 0.692 | 0.762 | 0.717 | 0.764 | 0.67 / 0.82 / 0.67 | 0.57 / 0.89 / 0.61 | 0.80 / 0.76 / 0.73 | 18 |
| FinancialBERT | 75.2% | 0.719 | 0.644 | 0.673 | 0.744 | 0.62 / 0.83 / 0.57 | 0.75 / 0.78 / 0.62 | 0.53 / 0.87 / 0.53 | 9 |
| Twitter RoBERTa (general) | 71.3% | 0.653 | 0.619 | 0.631 | 0.705 | 0.59 / 0.79 / 0.51 | 0.59 / 0.76 / 0.61 | 0.59 / 0.83 / 0.44 | 9 |

**1,000 PhraseBank sentences**

| Model | Accuracy | Macro precision | Macro recall | Macro F1 | Weighted F1 | F1 neg / neu / pos | Precision neg / neu / pos | Recall neg / neu / pos | Texts/s |
|---|---|---|---|---|---|---|---|---|---|
| FinBERT (option) † | 88.5% | 0.857 | 0.913 | 0.880 | 0.886 | 0.88 / 0.90 / 0.86 | 0.81 / 0.96 / 0.80 | 0.97 / 0.85 / 0.92 | 8 |
| FinBERT-tone | 78.6% | 0.793 | 0.718 | 0.747 | 0.779 | 0.73 / 0.84 / 0.67 | 0.82 / 0.78 / 0.78 | 0.66 / 0.91 / 0.59 | 8 |
| **DistilRoBERTa (default)** † | 83.9% | 0.832 | 0.806 | 0.818 | 0.838 | 0.80 / 0.87 / 0.78 | 0.85 / 0.86 / 0.79 | 0.75 / 0.89 / 0.78 | 16 |
| FinancialBERT † | 95.5% | 0.952 | 0.951 | 0.951 | 0.955 | 0.96 / 0.97 / 0.93 | 0.98 / 0.98 / 0.90 | 0.94 / 0.96 / 0.96 | 7 |
| Twitter RoBERTa (general) | 67.4% | 0.712 | 0.549 | 0.587 | 0.647 | 0.55 / 0.76 / 0.45 | 0.83 / 0.67 / 0.64 | 0.41 / 0.89 / 0.34 | 7 |


**What we found:**
- **DistilRoBERTa is best on both fair sets** (headlines: 86.7% accuracy,
  macro F1 0.840; tweets: 75.7%, macro F1 0.717) and about twice as fast,
  being a smaller, distilled model. So it is the default; FinBERT is the
  option. On the headlines the gap to FinBERT is one headline (26 vs 25
  of 30); the 1,000 tweets carry most of the evidence (+3.0 points of
  accuracy, +0.042 macro F1).
- FinancialBERT shows why PhraseBank can't decide: 95.5% there, but the
  weakest financial model on the headlines.
- Every model calls "TCS board approves ₹18,000 crore share buyback"
  neutral and "Crude oil prices surge past $95" positive.
- The general (non-financial) model is worst on headlines and
  PhraseBank, so financial training matters.

### Summarizers compared

**Test set:** 80 random articles (seed 42) from
[`kdave/Indian_Financial_News`](https://huggingface.co/datasets/kdave/Indian_Financial_News)
(Moneycontrol, Business Today, Financial Express and others), average 736
words, each with a reference summary (average 63 words). The references
look machine-written (lowercase, mostly copied lead sentences), so ROUGE
favours summaries that copy the article's key sentences; the checks that
need no reference count as much.

**Metrics:** *ROUGE-1/2/L* F1 against the reference (the app's own
implementation, `backend/app/services/summarization/evaluation.py`).
*Figures found in article* is the share of numbers in the summary (₹ amounts,
percentages, years) that appear in the article; a figure that doesn't is
made up, the worst error for financial news. *Made-up figure* is the
share of summaries with at least one. *Novel word pairs* is the share of
the summary's word pairs not in the article (0% means copied word for
word). Every summary is cut to the app's 100-word limit. Speed: median
seconds per article through the app's own code, each model run alone
on a laptop CPU (6 threads, `ml/time_summarizers.py`). Script:
`ml/compare_summarizers.py`; results and three example articles with
every model's summary: `ml/models/summarizer_comparison/`.

| Model | Key | Params | ROUGE-1 | ROUGE-2 | ROUGE-L | Figures found in article | Made-up figure | Novel word pairs | Avg words | Seconds per summary |
|---|---|---|---|---|---|---|---|---|---|---|
| **T5-small** (`Falconsai/text_summarization`, default) | `t5-small` | 60M | **0.448** | **0.303** | **0.376** | 99.9% | 1.2% | 5.6% | 51 | 5.6 |
| DistilBART (`sshleifer/distilbart-cnn-12-6`) | `distilbart` | 306M | 0.435 | 0.293 | 0.355 | 98.8% | 1.2% | 6.6% | 50 | 13.2 |
| BART-large (`facebook/bart-large-cnn`) | `bart-large-cnn` | 406M | 0.424 | 0.290 | 0.358 | 99.2% | 2.5% | 6.0% | 41 | 18.4 |
| PEGASUS financial (`human-centered-summarization/financial-summarization-pegasus`) | `pegasus-financial` | 570M | 0.251 | 0.121 | 0.200 | 100% | 0% | 35.9% | 24 | 14.5 |
| Extractive TF-IDF (the previous default) | `extractive` | – | 0.389 | 0.213 | 0.289 | 100% | 0% | 1.6% | 94 | 0.02 |
| First 60 words (baseline, not in the app) | – | – | 0.383 | 0.223 | 0.294 | 100% | 0% | 0% | 54 | – |

**What we found:**
- **T5-small is best on every ROUGE score** and almost never invents a
  figure, while being the smallest and fastest neural model, so it is the
  default. Part of its lead may be style: like the references, it mostly
  copies key sentences.
- DistilBART and BART-large are close behind.
- PEGASUS (financial) writes headline-length summaries (24 words) and
  rewrites the most, so it scores low against 63-word references; that
  is length and style more than quality, but too short for the app.
- Every neural model made up a figure in 1–2.5% of summaries; extractive
  can't (it only copies sentences), which is why it stays an option. It
  is also instant, while the neural models take 6–18 s per summary on a
  CPU (summaries are cached for an hour).
- The app summarizes the top 5 articles at once; the neural models read
  only 512–1,024 tokens, so each article gets an equal share of the input
  (otherwise T5 would only see the first article or two).

Hugging Face models download into `ml/models/hf_cache/` on first use
(DistilRoBERTa ~330 MB, T5-small ~240 MB; BART-large and PEGASUS
1.6–2.3 GB, only when picked). One summarization model is kept in memory
at a time. **Blockchain vault (Phase 10):** its evidence only counts
registered model versions, so after this change register the new defaults
with `python -m scripts.register_models` (it now picks up stock model 4.0.0).

## Current status

Phase 2's exit criteria are met. Track remaining polish items in
[`PHASE_2_EXECUTION_PLAN.md`](./PHASE_2_EXECUTION_PLAN.md) (source of truth).

- **Phase 0** — done. Empty-but-running React app talking to an
  empty-but-running FastAPI backend, backend talking to local MongoDB.
- **Phase 1** — built and tested, partially verified live:
  - Market data (yfinance): fully live — 20-stock universe, ~10k real
    price records in MongoDB, confirmed idempotent on re-runs
  - News: switched from NewsAPI (free plan's ~100 requests/day and
    truncated article text didn't fit hourly ingestion) to Indian
    financial RSS feeds — Economic Times, Livemint, and Google News
    per-company search. No API key or daily quota
  - Reddit (asyncpraw): **paused, not dropped** — pipeline is fully
    built and tested against fabricated data, waiting on Reddit's own
    access approval (see "Data ingestion" above). News is the working
    sentiment source in the meantime; Reddit slots in later with zero
    code changes once approved
  - Scheduler wraps all three into a real background job, retries
    transient failures with backoff, fails fast on permanent ones
- **Phase 2** — exit criteria verified live: register/login, add an
  expense, upload a CSV statement, add a watchlist item with notes, and
  get a rule-based alert when a price crosses a threshold, all confirmed
  end-to-end against the real backend and MongoDB. 39/39 backend tests,
  7/7 frontend tests, `npm run build` green. Refresh tokens, a ticker
  marquee, and a shared modal component library are explicitly deferred
  polish — see `PHASE_2_EXECUTION_PLAN.md` Section 7.
- **Phase 3** — complete. Expense categorizer trained on the **full**
  `mitulshah/transaction-categorization` dataset (Hugging Face, all
  4,501,043 rows), benchmarked against the DFTSen paper (95.3% accuracy
  reported) — **98.7% accuracy / 98.7% macro-F1** on held-out
  template-style test data with a classical TF-IDF + Logistic Regression
  model (Random Forest scored marginally higher but took 47 minutes to
  train vs. 89 seconds, so it wasn't shipped). A stress test against 50
  hand-written realistic examples (real brand names, Indian UPI/NEFT-style
  text) initially measured only **50.0% accuracy** — this dataset's
  synthetic merchant names don't overlap with real ones, so the model had
  no learned signal for brands like Swiggy, Zerodha, or BESCOM. Fixed by
  mixing ~13,466 supplementary rows of real vocabulary (484 hand-curated
  brands + 12,982 real Indian business names from the BharatPOI dataset)
  into training, upweighted via `sample_weight`; a second bug (the fix
  silently failing at full-dataset scale because `TfidfVectorizer`'s
  vocabulary selection ignores sample weighting) was found and fixed
  before shipping. A second pass reviewed the remaining misses for
  patterns, found 3 confident token-collision errors (e.g. "auto" in
  "AUTO DEBIT" pulling toward Transportation instead of meaning
  "automatic payment"), fixed them with trigrams + 14 targeted
  disambiguation rows, and expanded the stress test from 50 to 150
  examples — see `ml/log.md` for the full investigation. **Final
  realistic-text results: 92.0% accuracy, 0.9200 macro-F1** (138/150,
  all originally-targeted token-collision errors fixed; the 12 remaining
  misses are genuine category-boundary confusions, not vocabulary gaps).
  This stress test now runs automatically on every training run and
  reports the full precision/recall/F1 breakdown, not just accuracy
  (`ml/evaluate_on_realistic_examples.py`, wired into
  `ml/train_expense_categorizer.py`) so `metrics.json` always reflects
  it — see `PROJECT_PLAN.md` Phase 3 for the complete writeup. Manual
  entry and CSV import both auto-categorize when no category is given;
  the Budgeting page shows the live accuracy metric and marks
  ML-categorized transactions.

- **Phase 9** — built (AI Investment Advisor). One page that reads every
  module through a common interface (each with its own timeout) and turns
  their results into prioritised actions: overspending, emergency fund,
  debt, goals, investing per plan, rebalancing, concentration and holdings
  to review, each citing the facts and modules behind it. Rules decide; an
  optional LLM only rewords and is rejected if it changes a number. Phase 4
  predictions are used for return ranges only. Implements Phase 10's
  `Advisor` interface for vault trades (B20). Evaluated on 18 hand-written situations (18/18), every
  module knocked out in turn, and every ₹ figure traced. See
  `docs/PHASE_9_ADVISOR.md`.

- **Phase 7** — built (Portfolio Recommendation Engine). An 8-question
  risk profile (the lower of capacity and tolerance), an equity / debt /
  gold split by profile and goal horizon, minimum-variance stock weights
  (Ledoit-Wolf shrunk covariance, stock and sector caps) with a small,
  bounded FinBERT sentiment tilt, and real debt and gold funds from
  mfapi.in. Each recommendation is stored with rupee amounts, reasons and
  a risk summary. A walk-forward backtest (2013-2026) shows lower
  volatility than equal weight out of sample (13.9% vs 16.0%) for slightly
  less return. Educational only, not investment advice. See
  `docs/PHASE_7_PORTFOLIO.md`.

- **Phase 8** — complete (redefined as Smart Budgeting & Goal Planner).
  Users pick expense categories from a fixed list of 13 (Needs / Wants /
  Savings), which replaced the Phase 3 auto-categorizer in the app. Old
  categories are migrated on startup. Budget setup, an Estimated/Actual
  spending pie, a deterministic overspend rules engine (50/30/20,
  per-category ranges, DTI, emergency fund) and a flat vs step-up SIP
  goal planner with an affordability check. An LLM is optional and only
  rewords results. See `docs/PHASE_8_BUDGETING.md`.

See `PHASE_2_EXECUTION_PLAN.md` for remaining Phase 2 polish, and
`PROJECT_PLAN.md` for later phases and ownership.

### Training the expense categorizer (Phase 3)

```bash
cd ml
cp .env.example .env   # needs a free Hugging Face token — see that file
python3 train_expense_categorizer.py
```

Needs a Hugging Face account + accepting the dataset's access conditions
once at [huggingface.co/datasets/mitulshah/transaction-categorization](https://huggingface.co/datasets/mitulshah/transaction-categorization)
(instant, no review), then a token from
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
Writes `vectorizer.joblib` + `model.joblib` (gitignored — regenerate
locally) and `metrics.json` (tracked — the real reported results) to
`ml/models/expense_categorizer/`. As of Phase 8 the app no longer uses
this model (categories are picked by the user); the script is kept as
the Phase 3 record and is not needed to run the app.
