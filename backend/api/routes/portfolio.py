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
from backend.db.models import Client, Holding, Portfolio

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
    return [str(h).lower().strip().replace(" ", "_") if h else "" for h in row]


def _to_nse_ticker(symbol: str) -> str:
    """Convert a raw broker symbol to an NSE ticker (e.g. RELIANCE → RELIANCE.NS)."""
    symbol = symbol.strip().upper()
    # Already has exchange suffix
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    # BSE numeric code like 500285-EQ — keep as-is, yfinance won't know it anyway
    if re.match(r"^\d+(-EQ)?$", symbol):
        return symbol
    return symbol + ".NS"


def _parse_broker_format(rows: list) -> tuple[list[dict], list[str]]:
    """
    Parse PROFITMART / broker portfolio report format.
    Rows 1-3: metadata; Row 4 (index 3): headers; Rows 5+ (index 4+): data.

    Extracts open / partially-open positions and aggregates by symbol.
    Returns (holdings_list, skipped_list).
    """
    if len(rows) < 5:
        return [], []

    headers = _normalise_headers(rows[3])  # row 4 = index 3

    def col(names: list[str]) -> int:
        for n in names:
            if n in headers:
                return headers.index(n)
        return -1

    sym_idx      = col(["scrip_symbol"])
    qty_idx      = col(["purchase_qty"])
    rate_idx     = col(["purchase_rate"])
    sell_qty_idx = col(["sell_qty"])
    sell_date_idx = col(["sell_trade_date"])

    if any(i == -1 for i in [sym_idx, qty_idx, rate_idx]):
        return [], ["Could not find required broker columns (Scrip_Symbol, Purchase_Qty, Purchase_Rate)"]

    # Aggregate net open positions by symbol
    agg: dict[str, dict] = defaultdict(lambda: {"net_qty": 0.0, "cost_basis": 0.0})
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

            net_qty = buy_qty - sell_qty
            if net_qty <= 0:
                continue  # fully sold, skip

            agg[symbol]["net_qty"]    += net_qty
            agg[symbol]["cost_basis"] += net_qty * buy_rate

        except Exception:
            skipped.append(f"row {i}")

    holdings = []
    for symbol, data in agg.items():
        if data["net_qty"] > 0:
            holdings.append({
                "ticker":   _to_nse_ticker(symbol),
                "shares":   round(data["net_qty"], 6),
                "avg_cost": round(data["cost_basis"] / data["net_qty"], 4),
            })

    return holdings, skipped


def _is_broker_format(rows: list) -> bool:
    """Detect broker format by looking for Scrip_Symbol in row 4 (index 3)."""
    if len(rows) < 4:
        return False
    headers = _normalise_headers(rows[3])
    return "scrip_symbol" in headers and "purchase_qty" in headers


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


@router.post("/{portfolio_id}/holdings")
async def add_holding(
    portfolio_id: int, body: HoldingIn, db: AsyncSession = Depends(get_db)
):
    """Add a single holding manually."""
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
    """Delete a single holding by ID."""
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
    Upload an Excel file (.xlsx) to bulk-add holdings.

    Supports two formats:

    1. BROKER FORMAT (PROFITMART / similar):
       - Rows 1-3: metadata (broker name, report title, date)
       - Row 4: headers including Scrip_Symbol, Purchase_Qty, Purchase_Rate, Sell_Qty
       - Automatically extracts open positions, aggregates by symbol, adds .NS suffix

    2. SIMPLE FORMAT:
       - Row 1: headers — Ticker | Shares | Avg Cost
       - Row 2+: data rows
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

    # --- Detect and parse format ---
    if _is_broker_format(rows):
        holdings_to_add, skipped = _parse_broker_format(rows)
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
        cost_idx   = find_col(["avg_cost", "average_cost", "avg_cost_per_share",
                                "cost", "price", "buy_price", "purchase_rate"])

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

        holdings_to_add, skipped = [], []
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

    if not holdings_to_add:
        raise HTTPException(400, "No valid open positions found in the file.")

    added = []
    for h in holdings_to_add:
        db.add(Holding(
            portfolio_id=portfolio_id,
            ticker=h["ticker"],
            shares=h["shares"],
            avg_cost=h["avg_cost"],
        ))
        added.append(h["ticker"])

    await db.commit()
    return {
        "added": len(added),
        "tickers": added,
        "skipped": skipped,
        "format_detected": "broker" if _is_broker_format(rows) else "simple",
    }
