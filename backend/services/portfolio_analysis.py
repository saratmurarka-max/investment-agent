import asyncio
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

from backend.services.market_data import get_current_prices, get_historical_returns


async def build_portfolio_snapshot(holdings: list[dict]) -> dict[str, Any]:
    tickers = [h["ticker"] for h in holdings]
    prices = await get_current_prices(tickers)

    rows = []
    for h in holdings:
        ticker = h["ticker"]
        price = prices.get(ticker, 0.0)
        shares = float(h["shares"])
        avg_cost = float(h["avg_cost"])
        market_value = price * shares
        cost_basis = avg_cost * shares
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0
        rows.append({
            "ticker": ticker,
            "shares": shares,
            "avg_cost": avg_cost,
            "current_price": price,
            "market_value": market_value,
            "cost_basis": cost_basis,
            "pnl": pnl,
            "pnl_pct": round(pnl_pct, 2),
        })

    total_value = sum(r["market_value"] for r in rows)
    for r in rows:
        r["weight"] = round(r["market_value"] / total_value * 100, 2) if total_value else 0.0

    return {"total_value": round(total_value, 2), "holdings": rows}


async def compute_performance_metrics(
    tickers: list[str],
    weights: list[float],
    period: str = "1y",
    benchmark: str = "SPY",
) -> dict[str, Any]:
    all_tickers = list(set(tickers + [benchmark]))
    returns = await get_historical_returns(all_tickers, period)

    if returns.empty:
        return {"error": "No historical data available"}

    port_weights = np.array(weights)
    port_weights /= port_weights.sum()

    port_cols = [t for t in tickers if t in returns.columns]
    port_returns = returns[port_cols].dot(port_weights[: len(port_cols)])

    def annualized_return(r: pd.Series) -> float:
        return float((1 + r).prod() ** (252 / len(r)) - 1)

    def annualized_vol(r: pd.Series) -> float:
        return float(r.std() * np.sqrt(252))

    def sharpe(r: pd.Series, rf: float = 0.05) -> float:
        ann_r = annualized_return(r)
        vol = annualized_vol(r)
        return round((ann_r - rf) / vol, 3) if vol else 0.0

    def max_drawdown(r: pd.Series) -> float:
        cum = (1 + r).cumprod()
        dd = (cum - cum.cummax()) / cum.cummax()
        return round(float(dd.min()) * 100, 2)

    bench = returns[benchmark] if benchmark in returns.columns else pd.Series(dtype=float)

    return {
        "period": period,
        "portfolio": {
            "annualized_return": round(annualized_return(port_returns) * 100, 2),
            "annualized_volatility": round(annualized_vol(port_returns) * 100, 2),
            "sharpe_ratio": sharpe(port_returns),
            "max_drawdown_pct": max_drawdown(port_returns),
        },
        "benchmark": {
            "ticker": benchmark,
            "annualized_return": round(annualized_return(bench) * 100, 2) if not bench.empty else None,
            "sharpe_ratio": sharpe(bench) if not bench.empty else None,
        },
    }


def suggest_rebalancing(
    tickers: list[str],
    current_weights: list[float],
    target_weights: list[float],
    threshold_pct: float = 5.0,
) -> list[dict]:
    suggestions = []
    for ticker, current, target in zip(tickers, current_weights, target_weights):
        drift = current - target
        if abs(drift) >= threshold_pct:
            suggestions.append({
                "ticker": ticker,
                "current_weight_pct": round(current, 2),
                "target_weight_pct": round(target, 2),
                "drift_pct": round(drift, 2),
                "action": "reduce" if drift > 0 else "increase",
            })
    return suggestions


async def optimize_portfolio(tickers: list[str], period: str = "1y") -> dict[str, Any]:
    from pypfopt import EfficientFrontier, expected_returns, risk_models

    returns = await get_historical_returns(tickers, period)
    if returns.empty:
        return {"error": "No historical data available for optimization"}

    valid = [t for t in tickers if t in returns.columns]
    returns = returns[valid]

    def _run_optimization():
        mu = expected_returns.mean_historical_return(returns, returns_data=True, frequency=252)
        sigma = risk_models.sample_cov(returns, returns_data=True, frequency=252)
        ef = EfficientFrontier(mu, sigma)
        ef.max_sharpe(risk_free_rate=0.05)
        weights = ef.clean_weights()
        perf = ef.portfolio_performance(verbose=False, risk_free_rate=0.05)
        return weights, perf

    loop = asyncio.get_event_loop()
    weights, perf = await loop.run_in_executor(None, _run_optimization)

    return {
        "optimal_weights": {k: round(v * 100, 2) for k, v in weights.items()},
        "expected_annual_return_pct": round(perf[0] * 100, 2),
        "annual_volatility_pct": round(perf[1] * 100, 2),
        "sharpe_ratio": round(perf[2], 3),
    }
