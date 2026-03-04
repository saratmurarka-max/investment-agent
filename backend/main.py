import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.api.routes.chat import router as chat_router
from backend.api.routes.portfolio import router as portfolio_router
from backend.api.routes.stocks import router as stocks_router
from backend.db.database import AsyncSessionLocal, Base, engine
from backend.db.models import Client, Portfolio
from backend.services.nse import get_nse_stocks


async def _init_db() -> None:
    """
    Non-blocking DB initialisation — runs as a background task so the
    HTTP server starts accepting connections immediately (fixes Render
    port-scan timeout when Neon has a cold-start delay).
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Client).where(Client.id == 1))
            if not result.scalar_one_or_none():
                client = Client(
                    name="Demo Client",
                    email="demo@example.com",
                    risk_tolerance="medium",
                )
                session.add(client)
                await session.flush()
                portfolio = Portfolio(
                    client_id=client.id,
                    name="My Portfolio",
                    currency="INR",
                )
                session.add(portfolio)
                await session.commit()

        # Pre-warm the NSE stock cache after DB is ready
        asyncio.create_task(get_nse_stocks())

    except Exception:
        import traceback
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick off DB setup in the background — returns instantly so the
    # port is bound and health-checks succeed before Neon is ready.
    asyncio.create_task(_init_db())
    yield


app = FastAPI(
    title="Investment Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(stocks_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
