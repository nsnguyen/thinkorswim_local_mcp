"""MCP tools for historical snapshots: GEX/IV/VIX/expected move history and snapshot capture."""

from datetime import date

from mcp.server.fastmcp import FastMCP

from src.core.gex_calculator import calculate_aggregate_gex, calculate_per_strike_gex
from src.core.gex_levels import extract_key_levels, find_zero_gamma
from src.core.iv_context import build_iv_context
from src.core.snapshot_store import (
    SnapshotStore,
    compute_backwardation_events,
    compute_current_vs_history,
    compute_expected_move_accuracy,
    compute_iv_trend,
    compute_regime_streak,
    compute_vix_regime_history,
    compute_wall_movement,
    compute_zero_gamma_trend,
)
from src.core.vix_context import build_vix_context
from src.core.volatility import (
    calculate_atm_iv,
    calculate_expected_move_1sd,
    calculate_skew,
    calculate_term_structure,
    classify_term_structure_shape,
    find_atm_contracts,
)
from src.data.models import (
    BackwardationEvent,
    CurrentVsHistory,
    ExpectedMoveAccuracy,
    ExpectedMoveHistory,
    ExpectedMoveSnapshot,
    GexHistory,
    GexSnapshot,
    IVHistory,
    IVSnapshot,
    IVTrend,
    RegimeStreak,
    SnapshotResult,
    VIXHistory,
    VIXRegimeHistory,
    VIXSnapshot,
    WallMovement,
    ZeroGammaTrend,
)
from src.data.schwab_client import SchwabClient


def _capture_snapshot(
    schwab_client: SchwabClient,
    store: SnapshotStore,
    symbol: str,
    today: date,
) -> None:
    """Capture all 4 snapshot types for a symbol on a given date."""
    # GEX snapshot
    chain = schwab_client.get_options_chain(symbol, to_dte=45)
    calls = chain.call_contracts
    puts = chain.put_contracts
    spot = chain.underlying_price

    per_strike = calculate_per_strike_gex(calls, puts, spot)
    key_levels = extract_key_levels(per_strike, spot)
    zero_gamma = find_zero_gamma(per_strike)
    agg = calculate_aggregate_gex(calls, puts, spot)
    regime = "positive" if spot >= zero_gamma.price else "negative"

    store.save(symbol, "gex", {
        "date": today,
        "regime": regime,
        "zero_gamma": zero_gamma.price,
        "call_wall": key_levels["call_wall"].price,
        "put_wall": key_levels["put_wall"].price,
        "max_gamma": key_levels["max_gamma"].price,
        "hvl": key_levels["hvl"].price,
        "total_gex": agg.total_gex,
        "gross_gex": agg.gross_gex,
    })

    # IV snapshot
    atm_iv = calculate_atm_iv(calls, puts, spot)
    skew = calculate_skew(calls, puts, spot)
    ts_points = calculate_term_structure(calls, puts, spot)
    ts_shape = classify_term_structure_shape(ts_points)
    iv_ctx = build_iv_context(atm_iv)

    store.save(symbol, "iv", {
        "date": today,
        "atm_iv": atm_iv,
        "iv_percentile": iv_ctx["percentile"],
        "iv_rank": iv_ctx["rank"],
        "realized_vol_20d": iv_ctx["rv_20d"],
        "iv_rv_premium": iv_ctx["iv_rv_premium"],
        "skew_25d": skew["skew_25d"],
        "skew_regime": skew["regime"],
        "term_structure_shape": ts_shape,
    })

    # VIX snapshot
    vix_quote = schwab_client.get_quote("$VIX")
    vix3m_quote = schwab_client.get_quote("$VIX3M")
    vix_ctx = build_vix_context(vix_quote, vix3m_quote)

    store.save(symbol, "vix", {
        "date": today,
        "vix_level": vix_ctx["vix"]["level"],
        "vix_percentile": vix_ctx["vix"]["percentile"],
        "vix_regime": vix_ctx["vix"]["regime"],
        "vix3m": vix_ctx["vix3m"]["level"],
        "vix_vix3m_ratio": vix_ctx["term_structure"]["ratio"],
        "term_structure": vix_ctx["term_structure"]["shape"],
    })

    # Expected move snapshot (all expirations)
    for exp in chain.expirations:
        try:
            atm_call, atm_put = find_atm_contracts(calls, puts, spot, expiration=exp)
            exp_atm_iv = calculate_atm_iv(calls, puts, spot, expiration=exp)
            straddle = atm_call.mark + atm_put.mark
            em_1sd = calculate_expected_move_1sd(spot, exp_atm_iv, atm_call.days_to_expiration)

            store.save(symbol, "expected_move", {
                "date": today,
                "expiration": exp,
                "expected_move_straddle": round(straddle, 2),
                "expected_move_1sd": round(em_1sd, 2),
                "actual_move": None,
            })
        except Exception:
            continue  # skip expirations with insufficient data


