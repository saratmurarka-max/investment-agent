import asyncio
from functools import partial
from typing import Any

import pandas as pd
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


# ── Public async API ───────────────────────────────────────────────────────────

async def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """
    Fetch latest closing prices for a list of tickers.
    For Indian stocks, if .NS returns 0, automatically retries with .BO and vice versa.
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

    # Retry failed Indian tickers with alternate exchange suffix
    failed = [t for t in tickers if prices.get(t, 0.0) == 0.0 and _alternate_suffix(t)]
    if failed:
        alt_map = {_alternate_suffix(t): t for t in failed}  # alt_ticker → original_ticker
        alt_tickers = list(alt_map.keys())
        alt_data: pd.DataFrame = await _run_sync(_download, alt_tickers, "2d")
        if not alt_data.empty:
            for alt, orig in alt_map.items():
                price = _extract_price(alt_data, alt, alt_tickers)
                if price > 0.0:
                    prices[orig] = price  # store under original ticker key

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
