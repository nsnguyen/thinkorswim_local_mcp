"""MCP tools for volatility analysis: IV skew, term structure, surface, VIX, expected move."""

from datetime import UTC, date, datetime

from mcp.server.fastmcp import FastMCP

from src.core.iv_context import build_iv_context
from src.core.vix_context import build_vix_context
from src.core.volatility import (
    calculate_atm_iv,
    calculate_expected_move_1sd,
    calculate_skew,
    calculate_term_structure,
    calculate_term_structure_slope,
    classify_term_structure_shape,
    find_atm_contracts,
)
from src.data.models import (
    ExpectedMoveMulti,
    ExpectedMoveResult,
    IVContext,
    IVSurface,
    IVSurfacePoint,
    SkewData,
    TermStructure,
    VIX3MData,
    VIXContext,
    VIXData,
    VIXTermStructure,
    VolatilityAnalysis,
)
from src.data.schwab_client import SchwabClient


def register_tools(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    """Register volatility analysis tools with the MCP server."""

    @mcp.tool(
        name="analyze_volatility",
        description=(
            "Full volatility analysis: ATM IV, IV context (regime), "
            "skew (25d/10d/40d, butterfly), and term structure "
            "(shape, slope, by expiration)."
        ),
    )
    def analyze_volatility(symbol: str = "SPX") -> dict:
        """Fetch chain and compute comprehensive volatility metrics."""
        chain = schwab_client.get_options_chain(symbol)
        calls = chain.call_contracts
        puts = chain.put_contracts
        spot = chain.underlying_price

        atm_iv = calculate_atm_iv(calls, puts, spot)
        skew_data = calculate_skew(calls, puts, spot)
        ts_points = calculate_term_structure(calls, puts, spot)
        slope = calculate_term_structure_slope(ts_points)
        shape = classify_term_structure_shape(ts_points)
        iv_ctx = build_iv_context(atm_iv)

        result = VolatilityAnalysis(
            symbol=symbol,
            spot_price=spot,
            timestamp=datetime.now(UTC),
            atm_iv=atm_iv,
            iv_context=IVContext(**iv_ctx),
            skew=SkewData(**skew_data),
            term_structure=TermStructure(
                shape=shape, slope=slope, by_expiration=ts_points,
            ),
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_iv_surface",
        description=(
            "Get IV surface grid: IV values across strikes and expirations. "
            "Each point includes strike, DTE, IV, and delta."
        ),
    )
    def get_iv_surface(
        symbol: str = "SPX",
        num_strikes: int = 20,
        max_dte: int = 90,
    ) -> dict:
        """Build IV surface from chain data."""
        chain = schwab_client.get_options_chain(symbol, to_dte=max_dte)
        spot = chain.underlying_price

        # Filter to num_strikes nearest to spot on each side
        all_strikes = sorted(set(chain.strikes))
        if all_strikes:
            # Find strikes nearest to spot
            all_strikes.sort(key=lambda s: abs(s - spot))
            selected = set(all_strikes[: num_strikes * 2])
        else:
            selected = set()

        points = []
        for c in chain.call_contracts + chain.put_contracts:
            if c.strike_price in selected and c.implied_volatility > 0:
                points.append(
                    IVSurfacePoint(
                        strike=c.strike_price,
                        dte=c.days_to_expiration,
                        iv=c.implied_volatility,
                        delta=c.delta,
                        expiration=c.expiration_date,
                    )
                )

        result = IVSurface(
            symbol=symbol,
            spot_price=spot,
            timestamp=datetime.now(UTC),
            surface=points,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="analyze_term_structure",
        description=(
            "Analyze IV term structure: ATM IV across expirations, "
            "shape (contango/backwardation/flat/humped), and slope."
        ),
    )
    def analyze_term_structure(symbol: str = "SPX") -> dict:
        """Compute IV term structure analysis."""
        chain = schwab_client.get_options_chain(symbol)
        ts_points = calculate_term_structure(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        slope = calculate_term_structure_slope(ts_points)
        shape = classify_term_structure_shape(ts_points)

        result = TermStructure(
            shape=shape, slope=slope, by_expiration=ts_points,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_vix_context",
        description=(
            "Get VIX context: VIX level, regime, VIX3M level, "
            "and VIX/VIX3M term structure (contango/backwardation)."
        ),
    )
    def get_vix_context() -> dict:
        """Fetch VIX and VIX3M quotes and build context."""
        vix_quote = schwab_client.get_quote("$VIX")
        vix3m_quote = schwab_client.get_quote("$VIX3M")
        ctx = build_vix_context(vix_quote, vix3m_quote)

        result = VIXContext(
            timestamp=datetime.now(UTC),
            vix=VIXData(**ctx["vix"]),
            vix3m=VIX3MData(**ctx["vix3m"]),
            term_structure=VIXTermStructure(**ctx["term_structure"]),
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_expected_move",
        description=(
            "Calculate expected move for a symbol: straddle-based and "
            "1SD (IV-based) expected moves with upper/lower bounds. "
            "Use multiple_expirations=True for all expirations."
        ),
    )
    def get_expected_move(
        symbol: str = "SPX",
        expiration: str | None = None,
        multiple_expirations: bool = False,
    ) -> dict:
        """Compute expected move from ATM straddle and IV."""
        chain = schwab_client.get_options_chain(symbol)
        calls = chain.call_contracts
        puts = chain.put_contracts
        spot = chain.underlying_price

        def _compute_for_exp(exp: date) -> ExpectedMoveResult:
            atm_call, atm_put = find_atm_contracts(
                calls, puts, spot, expiration=exp,
            )
            atm_iv = calculate_atm_iv(calls, puts, spot, expiration=exp)
            straddle = atm_call.mark + atm_put.mark
            em_1sd = calculate_expected_move_1sd(
                spot, atm_iv, atm_call.days_to_expiration,
            )
            return ExpectedMoveResult(
                symbol=symbol,
                spot_price=spot,
                expiration=exp,
                dte=atm_call.days_to_expiration,
                atm_strike=atm_call.strike_price,
                atm_iv=atm_iv,
                expected_move_straddle=round(straddle, 2),
                expected_move_1sd=round(em_1sd, 2),
                upper_bound=round(spot + straddle, 2),
                lower_bound=round(spot - straddle, 2),
                upper_bound_1sd=round(spot + em_1sd, 2),
                lower_bound_1sd=round(spot - em_1sd, 2),
            )

        if multiple_expirations:
            results = [_compute_for_exp(exp) for exp in chain.expirations]
            multi = ExpectedMoveMulti(
                symbol=symbol,
                spot_price=spot,
                timestamp=datetime.now(UTC),
                expirations=results,
            )
            return multi.model_dump(mode="json")

        # Single expiration
        if expiration:
            target_exp = date.fromisoformat(expiration)
        else:
            target_exp = chain.expirations[0]  # nearest

        result = _compute_for_exp(target_exp)
        return result.model_dump(mode="json")
