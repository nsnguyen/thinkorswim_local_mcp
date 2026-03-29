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


# ── Snapshot Models (Phase 3B) ───────────────────────────────────


class GexSnapshot(BaseModel):
    """Daily GEX snapshot — one row per day per symbol."""

    date: date
    regime: str  # "positive" | "negative"
    zero_gamma: float
    call_wall: float
    put_wall: float
    max_gamma: float
    hvl: float
    total_gex: float
    gross_gex: float


class IVSnapshot(BaseModel):
    """Daily IV snapshot — one row per day per symbol."""

    date: date
    atm_iv: float
    iv_percentile: float | None
    iv_rank: float | None
    realized_vol_20d: float | None
    iv_rv_premium: float | None
    skew_25d: float
    skew_regime: str
    term_structure_shape: str


class VIXSnapshot(BaseModel):
    """Daily VIX snapshot."""

    date: date
    vix_level: float
    vix_percentile: float | None
    vix_regime: str
    vix3m: float
    vix_vix3m_ratio: float
    term_structure: str  # "contango" | "backwardation" | "flat"


class ExpectedMoveSnapshot(BaseModel):
    """Daily expected move snapshot — one per expiration per symbol."""

    date: date
    expiration: date
    expected_move_straddle: float
    expected_move_1sd: float
    actual_move: float | None  # backfilled next trading day


class RegimeStreak(BaseModel):
    """Consecutive days of the same GEX regime."""

    type: str
    days: int


class ZeroGammaTrend(BaseModel):
    """Zero gamma level movement over time."""

    direction: str  # "rising" | "falling" | "flat"
    change_5d: float | None
    min_30d: float | None
    max_30d: float | None


class WallMovement(BaseModel):
    """Call/put wall movement over 5 days."""

    call_wall_5d_change: float | None
    put_wall_5d_change: float | None


class GexHistory(BaseModel):
    """GEX history with pre-computed trends."""

    symbol: str
    days: int
    snapshots: list[GexSnapshot]
    regime_streak: RegimeStreak
    zero_gamma_trend: ZeroGammaTrend
    wall_movement: WallMovement


class IVTrend(BaseModel):
    """IV trend over time."""

    direction: str  # "rising" | "falling" | "flat"
    change_5d: float | None
    min_30d: float | None
    max_30d: float | None


class CurrentVsHistory(BaseModel):
    """Current IV relative to history."""

    iv_percentile: float | None
    days_above_current: int
    days_below_current: int


class IVHistory(BaseModel):
    """IV history with pre-computed trends."""

    symbol: str
    days: int
    snapshots: list[IVSnapshot]
    iv_trend: IVTrend
    current_vs_history: CurrentVsHistory


class VIXRegimeHistory(BaseModel):
    """Count of days in each VIX regime over period."""

    days_low: int
    days_normal: int
    days_elevated: int
    days_high: int


class BackwardationEvent(BaseModel):
    """A period when VIX/VIX3M went into backwardation."""

    date: date
    ratio: float
    duration_days: int


class VIXHistory(BaseModel):
    """VIX history with regime breakdown."""

    days: int
    snapshots: list[VIXSnapshot]
    regime_history: VIXRegimeHistory
    backwardation_events: list[BackwardationEvent]


class ExpectedMoveAccuracy(BaseModel):
    """Expected move accuracy statistics."""

    times_exceeded: int
    times_within: int
    exceed_rate: float
    avg_ratio: float | None
    max_ratio: float | None


class ExpectedMoveHistory(BaseModel):
    """Expected move history with accuracy stats."""

    symbol: str
    days: int
    snapshots: list[ExpectedMoveSnapshot]
    accuracy: ExpectedMoveAccuracy


class SnapshotResult(BaseModel):
    """Result of take_snapshot tool."""

    symbol: str
    date: date
    status: str  # "saved" | "already_exists"


# ── Trade Math Models (Phase 4) ──────────────────────────────────


class TradeLeg(BaseModel):
    """A single leg of an options trade."""

    strike: float
    option_type: str  # "CALL" | "PUT"
    action: str  # "BUY" | "SELL"
    expiration: date
    quantity: int = 1


class TradeEvaluation(BaseModel):
    """Full evaluation of a multi-leg options trade."""

    symbol: str
    spot_price: float
    strategy_type: str
    legs: list[TradeLeg]
    net_credit: float  # positive = credit, negative = debit
    max_profit: float
    max_loss: float
    breakevens: list[float]
    pop: float  # probability of profit (0-1)
    expected_value: float
    risk_reward: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float


class AlertCondition(BaseModel):
    """A persisted alert condition."""

    id: str
    type: str  # gex_flip, iv_rank_above, vix_above, wall_breach, price_above, etc.
    symbol: str | None = None
    threshold: float | None = None
    wall: str | None = None  # "call" | "put" for wall_breach
    created_at: datetime


class AlertResult(BaseModel):
    """Result of evaluating a single alert condition."""

    condition: AlertCondition
    status: str  # "triggered" | "clear"
    current_value: float | None = None
    previous_value: float | None = None
    details: str | None = None


class AlertCheckResult(BaseModel):
    """Result of check_alerts action."""

    action: str
    results: list[AlertResult] | None = None
    conditions: list[AlertCondition] | None = None
    message: str | None = None


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


# ── Market Extras Models (Phase 5) ────────────────────────────────


class PriceCandle(BaseModel):
    """Single OHLCV candle from price history."""

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceHistory(BaseModel):
    """Price history candles for a symbol."""

    symbol: str
    period_type: str
    frequency_type: str
    candles: list[PriceCandle]
    is_delayed: bool = False


class MarketMover(BaseModel):
    """Single entry from market movers list."""

    symbol: str
    description: str
    last: float
    change: float
    change_pct: float
    volume: int


class MarketHours(BaseModel):
    """Market session hours for a given market type."""

    market: str
    is_open: bool
    regular_start: str | None
    regular_end: str | None
    pre_market_start: str | None
    pre_market_end: str | None
    post_market_start: str | None
    post_market_end: str | None


class Instrument(BaseModel):
    """Instrument search result."""

    symbol: str
    description: str
    exchange: str
    asset_type: str
    cusip: str | None = None


class ExpirationDate(BaseModel):
    """Single available options expiration."""

    expiration_date: date
    dte: int
    expiration_type: str  # "weekly" | "monthly" | "quarterly" | "leap"
