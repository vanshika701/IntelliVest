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

# News search works by keyword, not ticker symbol — this maps each ticker
# to the search term that actually finds its news (used for the per-company
# Google News feed).
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

# Phase 6 sector map: id -> (display name, tickers). Every tracked stock is in
# exactly one sector (tests/test_sectors.py checks this).
SECTORS: dict[str, tuple[str, list[str]]] = {
    "auto": ("Auto", ["MARUTI.NS", "TMPV.NS"]),
    "banking": ("Banking", ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]),
    "consumer": ("Consumer Goods", ["TITAN.NS", "ASIANPAINT.NS"]),
    "energy": ("Energy", ["RELIANCE.NS"]),
    "financial_services": ("Financial Services", ["BAJFINANCE.NS"]),
    "fmcg": ("FMCG", ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS"]),
    "infrastructure": ("Infrastructure & Materials", ["LT.NS", "ULTRACEMCO.NS"]),
    "it": ("IT", ["TCS.NS", "INFY.NS", "WIPRO.NS"]),
    "pharma": ("Pharma", ["SUNPHARMA.NS"]),
}

TICKER_TO_SECTOR: dict[str, str] = {t: sid for sid, (_, tickers) in SECTORS.items() for t in tickers}

# Google News searches for sector-wide headlines (company news is separate).
SECTOR_NEWS_QUERIES: dict[str, str] = {
    "auto": '"auto sector" OR "auto stocks" OR "Nifty Auto"',
    "banking": '"banking sector" OR "bank stocks" OR "Nifty Bank"',
    "consumer": '"consumer durables" OR "consumer stocks" OR "jewellery stocks" OR "paint stocks"',
    "energy": '"energy stocks" OR "oil and gas stocks" OR "Nifty Energy"',
    "financial_services": '"NBFC stocks" OR "NBFC sector" OR "Nifty Financial Services"',
    "fmcg": '"FMCG sector" OR "FMCG stocks" OR "Nifty FMCG"',
    "infrastructure": '"infrastructure stocks" OR "infra stocks" OR "cement stocks" OR "cement sector"',
    "it": '"IT stocks" OR "IT sector" OR "Nifty IT"',
    "pharma": '"pharma sector" OR "pharma stocks" OR "Nifty Pharma"',
}

# A found headline must name its sector; search engines also match page text.
# Regex fragments, whole words, case-insensitive.
SECTOR_HEADLINE_TERMS: dict[str, str] = {
    "auto": r"autos?|automobiles?|automakers?|carmakers?|two-wheelers?|passenger vehicles?|EVs?",
    "banking": r"banks?|banking|bankex|PSBs?",
    "consumer": r"consumer|jewellery|jewellers?|paints?|durables?",
    "energy": r"energy|oil|gas|power|refiners?|renewables?|solar",
    "financial_services": r"NBFCs?|financials?|financial services|fintech|microfinance|lenders?",
    "fmcg": r"FMCG|consumer staples|packaged foods?",
    "infrastructure": r"infra|infrastructure|cement|capital goods|construction",
    "it": r"IT|I\.T\.|[Tt]ech|[Tt]echnology|[Ss]oftware",
    "pharma": r"pharma|pharmaceuticals?|drugmakers?|drug makers?|healthcare",
}

# How headlines actually refer to each company, used to tag articles from
# the general market feeds with tickers. Values are regex fragments
# (matched case-insensitively, as whole words); the negative lookaheads
# keep group companies that are separately listed from being misattributed
# (e.g. "SBI Life" is not SBIN, "L&T Finance" is not LT).
TICKER_ALIASES: dict[str, list[str]] = {
    "RELIANCE.NS": [
        r"Reliance(?! (?:Power|Infra|Infrastructure|Capital|Communications|Home|Naval))",
        r"RIL",
    ],
    "TCS.NS": [r"TCS", r"Tata Consultancy"],
    "INFY.NS": [r"Infosys"],
    "WIPRO.NS": [r"Wipro"],
    "HDFCBANK.NS": [r"HDFC Bank"],
    "ICICIBANK.NS": [r"ICICI Bank"],
    "SBIN.NS": [r"SBI(?! (?:Life|Card|Cards|Mutual|MF|General))", r"State Bank of India"],
    "KOTAKBANK.NS": [r"Kotak Mahindra Bank", r"Kotak Bank"],
    "AXISBANK.NS": [r"Axis Bank"],
    "BAJFINANCE.NS": [r"Bajaj Finance"],
    "HINDUNILVR.NS": [r"Hindustan Unilever", r"HUL"],
    "ITC.NS": [r"ITC(?! Hotels)"],
    "NESTLEIND.NS": [r"Nestl[eé] India"],
    "MARUTI.NS": [r"Maruti"],
    "TMPV.NS": [r"Tata Motors Passenger Vehicles", r"Tata Motors PV", r"TMPV"],
    "SUNPHARMA.NS": [r"Sun Pharma(?:ceutical)?"],
    "TITAN.NS": [r"Titan"],
    "ASIANPAINT.NS": [r"Asian Paints"],
    "LT.NS": [r"Larsen & Toubro", r"Larsen and Toubro", r"L&T(?! (?:Finance|Technology|Tech))"],
    "ULTRACEMCO.NS": [r"UltraTech"],
}

# General Indian market news feeds (publisher name, RSS URL). Moneycontrol
# and Business Standard were left out deliberately: their feeds return 403
# to automated requests.
NEWS_RSS_FEEDS: list[tuple[str, str]] = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms"),
    ("Livemint", "https://www.livemint.com/rss/markets"),
    ("Livemint", "https://www.livemint.com/rss/companies"),
]

# Reddit ingestion pulls general finance-discussion posts from these
# subreddits (not per-ticker like news — this is broad market sentiment,
# not company-specific search).
FINANCE_SUBREDDITS: list[str] = [
    "IndianStreetBets",
    "IndiaInvestments",
    "stocks",
    "wallstreetbets",
]
