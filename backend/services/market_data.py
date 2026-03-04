import asyncio
from functools import partial
from typing import Any

import pandas as pd
import requests
import yfinance as yf


# ── Sync helpers (run in thread pool so they don't block the event loop) ──────

def _download(tickers: list[str], period: str) -> pd.DataFrame:
    return yf.download(tickers, period=period, auto_adjust=True, progress=False)


def _ticker_info(ticker: str) -> dict:
    return yf.Ticker(ticker).info


async def _run_sync(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, *args))


def _alternate_suffix(ticker: str) -> str | None:
    """Return the alternate exchange ticker (.NS ↔ .BO) for Indian stocks."""
    if ticker.endswith(".NS"):
        return ticker[:-3] + ".BO"
    if ticker.endswith(".BO"):
        return ticker[:-3] + ".NS"
    return None


def _extract_price(data: pd.DataFrame, ticker: str, all_tickers: list[str]) -> float:
    try:
        if len(all_tickers) == 1:
            return float(data["Close"].dropna().iloc[-1])
        return float(data["Close"][ticker].dropna().iloc[-1])
    except Exception:
        return 0.0


def _fetch_single(ticker: str) -> float:
    """Download a single ticker and return its latest close price."""
    try:
        data = yf.download(ticker, period="2d", auto_adjust=True, progress=False)
        if not data.empty:
            return float(data["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return 0.0


def _yf_name_search(name: str) -> list[str]:
    """Use yfinance Search (>= 0.2) to find tickers by company name."""
    try:
        results = yf.Search(name, max_results=5).quotes
        return [q.get("symbol", "") for q in results if q.get("symbol")]
    except Exception:
        return []


def _screener_search(name: str) -> list[str]:
    """
    Search screener.in by company name.
    Returns candidate ticker symbols (without exchange suffix) from the first few results.
    """
    try:
        resp = requests.get(
            "https://www.screener.in/api/company/search/",
            params={"q": name, "fields": "name,url", "limit": 5},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.screener.in/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=8,
        )
        if resp.ok:
            symbols = []
            for item in resp.json():
                url = item.get("url", "")
                # URL format: "company/SYMBOL/" or "/company/SYMBOL/consolidated/"
                parts = [p for p in url.split("/") if p and p not in ("company", "consolidated")]
                if parts:
                    symbols.append(parts[0])
            return symbols
    except Exception:
        pass
    return []


# ── Public async API ───────────────────────────────────────────────────────────

async def get_current_prices(
    tickers: list[str],
    names: dict[str, str] | None = None,
) -> dict[str, float]:
    """
    Fetch latest closing prices for a list of tickers.

    Fallback chain for any ticker returning 0:
      1. Alternate exchange suffix (.NS ↔ .BO)
      2. yfinance Search by company name
      3. screener.in search by company name → try .NS and .BO with found symbol
    """
    if not tickers:
        return {}

    data: pd.DataFrame = await _run_sync(_download, tickers, "2d")
    prices: dict[str, float] = {}

    if not data.empty:
        for ticker in tickers:
            prices[ticker] = _extract_price(data, ticker, tickers)
    else:
        prices = {t: 0.0 for t in tickers}

    # Fallback 1: alternate exchange suffix (.NS ↔ .BO)
    failed = [t for t in tickers if prices.get(t, 0.0) == 0.0 and _alternate_suffix(t)]
    if failed:
        alt_map = {_alternate_suffix(t): t for t in failed}
        alt_tickers = list(alt_map.keys())
        alt_data: pd.DataFrame = await _run_sync(_download, alt_tickers, "2d")
        if not alt_data.empty:
            for alt, orig in alt_map.items():
                price = _extract_price(alt_data, alt, alt_tickers)
                if price > 0.0:
                    prices[orig] = price

    # Fallback 2 & 3: name-based search for still-missing tickers
    if names:
        name_failed = [t for t in tickers if prices.get(t, 0.0) == 0.0 and names.get(t)]
        for ticker in name_failed:
            company_name = names[ticker]

            # 2a. yfinance Search by name
            candidates = await _run_sync(_yf_name_search, company_name)
            found = False
            for candidate in candidates:
                price = await _run_sync(_fetch_single, candidate)
                if price > 0.0:
                    prices[ticker] = price
                    found = True
                    break

            if found:
                continue

            # 2b. screener.in search → try .NS then .BO
            screener_syms = await _run_sync(_screener_search, company_name)
            for sym in screener_syms:
                for suffix in (".NS", ".BO"):
                    price = await _run_sync(_fetch_single, sym + suffix)
                    if price > 0.0:
                        prices[ticker] = price
                        found = True
                        break
                if found:
                    break

    return prices


async def get_historical_returns(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Return daily % returns without blocking the event loop."""
    data: pd.DataFrame = await _run_sync(_download, tickers, period)
    if data.empty:
        return pd.DataFrame()
    close = data["Close"] if len(tickers) > 1 else data["Close"].to_frame(tickers[0])
    return close.pct_change().dropna()


async def get_ticker_info(ticker: str) -> dict[str, Any]:
    """Return key metadata for a ticker without blocking the event loop."""
    try:
        info = await _run_sync(_ticker_info, ticker)
    except Exception:
        info = {}
    # If primary ticker failed, try alternate exchange
    if not info.get("longName") and _alternate_suffix(ticker):
        try:
            info = await _run_sync(_ticker_info, _alternate_suffix(ticker))
        except Exception:
            info = {}
    return {
        "name": info.get("longName", ticker),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "dividend_yield": info.get("dividendYield"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
    }
