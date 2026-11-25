"""What to search when an instrument has no news of its own.

Stocks use their sector. Funds are rarely in the news by name, so they use
what they hold (gold, the Nifty IT index, small caps...), read from the
scheme's name and category.
"""

import re
from dataclasses import dataclass

from app.core.constants import SECTORS, TICKER_TO_SECTOR

_FOREIGN = re.compile(
    r"nikkei|\bTSE\b|eurozone|wall street|nasdaq|\bNYSE\b|coreweave|a\.m\. ET|quant.rat(ed|ings?)|\bTSX\b|hang seng|"
    r"\bkospi\b|pakistan|US (treasury|yields|stocks)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Topic:
    name: str
    phrases: tuple[str, ...]  # each searched as an exact phrase
    title_terms: str  # regex: a headline must match it
    sector: str | None = None

    foreign_ok: bool = False

    def matches(self, title: str, description: str | None = None) -> bool:
        if not self.foreign_ok and _FOREIGN.search(f"{title} {description or ''}"):
            return False
        # Case-sensitive for IT, so the word "it" doesn't count.
        flags = 0 if self.sector == "it" else re.IGNORECASE
        return re.search(rf"(?<!\w)(?:{self.title_terms})(?!\w)", title, flags) is not None


_SECTOR_TOPICS: dict[str, Topic] = {
    "auto": Topic("Auto", ("auto stocks", "Nifty Auto"), r"auto stocks?|auto sector|auto sales|nifty auto|carmakers?|automakers?", "auto"),
    "banking": Topic("Banking", ("bank stocks", "Nifty Bank"), r"bank stocks?|banking stocks?|bank nifty|nifty bank|banks|PSU banks?|banking sector", "banking"),
    "consumer": Topic("Consumer Goods", ("consumer durables stocks", "jewellery stocks"), r"consumer|jewellery|paints?|durables?", "consumer"),
    "energy": Topic("Energy", ("energy stocks", "oil and gas stocks"), r"energy|oil|gas|refin\w+|power stocks?", "energy"),
    "financial_services": Topic("Financial Services", ("NBFC stocks", "Nifty Financial Services"), r"NBFCs?|financial services|financials|lenders?", "financial_services"),
    "fmcg": Topic("FMCG", ("FMCG stocks", "Nifty FMCG"), r"FMCG|consumer staples", "fmcg"),
    "infrastructure": Topic("Infrastructure", ("infrastructure stocks", "cement stocks"), r"infra\w*|cement|capital goods|construction", "infrastructure"),
    "it": Topic("IT", ("IT stocks", "Nifty IT"), r"IT|[Tt]ech|[Tt]echnology", "it"),
    "pharma": Topic("Pharma", ("pharma stocks", "Nifty Pharma"), r"pharma\w*|drugmakers?|healthcare", "pharma"),
}

_GOLD = Topic("Gold", ("gold price", "gold ETF"), r"gold|bullion|precious metals?")
_SILVER = Topic("Silver", ("silver price", "silver ETF"), r"silver|bullion|precious metals?")
_METALS = Topic("Precious Metals", ("gold silver price", "bullion"), r"gold|silver|bullion|precious metals?")
_MARKET = Topic("Indian Stock Market", ("Nifty 50", "Sensex"), r"nifty|sensex|stock markets?|dalal street|FIIs?|equit\w+")

# First match on the fund's name wins, so narrow themes come before broad ones.
_FUND_RULES: list[tuple[str, Topic]] = [
    (r"gold.*silver|silver.*gold|precious metal|multi.?commodit", _METALS),
    (r"\bgold\b", _GOLD),
    (r"\bsilver\b", _SILVER),
    (r"\bIT\b|technolog|digital", _SECTOR_TOPICS["it"]),
    (r"pharma|health", _SECTOR_TOPICS["pharma"]),
    (r"\bbank(?!ing (?:&|and) psu)(?!ing and psu)", _SECTOR_TOPICS["banking"]),
    (r"financial services|nbfc", _SECTOR_TOPICS["financial_services"]),
    (r"fmcg", _SECTOR_TOPICS["fmcg"]),
    (r"consum", _SECTOR_TOPICS["consumer"]),
    (r"\bauto|mobility|transport", _SECTOR_TOPICS["auto"]),
    (r"energy|power|\boil\b", _SECTOR_TOPICS["energy"]),
    (r"infra", _SECTOR_TOPICS["infrastructure"]),
    (r"\bmetal", Topic("Metals", ("metal stocks", "Nifty Metal"), r"metals?|steel|aluminium|copper")),
    (r"defen[cs]e", Topic("Defence", ("defence stocks", "Nifty Defence"), r"defen[cs]e")),
    (r"real(ty| estate)", Topic("Real Estate", ("realty stocks", "Nifty Realty"), r"realty|real estate|housing")),
    (r"\bpsu\b|cpse", Topic("PSU", ("PSU stocks", "public sector stocks"), r"PSUs?|public sector")),
    (r"nasdaq|s&p 500|\bus\b|global|overseas|world", Topic("Global Markets", ("Wall Street", "Nasdaq"), r"nasdaq|wall street|S&P|dow|US stocks?|global", foreign_ok=True)),
    (r"small.?cap", Topic("Small Caps", ("smallcap stocks", "small cap stocks"), r"small.?caps?")),
    (r"mid.?cap", Topic("Mid Caps", ("midcap stocks", "mid cap stocks"), r"mid.?caps?")),
    (
        r"liquid|overnight|money market|gilt|\bbond|debt|duration|credit risk|banking (?:&|and) psu",
        Topic("Bonds & Interest Rates", ("RBI repo rate", "Indian bond yields", "government securities"), r"RBI|repo|gilts?|G-?secs?|indian? (bonds?|yields?)"),
    ),
]
# "Banking & PSU" funds hold bonds, not bank shares.
_DEBT_NAME = re.compile(r"banking\s*(&|and)\s*psu", re.IGNORECASE)


def topic_for_stock(ticker: str) -> Topic | None:
    sector = TICKER_TO_SECTOR.get(ticker)
    return _SECTOR_TOPICS.get(sector) if sector in SECTORS else None


def topic_for_fund(name: str, category: str | None) -> Topic:
    fund = name.split(" - ")[0]
    if _DEBT_NAME.search(fund):
        return _FUND_RULES[-1][1]
    for text in (fund, category or ""):
        # The category's own words ("Debt Scheme", "Small Cap Fund") are a second try.
        for pattern, topic in _FUND_RULES:
            # Scheme names are often all caps, so "IT" only counts as a whole word.
            if re.search(pattern, text, 0 if r"\bIT\b" in pattern and not text.isupper() else re.IGNORECASE):
                return topic
    return _MARKET
