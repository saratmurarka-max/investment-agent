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


# ── Public async API ───────────────────────────────────────────────────────────

async def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest closing prices without blocking the event loop."""
    data: pd.DataFrame = await _run_sync(_download, tickers, "2d")
    prices: dict[str, float] = {}

    if data.empty:
        return {t: 0.0 for t in tickers}

    if len(tickers) == 1:
        try:
            prices[tickers[0]] = float(data["Close"].iloc[-1])
        except Exception:
            prices[tickers[0]] = 0.0
    else:
        for ticker in tickers:
            try:
                prices[ticker] = float(data["Close"][ticker].dropna().iloc[-1])
            except Exception:
                prices[ticker] = 0.0

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
