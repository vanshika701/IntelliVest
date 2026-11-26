"""Refresh app/data/nse_equities.csv from NSE's list of every listed equity.

    cd backend
    python -m scripts.update_nse_listing

NSE publishes the list at EQUITY_L.csv (symbol, company name, series, ISIN,
...). Only those four columns are kept. Run it now and then to pick up new
listings; the app reads the committed file and never calls NSE itself.
"""

import csv
import io
import sys

import httpx

from app.services.stock_listing import LISTING_PATH

URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def main() -> None:
    # NSE refuses requests without a browser-like User-Agent.
    response = httpx.get(
        URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True
    )
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    rows = []
    for row in reader:
        row = {k.strip(): (v or "").strip() for k, v in row.items()}
        if row.get("SYMBOL") and row.get("NAME OF COMPANY"):
            rows.append(
                [
                    row["SYMBOL"],
                    row["NAME OF COMPANY"],
                    row.get("SERIES", ""),
                    row.get("ISIN NUMBER", ""),
                ]
            )
    if len(rows) < 1000:
        sys.exit(f"Only {len(rows)} rows; NSE's format may have changed. File not written.")
    rows.sort()
    with LISTING_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "name", "series", "isin"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} listings to {LISTING_PATH}")


if __name__ == "__main__":
    main()
