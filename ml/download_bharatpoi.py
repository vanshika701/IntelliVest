"""One-time preparation script: download BharatPOI (real Indian business
names + categories, ODbL 1.0 license, built on OpenStreetMap) and derive
a small, committed supplementary training file from it.

Why: the hand-curated real_merchant_vocabulary.py (484 rows, ~48 brands)
fixed the worst of the out-of-vocabulary problem (see ml/log.md) but is
tiny next to what real bank statements actually contain — thousands of
distinct local businesses, not just national brands. BharatPOI has
509,139 real, named Indian places with a category taxonomy.

Run once (not part of every training run — this is a data-prep step,
cached to ml/data/bharatpoi_supplementary.csv which IS committed since
it's small; the raw ~280MB download is not):

    cd ml
    python3 download_bharatpoi.py

Category mapping decisions (see ml/log.md for the full reasoning):
- "education" (schools/colleges) has no matching category in our 10 —
  excluded rather than force-fit.
- "infrastructure" (water towers, toilets, comms towers) gives generic
  non-merchant names, not realistic transaction text — excluded.
- "Income" cannot be helped by POI data at all — salary isn't a place.
- The rest map onto our 10 categories as documented in _CATEGORY_MAP.
"""

import os
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ML_DIR = Path(__file__).parent
DATA_DIR = ML_DIR / "data"
RAW_DIR = DATA_DIR / "raw"  # gitignored — the big download lives here
OUTPUT_PATH = DATA_DIR / "bharatpoi_supplementary.csv"  # small, committed

KAGGLE_DATASET_REF = "mansiaggarwal88/bharatpoi-india-places-intelligence-dataset"

# BharatPOI (category, subcategory) -> our Phase 3 category. Anything not
# listed here is deliberately excluded (see module docstring).
_CATEGORY_MAP: dict[str, str] = {
    # food -> Food & Dining
    "restaurant": "Food & Dining",
    "bakery": "Food & Dining",
    "cafe": "Food & Dining",
    "fast_food": "Food & Dining",
    "bar": "Food & Dining",
    "food_court": "Food & Dining",
    # healthcare -> Healthcare & Medical
    "hospital": "Healthcare & Medical",
    "clinic": "Healthcare & Medical",
    "dentist": "Healthcare & Medical",
    "doctors": "Healthcare & Medical",
    "pharmacy": "Healthcare & Medical",
    "veterinary": "Healthcare & Medical",
    # retail (+ marketplace from "community") -> Shopping & Retail
    "clothes": "Shopping & Retail",
    "supermarket": "Shopping & Retail",
    "electronics": "Shopping & Retail",
    "general_store": "Shopping & Retail",
    "stationery": "Shopping & Retail",
    "hairdresser": "Shopping & Retail",
    "jeweller": "Shopping & Retail",
    "convenience": "Shopping & Retail",
    "greengrocer": "Shopping & Retail",
    "hardware": "Shopping & Retail",
    "beauty": "Shopping & Retail",
    "butcher": "Shopping & Retail",
    "car_dealership": "Shopping & Retail",
    "furniture_shop": "Shopping & Retail",
    "shoes": "Shopping & Retail",
    "mall": "Shopping & Retail",
    "department_store": "Shopping & Retail",
    "bookshop": "Shopping & Retail",
    "beverages": "Shopping & Retail",
    "travel_agent": "Shopping & Retail",
    "gift_shop": "Shopping & Retail",
    "chemist": "Shopping & Retail",
    "optician": "Shopping & Retail",
    "sports_shop": "Shopping & Retail",
    "bicycle_shop": "Shopping & Retail",
    "florist": "Shopping & Retail",
    "kiosk": "Shopping & Retail",
    "laundry": "Shopping & Retail",
    "marketplace": "Shopping & Retail",
    # finance -> Financial Services
    "bank": "Financial Services",
    "atm": "Financial Services",
    # government -> Government & Legal
    "post_office": "Government & Legal",
    "police": "Government & Legal",
    "fire_station": "Government & Legal",
    "courthouse": "Government & Legal",
    "prison": "Government & Legal",
    "consulate": "Government & Legal",
    "town_hall": "Government & Legal",
    # recreation + tourism + accommodation -> Entertainment & Recreation
    "playground": "Entertainment & Recreation",
    "park": "Entertainment & Recreation",
    "fitness_centre": "Entertainment & Recreation",
    "sports_centre": "Entertainment & Recreation",
    "sports_pitch": "Entertainment & Recreation",
    "stadium": "Entertainment & Recreation",
    "artwork": "Entertainment & Recreation",
    "theatre": "Entertainment & Recreation",
    "attraction": "Entertainment & Recreation",
    "cinema": "Entertainment & Recreation",
    "memorial": "Entertainment & Recreation",
    "tourist_info": "Entertainment & Recreation",
    "viewpoint": "Entertainment & Recreation",
    "arts_centre": "Entertainment & Recreation",
    "historic_ruins": "Entertainment & Recreation",
    "monument": "Entertainment & Recreation",
    "museum": "Entertainment & Recreation",
    "theme_park": "Entertainment & Recreation",
    "hotel": "Entertainment & Recreation",
    "hostel": "Entertainment & Recreation",
    "guesthouse": "Entertainment & Recreation",
    "motel": "Entertainment & Recreation",
    "camp_site": "Entertainment & Recreation",
    "chalet": "Entertainment & Recreation",
    "wilderness_hut": "Entertainment & Recreation",
    # transport -> Transportation
    "car_wash": "Transportation",
    "bicycle_rental": "Transportation",
    # community (religious/spiritual only) -> Charity & Donations
    "wayside_shrine": "Charity & Donations",
    "wayside_cross": "Charity & Donations",
}

