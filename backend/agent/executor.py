"""Resolves tool calls from the agent into real function results."""

import asyncio
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Holding, Portfolio
from backend.services import market_data, portfolio_analysis

TOOL_TIMEOUT_SECONDS = 25


async def _load_holdings(portfolio_id: int, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")
    return [
        {"ticker": h.ticker, "shares": float(h.shares), "avg_cost": float(h.avg_cost)}
        for h in portfolio.holdings
    ]


async def execute_tool(name: str, inputs: dict[str, Any], db: AsyncSession) -> str:
    try:
        result = await asyncio.wait_for(
            _dispatch(name, inputs, db),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        result = {
            "error": (
                f"'{name}' timed out after {TOOL_TIMEOUT_SECONDS}s. "
                "Market data fetch is slow — please try a simpler question or try again shortly."
            )
        }
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, default=str)


async def _dispatch(name: str, inputs: dict, db: AsyncSession) -> Any:
    if name == "get_portfolio_snapshot":
        holdings = await _load_holdings(inputs["portfolio_id"], db)
        return await portfolio_analysis.build_portfolio_snapshot(holdings)

    if name == "get_performance_metrics":
        holdings = await _load_holdings(inputs["portfolio_id"], db)
        snapshot = await portfolio_analysis.build_portfolio_snapshot(holdings)
        tickers = [h["ticker"] for h in snapshot["holdings"]]
        weights = [h["weight"] / 100 for h in snapshot["holdings"]]
        return await portfolio_analysis.compute_performance_metrics(
            tickers=tickers,
            weights=weights,
            period=inputs.get("period", "1y"),
            benchmark=inputs.get("benchmark", "SPY"),
        )

    if name == "get_ticker_info":
        return await market_data.get_ticker_info(inputs["ticker"])

    if name == "suggest_rebalancing":
        holdings = await _load_holdings(inputs["portfolio_id"], db)
        snapshot = await portfolio_analysis.build_portfolio_snapshot(holdings)
        tickers = [h["ticker"] for h in snapshot["holdings"]]
        current_weights = [h["weight"] for h in snapshot["holdings"]]
        target_map: dict[str, float] = inputs["target_weights"]
        target_weights = [target_map.get(t, 0.0) for t in tickers]
        return portfolio_analysis.suggest_rebalancing(
            tickers=tickers,
            current_weights=current_weights,
            target_weights=target_weights,
            threshold_pct=inputs.get("threshold_pct", 5.0),
        )

    if name == "optimize_portfolio":
        holdings = await _load_holdings(inputs["portfolio_id"], db)
        tickers = [h["ticker"] for h in holdings]
        return await portfolio_analysis.optimize_portfolio(
            tickers=tickers,
            period=inputs.get("period", "1y"),
        )

    raise ValueError(f"Unknown tool: {name}")
