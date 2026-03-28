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


# ── Volatility Models ─────────────────────────────────────────────


class IVContext(BaseModel):
    """IV context with percentile, rank, realized vol.

    History-dependent fields are None until Phase 3B provides historical data.
    """

    percentile: float | None
    rank: float | None
    rv_20d: float | None
    iv_rv_premium: float | None
    regime: str  # "low", "normal", "elevated", "high"


class SkewData(BaseModel):
    """IV skew measurements across delta targets."""

    put_25d: float
    call_25d: float
    skew_25d: float
    skew_10d: float
    skew_40d: float
    butterfly: float
    regime: str  # "normal_skew", "steep_skew", "flat_skew", "inverted"


class TermStructurePoint(BaseModel):
    """ATM IV at a single expiration."""

    expiration: date
    dte: int
    atm_iv: float


class TermStructure(BaseModel):
    """IV term structure analysis."""

    shape: str  # "contango", "backwardation", "flat", "humped"
    slope: float
    by_expiration: list[TermStructurePoint]


class VolatilityAnalysis(BaseModel):
    """Full volatility analysis return type."""

    symbol: str
    spot_price: float
    timestamp: datetime
    atm_iv: float
    iv_context: IVContext
    skew: SkewData
    term_structure: TermStructure


class IVSurfacePoint(BaseModel):
    """Single point on the IV surface."""

    strike: float
    dte: int
    iv: float
    delta: float
    expiration: date


class IVSurface(BaseModel):
    """IV surface data."""

    symbol: str
    spot_price: float
    timestamp: datetime
    surface: list[IVSurfacePoint]


class VIXData(BaseModel):
    """VIX quote data with regime."""

    level: float
    change: float
    percentile: float | None  # None until Phase 3B
    regime: str  # "low", "normal", "elevated", "high"


class VIX3MData(BaseModel):
    """VIX3M level."""

    level: float


class VIXTermStructure(BaseModel):
    """VIX/VIX3M term structure."""

    ratio: float
    shape: str  # "contango", "backwardation", "flat"


class VIXContext(BaseModel):
    """Full VIX context return type."""

    timestamp: datetime
    vix: VIXData
    vix3m: VIX3MData
    term_structure: VIXTermStructure


class ExpectedMoveResult(BaseModel):
    """Expected move for a single expiration."""

    symbol: str
    spot_price: float
    expiration: date
    dte: int
    atm_strike: float
    atm_iv: float
    expected_move_straddle: float
    expected_move_1sd: float
    upper_bound: float
    lower_bound: float
    upper_bound_1sd: float
    lower_bound_1sd: float


class ExpectedMoveMulti(BaseModel):
    """Expected move across multiple expirations."""

    symbol: str
    spot_price: float
    timestamp: datetime
    expirations: list[ExpectedMoveResult]


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