MAX_ROWS_PER_CATEGORY = 2000
FORMAT_TEMPLATES = [
    "{name}",
    "POS DEBIT {name_upper}",
    "UPI-{name_upper}",
    "{name} PAYMENT",
    "NEFT-{name_upper}",
]


def _download_and_extract() -> Path:
    """Download the BharatPOI zip via the Kaggle API and extract the
    full CSV. Cached — skips re-downloading if already present."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RAW_DIR / "bharatpoi.csv"
    if csv_path.exists():
        print(f"Using cached {csv_path}")
        return csv_path

    token = os.environ.get("KAGGLE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "KAGGLE_API_TOKEN not set. Copy ml/.env.example to ml/.env and "
            "fill in a Kaggle API token (Account settings -> Create New Token)."
        )

    print(f"Downloading {KAGGLE_DATASET_REF} from Kaggle...")
    url = f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_DATASET_REF}"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=300)
    response.raise_for_status()

    zip_path = RAW_DIR / "bharatpoi.zip"
    zip_path.write_bytes(response.content)
    print(f"Downloaded {len(response.content):,} bytes, extracting bharatpoi.csv...")

    with zipfile.ZipFile(zip_path) as zf:
        zf.extract("bharatpoi.csv", RAW_DIR)
    zip_path.unlink()  # the extracted CSV is all we need going forward
    return csv_path


def _clean_name(name: str) -> str:
    """Light cleanup — collapse whitespace, drop stray punctuation noise
    that appears in some OSM-sourced names."""
    return re.sub(r"\s+", " ", name).strip()


def build_supplementary_dataset() -> pd.DataFrame:
    csv_path = _download_and_extract()

    print("Loading and filtering BharatPOI...")
    df = pd.read_csv(csv_path, usecols=["name_ascii", "has_name", "subcategory"])
    df = df[df["has_name"] & df["name_ascii"].notna()]
    df["our_category"] = df["subcategory"].map(_CATEGORY_MAP)
    df = df.dropna(subset=["our_category"])
    df["name_ascii"] = df["name_ascii"].apply(_clean_name)
    df = df[df["name_ascii"].str.len() >= 3]
    df = df.drop_duplicates(subset=["name_ascii", "our_category"])

    print(f"{len(df):,} usable rows after filtering + deduplication:")
    print(df["our_category"].value_counts())

    # Explicit loop rather than groupby().apply() — pandas 3.x's apply()
    # drops the grouping column by default (hit this same bug in
    # train_expense_categorizer.py; a plain loop sidesteps it entirely).
    sampled_parts = [
        group.sample(n=min(MAX_ROWS_PER_CATEGORY, len(group)), random_state=42)
        for _, group in df.groupby("our_category")
    ]
    sampled = pd.concat(sampled_parts, ignore_index=True)

    rows = []
    for i, row in enumerate(sampled.itertuples()):
        template = FORMAT_TEMPLATES[i % len(FORMAT_TEMPLATES)]
        description = template.format(name=row.name_ascii, name_upper=row.name_ascii.upper())
        rows.append((description, row.our_category))

    return pd.DataFrame(rows, columns=["transaction_description", "category"])


def main() -> None:
    load_dotenv(ML_DIR / ".env")
    result = build_supplementary_dataset()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(result):,} supplementary rows to {OUTPUT_PATH}")
    print(result["category"].value_counts())


if __name__ == "__main__":
    main()
