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
    "TATAMOTORS.NS",  # Auto
    "SUNPHARMA.NS",  # Pharma
    "TITAN.NS",  # Consumer goods
    "ASIANPAINT.NS",  # Consumer goods
    "LT.NS",  # Infrastructure
    "ULTRACEMCO.NS",  # Cement/materials
]
