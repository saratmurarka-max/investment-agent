"""
Fetches and caches the NSE India equity list.

Source: https://archives.nseindia.com/content/equities/EQUITY_L.csv

Strategy:
- On first request, return the built-in fallback list IMMEDIATELY (no waiting).
- Kick off a background task to fetch the full NSE list.
- Once fetched, all subsequent searches use the full ~2000+ stock list.
- Cache refreshes every 24 hours.
"""

import asyncio
import csv
import io
import logging
import time
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

NSE_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_TTL_SECONDS = 86_400  # 24 hours

_cache: list[dict] = []
_cache_time: float = 0.0
_fetch_in_progress: bool = False


class StockEntry(TypedDict):
    symbol: str   # e.g. RELIANCE
    ticker: str   # e.g. RELIANCE.NS
    name: str     # e.g. Reliance Industries Limited


async def _fetch_nse_csv() -> list[StockEntry]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,*/*",
        "Referer": "https://www.nseindia.com/",
    }
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        resp = await client.get(NSE_CSV_URL, headers=headers)
        resp.raise_for_status()
        text = resp.text

    reader = csv.DictReader(io.StringIO(text))
    stocks: list[StockEntry] = []
    for row in reader:
        symbol = row.get("SYMBOL", "").strip()
        name = row.get("NAME OF COMPANY", "").strip()
        if symbol:
            stocks.append({"symbol": symbol, "ticker": f"{symbol}.NS", "name": name})
    return stocks


async def _refresh_cache_background() -> None:
    """Run in background — never blocks callers."""
    global _cache, _cache_time, _fetch_in_progress
    if _fetch_in_progress:
        return
    _fetch_in_progress = True
    try:
        logger.info("Fetching NSE equity list in background...")
        stocks = await _fetch_nse_csv()
        _cache = stocks
        _cache_time = time.time()
        logger.info(f"NSE cache updated: {len(stocks)} stocks loaded.")
    except Exception as e:
        logger.warning(f"NSE fetch failed: {e}. Keeping existing cache ({len(_cache)} stocks).")
    finally:
        _fetch_in_progress = False


def get_nse_stocks_sync() -> list[StockEntry]:
    """
    Return whatever is in the cache RIGHT NOW (never blocks).
    Falls back to the built-in list if the cache is empty.
    """
    return _cache if _cache else _FALLBACK_STOCKS


async def get_nse_stocks() -> list[StockEntry]:
    """
    Returns stocks immediately from cache/fallback.
    Triggers a background refresh if the cache is stale or empty.
    """
    stale = not _cache or (time.time() - _cache_time) > CACHE_TTL_SECONDS
    if stale and not _fetch_in_progress:
        asyncio.create_task(_refresh_cache_background())
    return get_nse_stocks_sync()


def search_stocks(query: str, stocks: list[StockEntry], limit: int = 10) -> list[StockEntry]:
    """Symbol-prefix matches first, then company-name contains."""
    q = query.strip().upper()
    if not q:
        return []
    prefix  = [s for s in stocks if s["symbol"].startswith(q)]
    by_name = [s for s in stocks if q in s["name"].upper() and s not in prefix]
    return (prefix + by_name)[:limit]


# ── Built-in fallback: top 80 NSE stocks by market cap ──────────────────────
_FALLBACK_STOCKS: list[StockEntry] = [
    {"symbol": "RELIANCE",    "ticker": "RELIANCE.NS",    "name": "Reliance Industries Ltd"},
    {"symbol": "TCS",         "ticker": "TCS.NS",         "name": "Tata Consultancy Services Ltd"},
    {"symbol": "HDFCBANK",    "ticker": "HDFCBANK.NS",    "name": "HDFC Bank Ltd"},
    {"symbol": "INFY",        "ticker": "INFY.NS",        "name": "Infosys Ltd"},
    {"symbol": "ICICIBANK",   "ticker": "ICICIBANK.NS",   "name": "ICICI Bank Ltd"},
    {"symbol": "HINDUNILVR",  "ticker": "HINDUNILVR.NS",  "name": "Hindustan Unilever Ltd"},
    {"symbol": "SBIN",        "ticker": "SBIN.NS",        "name": "State Bank of India"},
    {"symbol": "BAJFINANCE",  "ticker": "BAJFINANCE.NS",  "name": "Bajaj Finance Ltd"},
    {"symbol": "BHARTIARTL",  "ticker": "BHARTIARTL.NS",  "name": "Bharti Airtel Ltd"},
    {"symbol": "WIPRO",       "ticker": "WIPRO.NS",       "name": "Wipro Ltd"},
    {"symbol": "TATAMOTORS",  "ticker": "TATAMOTORS.NS",  "name": "Tata Motors Ltd"},
    {"symbol": "TATASTEEL",   "ticker": "TATASTEEL.NS",   "name": "Tata Steel Ltd"},
    {"symbol": "HCLTECH",     "ticker": "HCLTECH.NS",     "name": "HCL Technologies Ltd"},
    {"symbol": "AXISBANK",    "ticker": "AXISBANK.NS",    "name": "Axis Bank Ltd"},
    {"symbol": "KOTAKBANK",   "ticker": "KOTAKBANK.NS",   "name": "Kotak Mahindra Bank Ltd"},
    {"symbol": "LT",          "ticker": "LT.NS",          "name": "Larsen & Toubro Ltd"},
    {"symbol": "ASIANPAINT",  "ticker": "ASIANPAINT.NS",  "name": "Asian Paints Ltd"},
    {"symbol": "MARUTI",      "ticker": "MARUTI.NS",      "name": "Maruti Suzuki India Ltd"},
    {"symbol": "SUNPHARMA",   "ticker": "SUNPHARMA.NS",   "name": "Sun Pharmaceutical Industries Ltd"},
    {"symbol": "TITAN",       "ticker": "TITAN.NS",       "name": "Titan Company Ltd"},
    {"symbol": "ULTRACEMCO",  "ticker": "ULTRACEMCO.NS",  "name": "UltraTech Cement Ltd"},
    {"symbol": "NESTLEIND",   "ticker": "NESTLEIND.NS",   "name": "Nestle India Ltd"},
    {"symbol": "POWERGRID",   "ticker": "POWERGRID.NS",   "name": "Power Grid Corporation of India Ltd"},
    {"symbol": "NTPC",        "ticker": "NTPC.NS",        "name": "NTPC Ltd"},
    {"symbol": "ONGC",        "ticker": "ONGC.NS",        "name": "Oil & Natural Gas Corporation Ltd"},
    {"symbol": "JSWSTEEL",    "ticker": "JSWSTEEL.NS",    "name": "JSW Steel Ltd"},
    {"symbol": "TECHM",       "ticker": "TECHM.NS",       "name": "Tech Mahindra Ltd"},
    {"symbol": "ADANIPORTS",  "ticker": "ADANIPORTS.NS",  "name": "Adani Ports & SEZ Ltd"},
    {"symbol": "ADANIENT",    "ticker": "ADANIENT.NS",    "name": "Adani Enterprises Ltd"},
    {"symbol": "BAJAJFINSV",  "ticker": "BAJAJFINSV.NS",  "name": "Bajaj Finserv Ltd"},
    {"symbol": "BAJAJ-AUTO",  "ticker": "BAJAJ-AUTO.NS",  "name": "Bajaj Auto Ltd"},
    {"symbol": "INDUSINDBK",  "ticker": "INDUSINDBK.NS",  "name": "IndusInd Bank Ltd"},
    {"symbol": "CIPLA",       "ticker": "CIPLA.NS",       "name": "Cipla Ltd"},
    {"symbol": "DRREDDY",     "ticker": "DRREDDY.NS",     "name": "Dr. Reddy's Laboratories Ltd"},
    {"symbol": "DIVISLAB",    "ticker": "DIVISLAB.NS",    "name": "Divi's Laboratories Ltd"},
    {"symbol": "EICHERMOT",   "ticker": "EICHERMOT.NS",   "name": "Eicher Motors Ltd"},
    {"symbol": "GRASIM",      "ticker": "GRASIM.NS",      "name": "Grasim Industries Ltd"},
    {"symbol": "HEROMOTOCO",  "ticker": "HEROMOTOCO.NS",  "name": "Hero MotoCorp Ltd"},
    {"symbol": "HINDALCO",    "ticker": "HINDALCO.NS",    "name": "Hindalco Industries Ltd"},
    {"symbol": "COALINDIA",   "ticker": "COALINDIA.NS",   "name": "Coal India Ltd"},
    {"symbol": "BPCL",        "ticker": "BPCL.NS",        "name": "Bharat Petroleum Corporation Ltd"},
    {"symbol": "IOC",         "ticker": "IOC.NS",         "name": "Indian Oil Corporation Ltd"},
    {"symbol": "BRITANNIA",   "ticker": "BRITANNIA.NS",   "name": "Britannia Industries Ltd"},
    {"symbol": "APOLLOHOSP",  "ticker": "APOLLOHOSP.NS",  "name": "Apollo Hospitals Enterprise Ltd"},
    {"symbol": "TATACONSUM",  "ticker": "TATACONSUM.NS",  "name": "Tata Consumer Products Ltd"},
    {"symbol": "SBILIFE",     "ticker": "SBILIFE.NS",     "name": "SBI Life Insurance Company Ltd"},
    {"symbol": "HDFCLIFE",    "ticker": "HDFCLIFE.NS",    "name": "HDFC Life Insurance Company Ltd"},
    {"symbol": "ICICIPRULI",  "ticker": "ICICIPRULI.NS",  "name": "ICICI Prudential Life Insurance"},
    {"symbol": "M&M",         "ticker": "M&M.NS",         "name": "Mahindra & Mahindra Ltd"},
    {"symbol": "SHREECEM",    "ticker": "SHREECEM.NS",    "name": "Shree Cement Ltd"},
    {"symbol": "PIDILITIND",  "ticker": "PIDILITIND.NS",  "name": "Pidilite Industries Ltd"},
    {"symbol": "DABUR",       "ticker": "DABUR.NS",       "name": "Dabur India Ltd"},
    {"symbol": "MARICO",      "ticker": "MARICO.NS",      "name": "Marico Ltd"},
    {"symbol": "GODREJCP",    "ticker": "GODREJCP.NS",    "name": "Godrej Consumer Products Ltd"},
    {"symbol": "BERGEPAINT",  "ticker": "BERGEPAINT.NS",  "name": "Berger Paints India Ltd"},
    {"symbol": "HAVELLS",     "ticker": "HAVELLS.NS",     "name": "Havells India Ltd"},
    {"symbol": "VOLTAS",      "ticker": "VOLTAS.NS",      "name": "Voltas Ltd"},
    {"symbol": "MUTHOOTFIN",  "ticker": "MUTHOOTFIN.NS",  "name": "Muthoot Finance Ltd"},
    {"symbol": "CHOLAFIN",    "ticker": "CHOLAFIN.NS",    "name": "Cholamandalam Investment & Finance"},
    {"symbol": "PAGEIND",     "ticker": "PAGEIND.NS",     "name": "Page Industries Ltd"},
    {"symbol": "BOSCHLTD",    "ticker": "BOSCHLTD.NS",    "name": "Bosch Ltd"},
    {"symbol": "AMBUJACEM",   "ticker": "AMBUJACEM.NS",   "name": "Ambuja Cements Ltd"},
    {"symbol": "ACC",         "ticker": "ACC.NS",         "name": "ACC Ltd"},
    {"symbol": "BANKBARODA",  "ticker": "BANKBARODA.NS",  "name": "Bank of Baroda"},
    {"symbol": "PNB",         "ticker": "PNB.NS",         "name": "Punjab National Bank"},
    {"symbol": "CANBK",       "ticker": "CANBK.NS",       "name": "Canara Bank"},
    {"symbol": "FEDERALBNK",  "ticker": "FEDERALBNK.NS",  "name": "Federal Bank Ltd"},
    {"symbol": "IDFCFIRSTB",  "ticker": "IDFCFIRSTB.NS",  "name": "IDFC First Bank Ltd"},
    {"symbol": "BANDHANBNK",  "ticker": "BANDHANBNK.NS",  "name": "Bandhan Bank Ltd"},
    {"symbol": "LUPIN",       "ticker": "LUPIN.NS",       "name": "Lupin Ltd"},
    {"symbol": "BIOCON",      "ticker": "BIOCON.NS",      "name": "Biocon Ltd"},
    {"symbol": "AUROPHARMA",  "ticker": "AUROPHARMA.NS",  "name": "Aurobindo Pharma Ltd"},
    {"symbol": "TORNTPHARM", "ticker": "TORNTPHARM.NS",  "name": "Torrent Pharmaceuticals Ltd"},
    {"symbol": "MCDOWELL-N",  "ticker": "MCDOWELL-N.NS",  "name": "United Spirits Ltd"},
    {"symbol": "UBL",         "ticker": "UBL.NS",         "name": "United Breweries Ltd"},
    {"symbol": "TATAPOWER",   "ticker": "TATAPOWER.NS",   "name": "Tata Power Company Ltd"},
    {"symbol": "ADANIGREEN",  "ticker": "ADANIGREEN.NS",  "name": "Adani Green Energy Ltd"},
    {"symbol": "ZOMATO",      "ticker": "ZOMATO.NS",      "name": "Zomato Ltd"},
    {"symbol": "NYKAA",       "ticker": "NYKAA.NS",       "name": "FSN E-Commerce Ventures Ltd"},
    {"symbol": "PAYTM",       "ticker": "PAYTM.NS",       "name": "One 97 Communications Ltd"},
    {"symbol": "DMART",       "ticker": "DMART.NS",       "name": "Avenue Supermarts Ltd"},
    {"symbol": "IRCTC",       "ticker": "IRCTC.NS",       "name": "Indian Railway Catering & Tourism Corp"},
]
