"""Pydantic v2 data models for Schwab market data."""

from datetime import date, datetime

from pydantic import BaseModel

# ── GEX Models ────────────────────────────────────────────────────


class StrikeGex(BaseModel):
    """Per-strike GEX computation result."""

    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_oi: int
    put_oi: int
    total_volume: int


class KeyLevel(BaseModel):
    """A single key GEX level (wall, zero gamma, max gamma, HVL)."""

    price: float
    gex: float
    call_oi: int
    put_oi: int


class GexRegime(BaseModel):
    """GEX regime classification."""

    type: str  # "positive" | "negative"
    zero_gamma: float
    spot_vs_zero_gamma: float


class TopGexStrike(BaseModel):
    """Ranked entry in top GEX strikes."""

    rank: int
    strike: float
    net_gex: float
    call_oi: int
    put_oi: int


class ZeroDteLevels(BaseModel):
    """Key GEX levels for 0DTE contracts only."""

    call_wall: KeyLevel
    put_wall: KeyLevel
    zero_gamma: KeyLevel
    max_gamma: KeyLevel


class GexLevels(BaseModel):
    """Full get_gex_levels return type."""

    symbol: str
    spot_price: float
    timestamp: datetime
    regime: GexRegime
    key_levels: dict[str, KeyLevel]
    top_10: list[TopGexStrike]
    zero_dte_levels: ZeroDteLevels | None


class GexSummary(BaseModel):
    """Aggregate GEX metrics."""

    symbol: str
    spot_price: float
    timestamp: datetime
    total_gex: float
    gross_gex: float
    total_dex: float
    total_vex: float
    aggregate_theta: float
    call_gex: float
    put_gex: float
    gex_ratio: float
    contracts_analyzed: int


class CharmShift(BaseModel):
    """Charm projection return type."""

    symbol: str
    spot_price: float
    hours_forward: float
    current_zero_gamma: float
    projected_zero_gamma: float
    shift_direction: str  # "higher" | "lower" | "unchanged"
    current_total_gex: float
    projected_total_gex: float


class VannaShift(BaseModel):
    """Vanna projection return type."""

    symbol: str
    spot_price: float
    iv_change_pct: float
    current_zero_gamma: float
    projected_zero_gamma: float
    current_total_gex: float
    projected_total_gex: float


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