def _auto_snapshot(
    schwab_client: SchwabClient,
    store: SnapshotStore,
    symbol: str,
) -> None:
    """Auto-snapshot if today's snapshot doesn't exist yet."""
    today = date.today()
    if not store.has_snapshot_today(symbol, "gex", today=today):
        _capture_snapshot(schwab_client, store, symbol, today)


def register_tools(
    mcp: FastMCP,
    schwab_client: SchwabClient,
    store: SnapshotStore,
) -> None:
    """Register history tools with the MCP server."""

    @mcp.tool(
        name="take_snapshot",
        description=(
            "Manually capture a daily snapshot of GEX, IV, VIX, and expected move "
            "data for a symbol. Returns 'already_exists' if today's snapshot exists."
        ),
    )
    def take_snapshot(symbol: str = "SPX") -> dict:
        """Capture all snapshot types for today."""
        today = date.today()
        if store.has_snapshot_today(symbol, "gex", today=today):
            return SnapshotResult(
                symbol=symbol, date=today, status="already_exists",
            ).model_dump(mode="json")

        _capture_snapshot(schwab_client, store, symbol, today)
        return SnapshotResult(
            symbol=symbol, date=today, status="saved",
        ).model_dump(mode="json")

    @mcp.tool(
        name="get_gex_history",
        description=(
            "Get GEX history for a symbol: daily snapshots with regime streak, "
            "zero gamma trend, and wall movement over the requested period."
        ),
    )
    def get_gex_history(symbol: str = "SPX", days: int = 30) -> dict:
        """Load GEX history with pre-computed trends."""
        _auto_snapshot(schwab_client, store, symbol)
        rows = store.load(symbol, "gex", days=days)

        result = GexHistory(
            symbol=symbol,
            days=days,
            snapshots=[GexSnapshot(**r) for r in rows],
            regime_streak=RegimeStreak(**compute_regime_streak(rows)),
            zero_gamma_trend=ZeroGammaTrend(**compute_zero_gamma_trend(rows)),
            wall_movement=WallMovement(**compute_wall_movement(rows)),
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_iv_history",
        description=(
            "Get IV history for a symbol: daily snapshots with IV trend "
            "and current-vs-history comparison over the requested period."
        ),
    )
    def get_iv_history(symbol: str = "SPX", days: int = 30) -> dict:
        """Load IV history with pre-computed trends."""
        _auto_snapshot(schwab_client, store, symbol)
        rows = store.load(symbol, "iv", days=days)

        # Get current ATM IV for comparison
        current_iv = rows[-1]["atm_iv"] if rows else 0.0

        result = IVHistory(
            symbol=symbol,
            days=days,
            snapshots=[IVSnapshot(**r) for r in rows],
            iv_trend=IVTrend(**compute_iv_trend(rows)),
            current_vs_history=CurrentVsHistory(
                **compute_current_vs_history(rows, current_iv),
            ),
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_vix_history",
        description=(
            "Get VIX history: daily snapshots with regime breakdown "
            "and backwardation events over the requested period."
        ),
    )
    def get_vix_history(days: int = 30) -> dict:
        """Load VIX history with regime breakdown."""
        # VIX is global — use a fixed symbol for storage
        symbol = "$VIX"
        _auto_snapshot(schwab_client, store, symbol)
        rows = store.load(symbol, "vix", days=days)

        result = VIXHistory(
            days=days,
            snapshots=[VIXSnapshot(**r) for r in rows],
            regime_history=VIXRegimeHistory(**compute_vix_regime_history(rows)),
            backwardation_events=[
                BackwardationEvent(**e) for e in compute_backwardation_events(rows)
            ],
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_expected_move_history",
        description=(
            "Get expected move history for a symbol: daily snapshots "
            "with accuracy statistics (exceed rate, avg ratio)."
        ),
    )
    def get_expected_move_history(symbol: str = "SPX", days: int = 30) -> dict:
        """Load expected move history with accuracy stats."""
        _auto_snapshot(schwab_client, store, symbol)
        rows = store.load(symbol, "expected_move", days=days)

        result = ExpectedMoveHistory(
            symbol=symbol,
            days=days,
            snapshots=[ExpectedMoveSnapshot(**r) for r in rows],
            accuracy=ExpectedMoveAccuracy(**compute_expected_move_accuracy(rows)),
        )
        return result.model_dump(mode="json")
