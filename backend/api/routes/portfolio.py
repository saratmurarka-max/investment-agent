import io

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

    Expected columns (case-insensitive, in any order):
        ticker | shares | avg_cost  (or average_cost / avg cost / cost)
    Row 1 must be headers. Example:
        Ticker  | Shares | Avg Cost
        AAPL    | 10     | 150.00
        MSFT    | 5      | 280.00
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

    # Normalise header names
    headers = [str(h).lower().strip().replace(" ", "_") if h else "" for h in rows[0]]

    def find_col(candidates: list[str]) -> int:
        for c in candidates:
            if c in headers:
                return headers.index(c)
        return -1

    ticker_idx = find_col(["ticker", "symbol", "stock"])
    shares_idx = find_col(["shares", "quantity", "qty", "units"])
    cost_idx   = find_col(["avg_cost", "average_cost", "avg_cost_per_share", "cost", "price", "buy_price"])

    missing = []
    if ticker_idx == -1: missing.append("ticker")
    if shares_idx == -1: missing.append("shares")
    if cost_idx   == -1: missing.append("avg_cost")
    if missing:
        raise HTTPException(
            400,
            f"Could not find required columns: {', '.join(missing)}. "
            f"Headers found: {', '.join(headers)}"
        )

    added, skipped = [], []
    for i, row in enumerate(rows[1:], start=2):
        try:
            ticker = str(row[ticker_idx]).upper().strip()
            shares = float(row[shares_idx])
            avg_cost = float(row[cost_idx])
            if not ticker or shares <= 0 or avg_cost <= 0:
                raise ValueError("Invalid values")
            db.add(Holding(portfolio_id=portfolio_id, ticker=ticker, shares=shares, avg_cost=avg_cost))
            added.append(ticker)
        except Exception:
            skipped.append(f"row {i}")

    await db.commit()
    return {
        "added": len(added),
        "tickers": added,
        "skipped": skipped,
    }
