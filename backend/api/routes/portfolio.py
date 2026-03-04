import io
import re
from collections import defaultdict
from datetime import date as date_type

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
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


def _to_exchange_ticker(symbol: str) -> str:
    """
    Resolve a raw broker symbol to a yfinance-compatible ticker.
    Defaults to .NS (NSE) — the primary exchange for most Indian stocks.
    Symbols already carrying .NS / .BO are returned unchanged.
    Numeric BSE codes (e.g. 531637-EQ) are converted to BSE format (531637.BO).
    """
    symbol = symbol.strip().upper()
    # Already qualified
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    # Numeric BSE code (e.g. 531637-EQ or 531637) → use BSE format for yfinance
    if re.match(r"^\d+(-EQ)?$", symbol):
        base = re.sub(r"-EQ$", "", symbol)
        return base + ".BO"
    # Default to NSE (primary Indian exchange)
    return symbol + ".NS"


def _is_broker_format(rows: list) -> bool:
    if len(rows) < 4:
        return False
    headers = _normalise_headers(rows[3])
    has_symbol = "scrip_symbol" in headers or "scrip_name" in headers
    return has_symbol and "purchase_qty" in headers


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

    sym_idx       = col(["scrip_symbol"])          # NSE/BSE ticker symbol (e.g. RELIANCE, BANKBARODA)
    name_idx      = col(["scrip_name"])            # Company display name (e.g. Reliance Industries Ltd.)
    qty_idx       = col(["purchase_qty"])
    rate_idx      = col(["purchase_rate"])
    sell_qty_idx  = col(["sell_qty"])
    stcg_idx      = col(["shorterm_pl", "short_term_pl", "shorterm_p\\l"])
    ltcg_idx      = col(["actual_longterm", "longterm_pl", "actual_longterm_pl"])

    # If no scrip_symbol column, fall back to scrip_name as ticker
    if sym_idx == -1:
        sym_idx = name_idx

    if any(i == -1 for i in [sym_idx, qty_idx, rate_idx]):
        return [], [], ["Could not find required broker columns"]

    open_agg: dict[str, dict] = defaultdict(lambda: {"net_qty": 0.0, "cost_basis": 0.0, "name": ""})
    real_agg: dict[str, dict] = defaultdict(lambda: {"short_term": 0.0, "long_term": 0.0})
    skipped: list[str] = []

    for i, row in enumerate(rows[4:], start=5):
        try:
            symbol = str(row[sym_idx] or "").strip().upper()
            if not symbol or symbol == "NONE":
                continue

            display_name = str(row[name_idx] or "").strip() if name_idx >= 0 else ""

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
                if display_name and not open_agg[symbol]["name"]:
                    open_agg[symbol]["name"] = display_name

        except Exception:
            skipped.append(f"row {i}")

    holdings = [
        {
            "ticker":   _to_exchange_ticker(sym),
            "name":     data["name"] or None,
            "shares":   round(data["net_qty"], 6),
            "avg_cost": round(data["cost_basis"] / data["net_qty"], 4),
        }
        for sym, data in open_agg.items()
        if data["net_qty"] > 0
    ]

    realized_pnls = [
        {
            "ticker":           _to_exchange_ticker(sym),
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
                "name": h.name,
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
    names = {h.ticker: h.name for h in holdings if h.name}
    try:
        current_prices = await market_data.get_current_prices(tickers, names=names)
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

        invested = avg_cost * shares
        total_invested += invested

        if price > 0:
            current_value  = price * shares
            unrealized     = current_value - invested
            pct            = (price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0.0
            total_current_value += current_value
        else:
            # LTP unavailable — assume break-even for portfolio summary totals
            current_value  = None
            unrealized     = None
            pct            = None
            total_current_value += invested  # treat as break-even so summary % isn't distorted

        holding_pnl.append({
            "id":              h.id,
            "ticker":          h.ticker,
            "name":            h.name,
            "shares":          shares,
            "avg_cost":        avg_cost,
            "current_price":   price if price > 0 else None,
            "invested":        round(invested, 2),
            "current_value":   round(current_value, 2) if current_value is not None else None,
            "unrealized_gain": round(unrealized, 2) if unrealized is not None else None,
            "unrealized_pct":  round(pct, 2) if pct is not None else None,
        })

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
        "name": holding.name,
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

    # ── Delete ALL existing holdings and realized P&L before re-importing ──────
    existing_holdings = await db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    )
    for h in existing_holdings.scalars().all():
        await db.delete(h)

    existing_pnl = await db.execute(
        select(RealizedPnL).where(RealizedPnL.portfolio_id == portfolio_id)
    )
    for row in existing_pnl.scalars().all():
        await db.delete(row)
    # ──────────────────────────────────────────────────────────────────────────

    # Insert open holdings
    added_tickers = []
    for h in holdings_to_add:
        db.add(Holding(
            portfolio_id=portfolio_id,
            ticker=h["ticker"],
            name=h.get("name"),
            shares=h["shares"],
            avg_cost=h["avg_cost"],
        ))
        added_tickers.append(h["ticker"])

    # Insert realized P&L
    if realized_to_add:

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


# ── Tax Report ─────────────────────────────────────────────────────────────────

def _tax_excel(client_name: str, holdings, realized_rows, prices: dict) -> openpyxl.Workbook:
    """
    Generate a tax filing workbook with three sheets:
      1. Tax Summary        – AY, STCG/LTCG totals, estimated tax liability
      2. Realized Gains     – Per-stock STCG and LTCG breakdown
      3. Open Positions     – Unrealized P&L on current holdings
    """
    wb = openpyxl.Workbook()

    # ── Colour / font helpers ──────────────────────────────────────────────────
    NAVY   = "1B3A6B"
    BLUE   = "2E6DB4"
    LBLUE  = "D9E8F7"
    GREEN  = "006B3C"
    RED    = "C00000"
    GRAY   = "F5F5F5"
    WHITE  = "FFFFFF"
    BLACK  = "000000"

    def hdr_font(bold=True, color=WHITE, sz=11):
        return Font(bold=bold, color=color, size=sz, name="Calibri")

    def cell_font(bold=False, color=BLACK, sz=10):
        return Font(bold=bold, color=color, size=sz, name="Calibri")

    def fill(hex_color):
        return PatternFill("solid", fgColor=hex_color)

    def thin_border():
        s = Side(style="thin", color="C0C0C0")
        return Border(left=s, right=s, top=s, bottom=s)

    def center(wrap=False):
        return Alignment(horizontal="center", vertical="center", wrap_text=wrap)

    def right_align():
        return Alignment(horizontal="right", vertical="center")

    def inr(ws, row, col, value, color=None):
        cell = ws.cell(row=row, column=col, value=round(float(value), 2))
        cell.number_format = u'₹#,##0.00'
        cell.alignment = right_align()
        cell.border = thin_border()
        cell.font = cell_font(color=color or BLACK)
        return cell

    def label(ws, row, col, text, bold=False, bg=None, fg=BLACK, wrap=False, colspan=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.font = cell_font(bold=bold, color=fg, sz=10)
        cell.alignment = center(wrap) if colspan > 1 else Alignment(vertical="center", wrap_text=wrap)
        cell.border = thin_border()
        if bg:
            cell.fill = fill(bg)
        if colspan > 1:
            ws.merge_cells(start_row=row, start_column=col,
                           end_row=row, end_column=col + colspan - 1)
        return cell

    FY = "2025-26"
    AY = "2026-27"
    today = date_type.today().strftime("%d-%b-%Y")

    # ── Compute totals ─────────────────────────────────────────────────────────
    total_stcg = sum(float(r.short_term_gain) for r in realized_rows)
    total_ltcg = sum(float(r.long_term_gain)  for r in realized_rows)
    ltcg_exempt   = min(max(total_ltcg, 0), 125_000)          # ₹1,25,000 exemption
    ltcg_taxable  = max(total_ltcg - ltcg_exempt, 0)
    tax_stcg      = max(total_stcg, 0) * 0.20                 # 20% on STCG
    tax_ltcg      = ltcg_taxable * 0.125                      # 12.5% on taxable LTCG
    total_tax_est = tax_stcg + tax_ltcg

    total_invested = sum(float(h.avg_cost) * float(h.shares) for h in holdings)
    priced = [(h, prices.get(h.ticker, 0.0)) for h in holdings]
    total_current  = sum(p * float(h.shares) for h, p in priced if p > 0)
    total_unrealized = sum(
        (p - float(h.avg_cost)) * float(h.shares)
        for h, p in priced if p > 0
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 1 – Tax Summary
    # ══════════════════════════════════════════════════════════════════════════
    ws = wb.active
    ws.title = "Tax Summary"
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 22
    ws.row_dimensions[1].height = 8

    # Title banner
    ws.row_dimensions[2].height = 30
    ws.merge_cells("B2:C2")
    t = ws["B2"]
    t.value = f"Capital Gains Tax Report — FY {FY}  |  AY {AY}"
    t.font  = Font(bold=True, color=WHITE, size=14, name="Calibri")
    t.fill  = fill(NAVY)
    t.alignment = center()
    t.border = thin_border()

    # Meta info
    for r, (lbl, val) in enumerate([
        ("Client Name",       client_name),
        ("Assessment Year",   f"AY {AY}"),
        ("Financial Year",    f"FY {FY}  (01-Apr-2025 to 31-Mar-2026)"),
        ("Report Generated",  today),
    ], start=3):
        ws.row_dimensions[r].height = 18
        label(ws, r, 2, lbl, bold=True, bg=LBLUE)
        label(ws, r, 3, val)

    # Spacer
    ws.row_dimensions[7].height = 10

    # ── Section: Realized Capital Gains ───────────────────────────────────────
    ws.row_dimensions[8].height = 20
    ws.merge_cells("B8:C8")
    sh = ws["B8"]
    sh.value = "Section A — Realized Capital Gains (Equity)"
    sh.font, sh.fill, sh.alignment, sh.border = hdr_font(), fill(BLUE), center(), thin_border()

    rows_a = [
        ("Short-Term Capital Gain / Loss (STCG)",    total_stcg),
        ("Long-Term Capital Gain / Loss (LTCG)",     total_ltcg),
        ("LTCG Exemption (up to ₹1,25,000)",        -ltcg_exempt),
        ("Net Taxable LTCG",                         ltcg_taxable),
    ]
    for i, (lbl_text, val) in enumerate(rows_a, start=9):
        ws.row_dimensions[i].height = 18
        label(ws, i, 2, lbl_text, bg=GRAY)
        color = GREEN if val >= 0 else RED
        inr(ws, i, 3, val, color=color)

    # ── Section: Tax Estimate ─────────────────────────────────────────────────
    ws.row_dimensions[13].height = 10
    ws.row_dimensions[14].height = 20
    ws.merge_cells("B14:C14")
    sh2 = ws["B14"]
    sh2.value = "Section B — Estimated Tax Liability"
    sh2.font, sh2.fill, sh2.alignment, sh2.border = hdr_font(), fill(BLUE), center(), thin_border()

    tax_rows = [
        ("Tax on STCG @ 20%  (Section 111A)",   tax_stcg),
        ("Tax on LTCG @ 12.5%  (Section 112A)", tax_ltcg),
        ("Total Estimated Tax",                  total_tax_est),
    ]
    for i, (lbl_text, val) in enumerate(tax_rows, start=15):
        ws.row_dimensions[i].height = 18
        bold = (i == 17)
        label(ws, i, 2, lbl_text, bold=bold, bg=GRAY if not bold else LBLUE)
        inr(ws, i, 3, val, color=RED if val > 0 else GREEN)
        if bold:
            ws.cell(row=i, column=2).font = cell_font(bold=True)

    # ── Section: Open Positions Summary ───────────────────────────────────────
    ws.row_dimensions[18].height = 10
    ws.row_dimensions[19].height = 20
    ws.merge_cells("B19:C19")
    sh3 = ws["B19"]
    sh3.value = "Section C — Open Positions (Unrealized)"
    sh3.font, sh3.fill, sh3.alignment, sh3.border = hdr_font(), fill(BLUE), center(), thin_border()

    open_rows = [
        ("Total Amount Invested (Open Positions)",   total_invested),
        ("Current Portfolio Value (Live Prices)",    total_current),
        ("Unrealized Gain / Loss",                   total_unrealized),
    ]
    for i, (lbl_text, val) in enumerate(open_rows, start=20):
        ws.row_dimensions[i].height = 18
        label(ws, i, 2, lbl_text, bg=GRAY)
        inr(ws, i, 3, val, color=GREEN if val >= 0 else RED)

    # Disclaimer
    ws.row_dimensions[23].height = 10
    ws.row_dimensions[24].height = 30
    ws.merge_cells("B24:C24")
    disc = ws["B24"]
    disc.value = (
        "⚠  Disclaimer: Tax rates as per Finance Act 2024 (STCG 20%, LTCG 12.5% with ₹1.25L "
        "exemption). Figures are computed from broker-uploaded data. Please verify with a "
        "Chartered Accountant before filing your ITR."
    )
    disc.font      = Font(italic=True, color="7F7F7F", size=9, name="Calibri")
    disc.alignment = Alignment(wrap_text=True, vertical="center")

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 2 – Realized Capital Gains (per stock)
    # ══════════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("Realized Capital Gains")
    COL_WIDTHS2 = [2, 32, 16, 18, 18, 20, 20]
    for i, w in enumerate(COL_WIDTHS2, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # Sheet title
    ws2.row_dimensions[2].height = 26
    ws2.merge_cells("B2:G2")
    t2 = ws2["B2"]
    t2.value = f"Realized Capital Gains — FY {FY}  (Equity)"
    t2.font, t2.fill, t2.alignment, t2.border = hdr_font(sz=12), fill(NAVY), center(), thin_border()

    # Column headers
    headers2 = ["#", "Stock Name", "Ticker", "STCG (₹)", "LTCG (₹)", "Tax Est. STCG", "Tax Est. LTCG"]
    ws2.row_dimensions[3].height = 20
    for col, hdr in enumerate(headers2, 2):
        c = ws2.cell(row=3, column=col, value=hdr)
        c.font, c.fill, c.alignment, c.border = hdr_font(), fill(BLUE), center(True), thin_border()

    row = 4
    for idx, r in enumerate(realized_rows, 1):
        stcg = float(r.short_term_gain)
        ltcg = float(r.long_term_gain)
        t_stcg = max(stcg, 0) * 0.20
        t_ltcg = max(ltcg, 0) * 0.125
        bg = WHITE if idx % 2 == 0 else GRAY

        # Find display name from holdings
        h_match = next((h for h in holdings if h.ticker == r.ticker), None)
        dname = (h_match.name or r.ticker) if h_match else r.ticker
        ticker_display = r.ticker.replace(".NS", "").replace(".BO", "")

        ws2.row_dimensions[row].height = 18
        for col, val in enumerate([idx, dname, ticker_display, stcg, ltcg, t_stcg, t_ltcg], 2):
            c = ws2.cell(row=row, column=col, value=val)
            c.border = thin_border()
            c.fill   = fill(bg)
            if col in (5, 6, 7, 8):           # numeric columns
                c.number_format = u'₹#,##0.00'
                c.alignment = right_align()
                c.font = cell_font(color=GREEN if float(val) >= 0 else RED)
            else:
                c.font = cell_font()
        row += 1

    # Totals row
    ws2.row_dimensions[row].height = 20
    total_labels = ["", "TOTAL", "", total_stcg, total_ltcg,
                    max(total_stcg, 0) * 0.20, max(total_ltcg - 125_000, 0) * 0.125]
    for col, val in enumerate(total_labels, 2):
        c = ws2.cell(row=row, column=col, value=val)
        c.font, c.fill, c.border = hdr_font(color=WHITE), fill(NAVY), thin_border()
        if col >= 5:
            c.number_format = u'₹#,##0.00'
            c.alignment = right_align()

    # Tax rate note
    row += 2
    ws2.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
    note = ws2.cell(row=row, column=2,
                    value="Tax Rates: STCG @ 20% (Sec 111A) | LTCG @ 12.5% on gains above ₹1,25,000 (Sec 112A)  |  Finance Act 2024")
    note.font = Font(italic=True, size=9, color="595959", name="Calibri")

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 3 – Open Positions
    # ══════════════════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("Open Positions")
    COL_WIDTHS3 = [2, 32, 14, 10, 16, 16, 18, 18, 14]
    for i, w in enumerate(COL_WIDTHS3, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    ws3.row_dimensions[2].height = 26
    ws3.merge_cells("B2:J2")
    t3 = ws3["B2"]
    t3.value = f"Open Positions as of {today}  |  FY {FY}"
    t3.font, t3.fill, t3.alignment, t3.border = hdr_font(sz=12), fill(NAVY), center(), thin_border()

    headers3 = ["#", "Stock Name", "Ticker", "Qty", "Avg Cost (₹)", "LTP (₹)",
                "Invested (₹)", "Current Value (₹)", "Unrealized P&L (₹)", "P&L %"]
    ws3.row_dimensions[3].height = 20
    for col, hdr in enumerate(headers3, 2):
        c = ws3.cell(row=3, column=col, value=hdr)
        c.font, c.fill, c.alignment, c.border = hdr_font(), fill(BLUE), center(True), thin_border()

    row3 = 4
    for idx, h in enumerate(holdings, 1):
        ltp      = prices.get(h.ticker, 0.0)
        invested = float(h.avg_cost) * float(h.shares)
        cur_val  = ltp * float(h.shares) if ltp > 0 else None
        unreal   = (cur_val - invested) if cur_val is not None else None
        pct      = ((ltp - float(h.avg_cost)) / float(h.avg_cost) * 100) if ltp > 0 and float(h.avg_cost) > 0 else None
        bg       = WHITE if idx % 2 == 0 else GRAY
        name_disp   = h.name or h.ticker
        ticker_disp = h.ticker.replace(".NS", "").replace(".BO", "")

        ws3.row_dimensions[row3].height = 18
        vals = [idx, name_disp, ticker_disp, float(h.shares), float(h.avg_cost),
                ltp if ltp > 0 else "—", invested, cur_val or "—", unreal or "—",
                f"{pct:+.2f}%" if pct is not None else "—"]
        num_cols = {5, 6, 7, 8, 9}
        for col, val in enumerate(vals, 2):
            c = ws3.cell(row=row3, column=col, value=val)
            c.border = thin_border()
            c.fill   = fill(bg)
            if col in num_cols and isinstance(val, (int, float)):
                c.number_format = u'₹#,##0.00'
                c.alignment = right_align()
                if col in (9, 10) and isinstance(val, float):
                    c.font = cell_font(color=GREEN if val >= 0 else RED)
                else:
                    c.font = cell_font()
            elif col == 4:
                c.alignment = right_align()
                c.font = cell_font()
            else:
                c.font = cell_font()
        row3 += 1

    # Total row
    ws3.row_dimensions[row3].height = 20
    tot_vals = ["", "TOTAL", "", "", "", "", total_invested, total_current or "—",
                total_unrealized or "—", ""]
    for col, val in enumerate(tot_vals, 2):
        c = ws3.cell(row=row3, column=col, value=val)
        c.font, c.fill, c.border = hdr_font(color=WHITE), fill(NAVY), thin_border()
        if col in (8, 9, 10) and isinstance(val, (int, float)):
            c.number_format = u'₹#,##0.00'
            c.alignment = right_align()

    return wb


@router.get("/{portfolio_id}/tax-report")
async def download_tax_report(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a Tax P&L report in Excel format for the current FY."""
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    client = await db.get(Client, portfolio.client_id)
    client_name = client.name if client else "Client"

    # Holdings
    h_res = await db.execute(select(Holding).where(Holding.portfolio_id == portfolio_id))
    holdings = h_res.scalars().all()

    # Realized P&L rows
    pnl_res = await db.execute(select(RealizedPnL).where(RealizedPnL.portfolio_id == portfolio_id))
    realized_rows = pnl_res.scalars().all()

    # Live prices for open positions
    tickers = [h.ticker for h in holdings]
    names   = {h.ticker: h.name for h in holdings if h.name}
    try:
        prices = await market_data.get_current_prices(tickers, names=names)
    except Exception:
        prices = {}

    wb = _tax_excel(client_name, holdings, realized_rows, prices)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    safe_name = re.sub(r"[^\w\-]", "_", portfolio.name)
    filename  = f"TaxReport_FY2025-26_{safe_name}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
