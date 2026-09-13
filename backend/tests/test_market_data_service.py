"""Unit test — exercises the cleaning logic alone, with a fabricated
DataFrame instead of a real yfinance call. This is the pattern for
testing transformation logic: no network, no database, just input -> output.
"""

import pandas as pd

from app.services.market_data_service import clean_history


def test_clean_history_normalizes_timezone_and_drops_incomplete_rows() -> None:
    index = pd.DatetimeIndex(
        ["2026-01-01", "2026-01-02"], tz="Asia/Kolkata", name="Date"
    )
    history = pd.DataFrame(
        {
            "Open": [100.0, 200.0],
            "High": [101.0, 201.0],
            "Low": [99.0, 199.0],
            "Close": [100.5, None],  # incomplete row — should get dropped
            "Volume": [1000, 2000],
        },
        index=index,
    )

    records = clean_history("RELIANCE.NS", history)

    assert len(records) == 1
    record = records[0]
    assert record["ticker"] == "RELIANCE.NS"
    assert record["date"].tzinfo is not None
    assert record["date"].utcoffset().total_seconds() == 0  # normalized to UTC
    assert record["open"] == 100.0
    assert record["volume"] == 1000
    assert isinstance(record["volume"], int)
