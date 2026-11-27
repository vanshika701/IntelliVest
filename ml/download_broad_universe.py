"""Pick and download the wider training set for the stock predictor.

    .venv/Scripts/python ml/download_broad_universe.py

Model 2.0.0 learned from 20 of today's largest companies. Their dips
recovered, so it learned that dips recover. This adds about 180 other NSE
stocks of every size, picked at random (fixed seed) from NSE's equity list
among those that:

- have prices back to at least 2012 (enough years for the walk-forward test)
- traded at least Rs 2 crore a day (median, last year), so prices are real
  trades and not thin, circuit-bound quotes

Still survivors: Yahoo has no prices for delisted companies, so stocks that
collapsed and left the exchange (Jet Airways, DHFL) can't be included.

Outputs:
- ml/data/broad_universe.csv: the chosen tickers (tracked)
- ml/data/raw/broad_history.parquet: their daily prices (gitignored)
"""

import csv
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from app.core.constants import STOCK_UNIVERSE
from app.services.stock_listing import LISTING_PATH

DATA_START = "2008-03-01"
EXTRA_STOCKS = 180
CANDIDATES = 600
SEED = 42
MIN_FIRST_DATE = pd.Timestamp("2012-01-01")
MIN_DAILY_VALUE = 2e7  # Rs 2 crore
BATCH = 100
UNIVERSE_PATH = ML_DIR / "data" / "broad_universe.csv"
HISTORY_PATH = ML_DIR / "data" / "raw" / "broad_history.parquet"


def download(tickers: list[str]) -> pd.DataFrame:
    frames = []
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i : i + BATCH]
        raw = yf.download(
            batch,
            start=DATA_START,
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
            timeout=60,
        )
        for ticker in batch:
            if ticker not in raw.columns.get_level_values(0):
                continue
            f = raw[ticker].dropna(subset=["Close"])
            f = f[f["Close"] > 0]
            if f.empty:
                continue
            frames.append(
                pd.DataFrame(
                    {
                        "ticker": ticker,
                        "date": pd.to_datetime([d.date() for d in f.index]),
                        "close": f["Close"].to_numpy(),
                        "volume": f["Volume"].to_numpy(),
                    }
                )
            )
        print(f"  downloaded {min(i + BATCH, len(tickers))}/{len(tickers)}")
    return pd.concat(frames, ignore_index=True)


def eligible(prices: pd.DataFrame) -> list[str]:
    keep = []
    for ticker, g in prices.groupby("ticker"):
        if g["date"].min() > MIN_FIRST_DATE:
            continue
        recent = g.tail(250)
        if np.median(recent["close"] * recent["volume"]) >= MIN_DAILY_VALUE:
            keep.append(ticker)
    return keep


def main() -> None:
    with LISTING_PATH.open(encoding="utf-8") as f:
        listed = [r["symbol"] + ".NS" for r in csv.DictReader(f) if r["series"] == "EQ"]
    pool = sorted(set(listed) - set(STOCK_UNIVERSE))
    candidates = random.Random(SEED).sample(pool, CANDIDATES)
    print(
        f"Downloading {len(candidates)} random candidates + {len(STOCK_UNIVERSE)} tracked..."
    )
    prices = download(candidates + STOCK_UNIVERSE)

    ok = [t for t in eligible(prices) if t not in STOCK_UNIVERSE]
    # Keep the random order, so the pick doesn't depend on download order.
    order = {t: i for i, t in enumerate(candidates)}
    chosen = sorted(ok, key=order.__getitem__)[:EXTRA_STOCKS]
    universe = sorted(STOCK_UNIVERSE) + sorted(chosen)
    print(
        f"{len(ok)} candidates passed the filters; using {len(chosen)} + {len(STOCK_UNIVERSE)} tracked"
    )

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    prices[prices["ticker"].isin(universe)].to_parquet(HISTORY_PATH, index=False)
    with UNIVERSE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "tracked"])
        writer.writerows([t, t in STOCK_UNIVERSE] for t in universe)
    print(f"Wrote {UNIVERSE_PATH} and {HISTORY_PATH}")


if __name__ == "__main__":
    main()
