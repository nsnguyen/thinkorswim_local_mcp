"""Pydantic v2 data models for Schwab market data."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class OptionContract(BaseModel):
    """Single option contract with greeks and market data."""

    symbol: str
    underlying_symbol: str
    option_type: str  # "CALL" | "PUT"
    strike_price: float
    expiration_date: date
    days_to_expiration: int
    bid: float
    ask: float
    last: float
    mark: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    in_the_money: bool
    multiplier: float = 100.0


class OptionsChainData(BaseModel):
    """Full options chain for a symbol."""

    symbol: str
    underlying_price: float
    timestamp: datetime
    call_contracts: list[OptionContract]
    put_contracts: list[OptionContract]
    expirations: list[date]
    strikes: list[float]
    is_delayed: bool


class Quote(BaseModel):
    """Real-time quote for any symbol."""

    symbol: str
    last: float
    bid: float
    ask: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    net_change: float
    net_change_pct: float
    is_delayed: bool
    timestamp: datetime
