"""Every NSE equity is searchable; the 20 tracked stocks stay first on ties."""

from app.core.constants import STOCK_UNIVERSE
from app.services import stock_listing
from app.services.instrument_service import InstrumentNotFound, parse_instrument_id


def test_listing_covers_nse_and_every_tracked_stock() -> None:
    assert stock_listing.is_listed("COALINDIA.NS") and not stock_listing.is_tracked("COALINDIA.NS")
    assert all(stock_listing.is_listed(t) and stock_listing.is_tracked(t) for t in STOCK_UNIVERSE)
    assert stock_listing.company_name("COALINDIA.NS") == "Coal India"
    assert stock_listing.company_name("TCS.NS") == "Tata Consultancy Services"


def test_search_ranks_exact_symbol_then_prefix_then_words() -> None:
    assert stock_listing.search("coalindia", 5)[0][0] == "COALINDIA.NS"
    assert stock_listing.search("coal", 5)[0] == ("COALINDIA.NS", "Coal India")
    assert ("STLTECH.NS", "Sterlite Technologies") in stock_listing.search("sterlite", 5)
    assert stock_listing.search("hdfc", 5)[0][0] == "HDFCBANK.NS"  # tracked first on a tie
    assert stock_listing.search("   ", 5) == []
    assert len(stock_listing.search("a", 8)) == 8
    # "old" may start a word, never sit inside one like "Gold".
    assert all(
        " old" in f" {name.lower()}" or ticker.lower().startswith("old")
        for ticker, name in stock_listing.search("old", 20)
    )


def test_any_listed_stock_parses_but_unknown_ones_do_not() -> None:
    assert parse_instrument_id("stock-VEDL.NS") == ("stock", "VEDL.NS")
    for bad in ("stock-NOTAREALCO.NS", "stock-VEDL", "stock-"):
        try:
            parse_instrument_id(bad)
        except InstrumentNotFound:
            continue
        raise AssertionError(bad)
