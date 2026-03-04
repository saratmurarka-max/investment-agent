import io
import re
from collections import defaultdict

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.database import get_db
from backend.db.models import Client, Holding, Portfolio, RealizedPnL
from backend.services import market_data

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


# --- Schemas ---

class HoldingIn(BaseModel):
    ticker: str
    shares: float
    avg_cost: float


class PortfolioIn(BaseModel):
    name: str
    currency: str = "USD"
    holdings: list[HoldingIn] = []


class ClientIn(BaseModel):
    name: str
    email: str
    risk_tolerance: str = "medium"


# --- Helpers ---

def _normalise_headers(row) -> list[str]:
    return [str(h).lower().strip().replace(" ", "_").replace("\\", "") if h else "" for h in row]


def _to_nse_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    if re.match(r"^\d+(-EQ)?$", symbol):
        return symbol
    return symbol + ".NS"


def _is_broker_format(rows: list) -> bool:
    if len(rows) < 4:
        return False
    headers = _normalise_headers(rows[3])
    return "scrip_symbol" in headers and "purchase_qty" in headers


def _parse_broker_format(rows: list) -> tuple[list[dict], list[dict], list[str]]:
    """
    Returns:
        holdings      - list of open positions {ticker, shares, avg_cost}
        realized_pnls - list of realized P&L per ticker {ticker, short_term_gain, long_term_gain}
        skipped       - list of skipped row descriptions
    """
    if len(rows) < 5:
        return [], [], []

    headers = _normalise_headers(rows[3])

    def col(names: list[str]) -> int:
        for n in names:
            if n in headers:
                return headers.index(n)
        return -1

    sym_idx       = col(["scrip_symbol"])
    qty_idx       = col(["purchase_qty"])
    rate_idx      = col(["purchase_rate"])
    sell_qty_idx  = col(["sell_qty"])
    stcg_idx      = col(["shorterm_pl", "short_term_pl", "shorterm_p\\l"])
    ltcg_idx      = col(["actual_longterm", "longterm_pl", "actual_longterm_pl"])

    if any(i == -1 for i in [sym_idx, qty_idx, rate_idx]):
        return [], [], ["Could not find required broker columns"]

    open_agg: dict[str, dict] = defaultdict(lambda: {"net_qty": 0.0, "cost_basis": 0.0})
    real_agg: dict[str, dict] = defaultdict(lambda: {"short_term": 0.0, "long_term": 0.0})
    skipped: list[str] = []

    for i, row in enumerate(rows[4:], start=5):
        try:
            symbol = str(row[sym_idx] or "").strip().upper()
            if not symbol or symbol == "NONE":
                continue

            buy_qty  = float(row[qty_idx]  or 0)
            buy_rate = float(row[rate_idx] or 0)
            sell_qty = float(row[sell_qty_idx] or 0) if sell_qty_idx >= 0 else 0

            if buy_qty <= 0:
                continue

            # Realized P&L for sold portion
            if sell_qty > 0:
                stcg = float(row[stcg_idx] or 0) if stcg_idx >= 0 else 0
                ltcg = float(row[ltcg_idx] or 0) if ltcg_idx >= 0 else 0
                real_agg[symbol]["short_term"] += stcg
                real_agg[symbol]["long_term"]  += ltcg

            # Open position (unsold portion)
            net_qty = buy_qty - sell_qty
            if net_qty > 0:
                open_agg[symbol]["net_qty"]    += net_qty
                open_agg[symbol]["cost_basis"] += net_qty * buy_rate

        except Exception:
            skipped.append(f"row {i}")

    holdings = [
        {
            "ticker":   _to_nse_ticker(sym),
            "shares":   round(data["net_qty"], 6),
            "avg_cost": round(data["cost_basis"] / data["net_qty"], 4),
        }
        for sym, data in open_agg.items()
        if data["net_qty"] > 0
    ]

    realized_pnls = [
        {
            "ticker":           _to_nse_ticker(sym),
            "short_term_gain":  round(data["short_term"], 4),
            "long_term_gain":   round(data["long_term"], 4),
        }
        for sym, data in real_agg.items()
        if data["short_term"] != 0 or data["long_term"] != 0
    ]

    return holdings, realized_pnls, skipped


