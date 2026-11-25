# Phase 6: Sector-Level Market Intelligence

Built 2026-11-25.

- [x] Sector map for the 20 tracked stocks, 9 sectors (`SECTORS` in `backend/app/core/constants.py`)
- [x] Price rollups: 1 day, 1 week, 1 month and 3 month change, trend, advancers/decliners, index line
- [x] Sentiment rollups: average FinBERT score, label and article counts over 7 days
- [x] Recomputed after each price and news job and at startup; requests only read `sector_snapshots`
- [x] `GET /api/v1/sectors` and `/api/v1/sectors/{id}`; Sectors page
- [ ] Add Phase 4 predictions to the rollup once they are stored

**Rules:** every stock counts equally. Trend is up or down when the 1 month (21 trading days) change
passes 2%. A label needs at least 3 articles, and a story about two stocks in a sector counts once.
Stocks whose prices are over 7 days behind their sector are left out.

**Limits:** Energy, Financial Services and Pharma hold one stock each, so they mirror that stock.

Code: `backend/app/services/sector_service.py`, `frontend/src/pages/SectorsPage.tsx`.
Tests: `backend/tests/test_sectors.py`, `frontend/src/pages/market-pages.test.tsx`.
