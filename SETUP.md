# Setup Guide

## Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ (or Docker)

---

## 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY and DATABASE_URL

# Start PostgreSQL (if using Docker)
docker run -d \
  -e POSTGRES_DB=investment_db \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 postgres:16-alpine

# Run the API (tables are created automatically on startup)
uvicorn backend.main:app --reload
# API runs at http://localhost:8000
# Docs at    http://localhost:8000/docs
```

## 2. Frontend

```bash
cd frontend
npm install
npm run dev
# UI runs at http://localhost:5173
```

## 3. Seed demo data (optional)

```bash
# Create a client
curl -X POST http://localhost:8000/api/portfolios/clients \
  -H "Content-Type: application/json" \
  -d '{"name": "Jane Doe", "email": "jane@example.com", "risk_tolerance": "medium"}'

# Create a portfolio with holdings for client_id=1
curl -X POST http://localhost:8000/api/portfolios/clients/1/portfolios \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Growth Portfolio",
    "holdings": [
      {"ticker": "AAPL", "shares": 10, "avg_cost": 150.00},
      {"ticker": "MSFT", "shares": 5,  "avg_cost": 280.00},
      {"ticker": "GOOGL", "shares": 3, "avg_cost": 130.00},
      {"ticker": "AMZN", "shares": 4,  "avg_cost": 175.00},
      {"ticker": "BRK-B", "shares": 8, "avg_cost": 340.00}
    ]
  }'
```

---

## Architecture

```
frontend (React + Vite)
    └── POST /api/chat/          ← streams agent response
    └── GET  /api/portfolios/:id ← holdings data

backend (FastAPI)
    ├── agent/
    │   ├── agent.py      ← Claude claude-sonnet-4-6 multi-turn loop
    │   ├── tools.py      ← tool schemas
    │   └── executor.py   ← tool implementations
    ├── services/
    │   ├── market_data.py         ← yfinance
    │   └── portfolio_analysis.py  ← metrics + optimization
    └── db/
        └── models.py    ← Client, Portfolio, Holding

database (PostgreSQL)
```

## Full Docker setup

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your ANTHROPIC_API_KEY

docker-compose up --build
```
