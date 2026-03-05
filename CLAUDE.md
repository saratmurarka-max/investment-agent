# Investment Agent — Claude Project Context

## What This App Is

A full-stack **investment portfolio management** web app for **PROFITMART** broker clients.

- **Backend**: FastAPI (Python 3.11), async, deployed on **Render**
- **Frontend**: React + Vite + Tailwind CSS, deployed on **Vercel**
- **Database**: Neon PostgreSQL (async via SQLAlchemy)
- **Key libs**: `openpyxl`, `xlrd`, `yfinance`, `Pillow`, `pandas`

---

## Architecture

```
investment-agent/
├── backend/
│   ├── api/routes/portfolio.py   ← ALL core logic (1600+ lines)
│   ├── db/models.py               ← SQLAlchemy ORM models
│   ├── db/database.py             ← Async engine + session
│   ├── services/market_data.py   ← yfinance price fetcher
│   ├── main.py                    ← FastAPI app entry
│   └── requirements.txt
├── frontend/
│   └── src/components/
│       ├── AddHoldings.tsx        ← File upload + portfolio UI
│       └── ...
└── render.yaml                    ← Render deployment config
```

---

## Database Models

| Model | Key fields |
|---|---|
| `Client` | id, name, email, risk_tolerance |
| `Portfolio` | id, client_id, name, currency, broker_client_id |
| `Holding` | id, portfolio_id, ticker, name, shares, avg_cost |
| `RealizedPnL` | id, portfolio_id, ticker, short_term_gain, long_term_gain |
| `DerivativeTrade` | id, portfolio_id, scrip_symbol, instrument_type, option_type, underlying, expiry_date, strike_price, trade_date, buy_qty, buy_rate, buy_amount, sell_date, sell_qty, sell_rate, sell_amount, booked_pnl, booked_profit, booked_loss |

---

## Key Helpers in `portfolio.py`

### `_read_excel_rows(contents, filename) -> list[tuple]`
Dispatcher that supports **three** file formats:
1. **HTML-disguised XLS** — detects `contents.lstrip()[:1] == b'<'`, parses with built-in `html.parser.HTMLParser` (no extra deps). PROFITMART's `.xls` exports are HTML tables, not real BIFF files.
2. **Real .xls (BIFF)** — uses `xlrd`
3. **.xlsx** — uses `openpyxl`

### `_is_broker_format(rows)` / `_parse_broker_format(rows)`
Detects and parses PROFITMART equity P&L report. Row structure:
- `rows[0]`: "PROFITMART SECURITIES PVT. LTD."
- `rows[1]`: "Portfolio Report"
- `rows[2]`: "From Date :..."
- `rows[3]`: Column headers (Scrip_Symbol, Purchase_Qty, Purchase_Rate, Sell_Qty, Shorterm P\L, Actual Longterm, ...)
- `rows[4+]`: Data rows

Returns: `(holdings, realized_pnls, skipped, client_info)`

### `_is_derivative_format(rows)` / `_parse_derivative_format(rows)`
Detects/parses PROFITMART DER P&L report (same row structure).
Key columns: `Instrument_Type`, `Booked_P/L`, `Booked_Profit`, `Booked_Loss`.
Returns: `(trades, skipped, client_info)`

### `_get_fy_dividends(holdings) -> list[dict]`
Fetches FY 2025-26 dividends via yfinance for each open holding.
- Filters ex-dates: 01-Apr-2025 → 31-Mar-2026
- Returns `[{ticker, display, ticker_clean, ex_date, dps, shares, total}]`
- Runs via `asyncio.to_thread` in the async endpoint

### `_tax_excel(client_name, holdings, realized_rows, prices, deriv_summary=None, dividend_rows=None) -> Workbook`
Generates the Tax P&L Excel report. Sheets:
1. **Tax Summary** — Sections A–E: Capital Gains, Tax Estimate, Open Positions, F&O P&L, Dividend Income
2. **Realized Capital Gains** — per-stock STCG/LTCG
3. **Open Positions** — unrealized P&L with live prices
4. **F&O Summary** — monthly derivative P&L (optional)
5. **Dividend Income** — per-stock per-ex-date dividends (optional)

All sheets have the PROFITMART logo (embedded as base64 PNG constant `_PROFITMART_LOGO_B64`).

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/portfolios/clients` | Create client |
| GET | `/portfolios/clients/{id}/portfolios` | List portfolios |
| POST | `/portfolios/clients/{id}/portfolios` | Create portfolio |
| GET | `/portfolios/{id}` | Get portfolio + holdings |
| GET | `/portfolios/{id}/pnl` | Unrealized + realized P&L |
| POST | `/portfolios/{id}/holdings` | Add single holding |
| DELETE | `/portfolios/{id}/holdings` | Clear all holdings |
| DELETE | `/portfolios/{id}/holdings/{hid}` | Delete one holding |
| POST | `/portfolios/{id}/holdings/upload` | Upload equity XLS/XLSX |
| POST | `/portfolios/{id}/derivatives/upload` | Upload derivatives XLS/XLSX |
| GET | `/portfolios/{id}/derivatives/pnl` | F&O P&L stats |
| DELETE | `/portfolios/{id}/derivatives` | Clear all derivatives |
| GET | `/portfolios/{id}/tax-report` | Download tax Excel |

---

## Tax Report Logic (FY 2025-26 / AY 2026-27)

- **STCG**: taxed @ 20% (Section 111A)
- **LTCG**: exempt up to ₹1,25,000; taxed @ 12.5% above (Section 112A) — Finance Act 2024
- **F&O**: taxed as Business Income (PGBP, non-speculative) — file ITR-3
- **Dividends**: fully taxable at slab rate post Finance Act 2020; TDS @ 10% if >₹5,000/company/year

---

## Frontend — `AddHoldings.tsx`

- Two upload tabs: **Upload Equity File** / **Upload Derivatives File**
- Both accept `.xlsx` and `.xls`
- Client-side extension check before upload
- Shows upload success/error, skipped rows, detected format

---

## Git / Deployment

- **Branch**: `feat/xls-file-support` (3 commits ahead of `main`)
  - `3d86e20` — .xls file format support (xlrd + HTML detection)
  - `8464f97` — Dividend income report (Section E + Sheet 5)
  - `2a517a5` — Fix HTML-disguised XLS (PROFITMART HTML table parser)
- **PR**: https://github.com/saratmurarka-max/investment-agent/pull/new/feat/xls-file-support
- Auto-deploys on merge to `main`: Render (backend) + Vercel (frontend)

---

## Known Issues / Notes

- Dividend share count uses **current open position** as proxy for holding on ex-date (individual buy/sell transaction dates are not stored per-row in the DB, only aggregated position).
- NSE/BSE direct scraping not used (anti-scraping); yfinance used instead.
- `_to_exchange_ticker()` defaults to `.NS` (NSE); numeric codes (e.g. `531637-EQ`) → `.BO` (BSE).
- Client ID cross-validation: derivative upload checks `broker_client_id` matches equity upload to prevent mixing client files.