# --- Routes ---

@router.post("/clients")
async def create_client(body: ClientIn, db: AsyncSession = Depends(get_db)):
    client = Client(**body.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return {"id": client.id, "name": client.name, "email": client.email}


@router.get("/clients/{client_id}/portfolios")
async def list_portfolios(client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.client_id == client_id)
    )
    portfolios = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "currency": p.currency,
            "holding_count": len(p.holdings),
        }
        for p in portfolios
    ]


@router.post("/clients/{client_id}/portfolios")
async def create_portfolio(
    client_id: int, body: PortfolioIn, db: AsyncSession = Depends(get_db)
):
    portfolio = Portfolio(client_id=client_id, name=body.name, currency=body.currency)
    db.add(portfolio)
    await db.flush()
    for h in body.holdings:
        db.add(Holding(portfolio_id=portfolio.id, **h.model_dump()))
    await db.commit()
    await db.refresh(portfolio)
    return {"id": portfolio.id, "name": portfolio.name}


@router.get("/{portfolio_id}")
async def get_portfolio(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "currency": portfolio.currency,
        "holdings": [
            {
                "id": h.id,
                "ticker": h.ticker,
                "shares": float(h.shares),
                "avg_cost": float(h.avg_cost),
            }
            for h in portfolio.holdings
        ],
    }


