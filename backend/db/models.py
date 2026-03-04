from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    risk_tolerance: Mapped[str] = mapped_column(String(10), default="medium")  # low/medium/high
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="client")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="portfolios")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    realized_pnls: Mapped[list["RealizedPnL"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    derivative_trades: Mapped[list["DerivativeTrade"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # average cost per share
    purchased_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")


class RealizedPnL(Base):
    """Stores realized gains/losses from sold positions (populated from broker uploads)."""
    __tablename__ = "realized_pnl"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    short_term_gain: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # STCG
    long_term_gain: Mapped[Decimal] = mapped_column(Numeric(18, 4))   # LTCG

    portfolio: Mapped["Portfolio"] = relationship(back_populates="realized_pnls")


class DerivativeTrade(Base):
    """Stores F&O trades from broker derivative P&L uploads (PROFITMART DER P&L format)."""
    __tablename__ = "derivative_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    scrip_symbol: Mapped[str] = mapped_column(String(150))
    instrument_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)   # OP, FU
    option_type: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)         # CE, PE
    underlying: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)         # NIFTY
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    strike_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    trade_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    buy_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    buy_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    buy_amount: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    sell_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sell_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    sell_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    sell_amount: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    booked_pnl: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    booked_profit: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    booked_loss: Mapped[Decimal] = mapped_column(Numeric(16, 4))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="derivative_trades")
