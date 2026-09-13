"""App-wide constants that aren't secrets/environment config.

These differ from Settings (core/config.py) in kind: they're not
per-environment values you'd override with an env var, they're product
decisions (which stocks we track) that happen to live in code so they're
version-controlled and reviewable like everything else.
"""

# Starting stock universe: 20 large-cap NSE-listed stocks spanning
# several sectors, using yfinance's ".NS" suffix convention. Deliberately
# small and fixed for now (per the plan: easier to debug/evaluate a small,
# well-understood universe before scaling up in Phase 11).
STOCK_UNIVERSE: list[str] = [
    "RELIANCE.NS",  # Energy / Conglomerate
    "TCS.NS",  # IT
    "INFY.NS",  # IT
    "WIPRO.NS",  # IT
    "HDFCBANK.NS",  # Banking
    "ICICIBANK.NS",  # Banking
    "SBIN.NS",  # Banking
    "KOTAKBANK.NS",  # Banking
    "AXISBANK.NS",  # Banking
    "BAJFINANCE.NS",  # Financial services
    "HINDUNILVR.NS",  # FMCG
    "ITC.NS",  # FMCG
    "NESTLEIND.NS",  # FMCG
    "MARUTI.NS",  # Auto
    "TMPV.NS",  # Auto (Tata Motors Passenger Vehicles, post-demerger — old TATAMOTORS.NS is delisted)
    "SUNPHARMA.NS",  # Pharma
    "TITAN.NS",  # Consumer goods
    "ASIANPAINT.NS",  # Consumer goods
    "LT.NS",  # Infrastructure
    "ULTRACEMCO.NS",  # Cement/materials
]

# NewsAPI searches by keyword, not ticker symbol — this maps each ticker
# to the search term that actually finds its news.
TICKER_TO_COMPANY_NAME: dict[str, str] = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "WIPRO.NS": "Wipro",
    "HDFCBANK.NS": "HDFC Bank",
    "ICICIBANK.NS": "ICICI Bank",
    "SBIN.NS": "State Bank of India",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "AXISBANK.NS": "Axis Bank",
    "BAJFINANCE.NS": "Bajaj Finance",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "ITC.NS": "ITC Limited",
    "NESTLEIND.NS": "Nestle India",
    "MARUTI.NS": "Maruti Suzuki",
    "TMPV.NS": "Tata Motors Passenger Vehicles",
    "SUNPHARMA.NS": "Sun Pharma",
    "TITAN.NS": "Titan Company",
    "ASIANPAINT.NS": "Asian Paints",
    "LT.NS": "Larsen & Toubro",
    "ULTRACEMCO.NS": "UltraTech Cement",
}

# Reddit ingestion pulls general finance-discussion posts from these
# subreddits (not per-ticker like news — this is broad market sentiment,
# not company-specific search).
FINANCE_SUBREDDITS: list[str] = [
    "IndianStreetBets",
    "IndiaInvestments",
    "stocks",
    "wallstreetbets",
]