@router.get("/{portfolio_id}/pnl")
async def get_portfolio_pnl(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns per-holding P&L (unrealized) using live prices + total realized P&L.
    """
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holdings = portfolio.holdings
    if not holdings:
        return {
            "holdings": [],
            "summary": {
                "total_invested": 0,
                "total_current_value": 0,
                "total_unrealized_gain": 0,
                "total_unrealized_pct": 0,
                "total_realized_gain": 0,
                "total_short_term_gain": 0,
                "total_long_term_gain": 0,
            }
        }

    # Fetch live prices for all tickers
    tickers = [h.ticker for h in holdings]
    try:
        current_prices = await market_data.get_current_prices(tickers)
    except Exception:
        current_prices = {}

    # Compute unrealized P&L per holding
    holding_pnl = []
    total_invested = 0.0
    total_current_value = 0.0

    for h in holdings:
        avg_cost = float(h.avg_cost)
        shares   = float(h.shares)
        price    = current_prices.get(h.ticker, 0.0)

        invested      = avg_cost * shares
        current_value = price * shares
        unrealized    = current_value - invested
        pct           = ((price - avg_cost) / avg_cost * 100) if avg_cost > 0 and price > 0 else 0.0

        holding_pnl.append({
            "id":              h.id,
            "ticker":          h.ticker,
            "shares":          shares,
            "avg_cost":        avg_cost,
            "current_price":   price,
            "invested":        round(invested, 2),
            "current_value":   round(current_value, 2),
            "unrealized_gain": round(unrealized, 2),
            "unrealized_pct":  round(pct, 2),
        })

        total_invested      += invested
        total_current_value += current_value

    # Fetch realized P&L stored from broker uploads
    real_result = await db.execute(
        select(RealizedPnL).where(RealizedPnL.portfolio_id == portfolio_id)
    )
    realized_rows = real_result.scalars().all()
    total_stcg = sum(float(r.short_term_gain) for r in realized_rows)
    total_ltcg = sum(float(r.long_term_gain)  for r in realized_rows)
    total_realized = total_stcg + total_ltcg

    total_unrealized = total_current_value - total_invested
    total_unrealized_pct = (total_unrealized / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "holdings": holding_pnl,
        "summary": {
            "total_invested":      round(total_invested, 2),
            "total_current_value": round(total_current_value, 2),
            "total_unrealized_gain": round(total_unrealized, 2),
            "total_unrealized_pct":  round(total_unrealized_pct, 2),
            "total_realized_gain":   round(total_realized, 2),
            "total_short_term_gain": round(total_stcg, 2),
            "total_long_term_gain":  round(total_ltcg, 2),
        },
    }


@router.post("/{portfolio_id}/holdings")
async def add_holding(
    portfolio_id: int, body: HoldingIn, db: AsyncSession = Depends(get_db)
):
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holding = Holding(
        portfolio_id=portfolio_id,
        ticker=body.ticker.upper().strip(),
        shares=body.shares,
        avg_cost=body.avg_cost,
    )
    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    return {
        "id": holding.id,
        "ticker": holding.ticker,
        "shares": float(holding.shares),
        "avg_cost": float(holding.avg_cost),
    }


@router.delete("/{portfolio_id}/holdings/{holding_id}")
async def delete_holding(
    portfolio_id: int, holding_id: int, db: AsyncSession = Depends(get_db)
):
    holding = await db.get(Holding, holding_id)
    if not holding or holding.portfolio_id != portfolio_id:
        raise HTTPException(404, "Holding not found")
    await db.delete(holding)
    await db.commit()
    return {"deleted": holding_id}


@router.post("/{portfolio_id}/holdings/upload")
async def upload_holdings_excel(
    portfolio_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Supports two Excel formats:

    1. BROKER FORMAT (PROFITMART / similar broker reports):
       - Rows 1-3: metadata; Row 4: headers with Scrip_Symbol, Purchase_Qty, etc.
       - Automatically extracts open positions + realized P&L

    2. SIMPLE FORMAT:
       - Row 1: Ticker | Shares | Avg Cost
    """
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Only .xlsx files are supported")

    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    contents = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(400, "Could not read Excel file. Make sure it is a valid .xlsx file.")

    if len(rows) < 2:
        raise HTTPException(400, "File must have a header row and at least one data row.")

    broker_fmt = _is_broker_format(rows)

    if broker_fmt:
        holdings_to_add, realized_to_add, skipped = _parse_broker_format(rows)
    else:
        # Simple format
        headers = _normalise_headers(rows[0])

        def find_col(candidates: list[str]) -> int:
            for c in candidates:
                if c in headers:
                    return headers.index(c)
            return -1

        ticker_idx = find_col(["ticker", "symbol", "stock", "scrip_symbol"])
        shares_idx = find_col(["shares", "quantity", "qty", "units", "purchase_qty"])
        cost_idx   = find_col(["avg_cost", "average_cost", "cost", "price",
                                "buy_price", "purchase_rate"])

        missing = []
        if ticker_idx == -1: missing.append("ticker/symbol")
        if shares_idx == -1: missing.append("shares/qty")
        if cost_idx   == -1: missing.append("avg_cost/price")
        if missing:
            raise HTTPException(
                400,
                f"Could not find required columns: {', '.join(missing)}. "
                f"Headers found: {', '.join(h for h in headers if h)}"
            )

        holdings_to_add, realized_to_add, skipped = [], [], []
        for i, row in enumerate(rows[1:], start=2):
            try:
                ticker   = str(row[ticker_idx]).upper().strip()
                shares   = float(row[shares_idx])
                avg_cost = float(row[cost_idx])
                if not ticker or shares <= 0 or avg_cost <= 0:
                    raise ValueError("Invalid values")
                holdings_to_add.append({"ticker": ticker, "shares": shares, "avg_cost": avg_cost})
            except Exception:
                skipped.append(f"row {i}")

    if not holdings_to_add and not realized_to_add:
        raise HTTPException(400, "No valid positions found in the file.")

    # Insert open holdings
    added_tickers = []
    for h in holdings_to_add:
        db.add(Holding(
            portfolio_id=portfolio_id,
            ticker=h["ticker"],
            shares=h["shares"],
            avg_cost=h["avg_cost"],
        ))
        added_tickers.append(h["ticker"])

    # Insert realized P&L (replace existing for same ticker)
    if realized_to_add:
        existing = await db.execute(
            select(RealizedPnL).where(RealizedPnL.portfolio_id == portfolio_id)
        )
        for row in existing.scalars().all():
            await db.delete(row)

        for r in realized_to_add:
            db.add(RealizedPnL(
                portfolio_id=portfolio_id,
                ticker=r["ticker"],
                short_term_gain=r["short_term_gain"],
                long_term_gain=r["long_term_gain"],
            ))

    await db.commit()
    return {
        "added": len(added_tickers),
        "tickers": added_tickers,
        "realized_pnl_imported": len(realized_to_add),
        "skipped": skipped,
        "format_detected": "broker" if broker_fmt else "simple",
    }
