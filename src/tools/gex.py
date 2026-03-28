"""MCP tools for GEX analysis: levels, summary, 0DTE, charm/vanna projections."""

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from src.core.gex_calculator import (
    calculate_aggregate_gex,
    calculate_per_strike_gex,
    project_charm_adjusted_gex,
    project_vanna_adjusted_gex,
)
from src.core.gex_levels import (
    classify_gex_regime,
    extract_key_levels,
    extract_top_gex_strikes,
    extract_zero_dte_levels,
    find_zero_gamma,
)
from src.data.models import CharmShift, GexLevels, VannaShift
from src.data.schwab_client import SchwabClient


def register_tools(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    """Register GEX analysis tools with the MCP server."""

    @mcp.tool(
        name="get_gex_levels",
        description=(
            "Get GEX levels for a symbol: regime (positive/negative), key levels "
            "(call wall, put wall, zero gamma, max gamma, HVL), top 10 GEX strikes, "
            "and optional 0DTE levels. GEX formula: |gamma| * OI * 100 * spot^2 * 0.01."
        ),
    )
    def get_gex_levels(
        symbol: str = "SPX",
        max_dte: int = 45,
        include_0dte: bool = True,
    ) -> dict:
        """Fetch options chain and compute GEX levels with regime classification."""
        chain = schwab_client.get_options_chain(symbol, to_dte=max_dte)
        per_strike = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        key_levels = extract_key_levels(per_strike, chain.underlying_price)
        top_10 = extract_top_gex_strikes(per_strike)
        regime = classify_gex_regime(
            chain.underlying_price, key_levels["zero_gamma"].price
        )
        zero_dte = (
            extract_zero_dte_levels(
                chain.call_contracts, chain.put_contracts, chain.underlying_price
            )
            if include_0dte
            else None
        )
        result = GexLevels(
            symbol=symbol,
            spot_price=chain.underlying_price,
            timestamp=datetime.now(UTC),
            regime=regime,
            key_levels=key_levels,
            top_10=top_10,
            zero_dte_levels=zero_dte,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_gex_summary",
        description=(
            "Get aggregate GEX metrics: total/gross GEX, DEX (delta exposure), "
            "VEX (vega exposure), aggregate theta, call/put GEX breakdown, and GEX ratio."
        ),
    )
    def get_gex_summary(symbol: str = "SPX") -> dict:
        """Fetch options chain and compute aggregate GEX metrics."""
        chain = schwab_client.get_options_chain(symbol)
        result = calculate_aggregate_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_0dte_levels",
        description=(
            "Get GEX levels for 0DTE contracts only. Same structure as get_gex_levels "
            "but filtered to same-day expiration contracts."
        ),
    )
    def get_0dte_levels(symbol: str = "SPX") -> dict:
        """Fetch options chain and compute GEX levels for 0DTE contracts only."""
        chain = schwab_client.get_options_chain(symbol, to_dte=0)
        per_strike = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        key_levels = extract_key_levels(per_strike, chain.underlying_price)
        top_10 = extract_top_gex_strikes(per_strike)
        regime = classify_gex_regime(
            chain.underlying_price, key_levels["zero_gamma"].price
        )
        result = GexLevels(
            symbol=symbol,
            spot_price=chain.underlying_price,
            timestamp=datetime.now(UTC),
            regime=regime,
            key_levels=key_levels,
            top_10=top_10,
            zero_dte_levels=None,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="estimate_charm_shift",
        description=(
            "Project how GEX levels shift due to charm (time decay) over a given number of hours. "
            "Shows current vs projected zero gamma and total GEX. Charm approx: -theta/spot."
        ),
    )
    def estimate_charm_shift(
        symbol: str = "SPX",
        hours_forward: float = 3.0,
    ) -> dict:
        """Project GEX level shifts from charm decay."""
        chain = schwab_client.get_options_chain(symbol, to_dte=45)
        spot = chain.underlying_price

        current = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, spot
        )
        projected = project_charm_adjusted_gex(
            chain.call_contracts, chain.put_contracts, spot, hours_forward
        )

        current_zg = find_zero_gamma(current)
        projected_zg = find_zero_gamma(projected)
        current_total = sum(sg.net_gex for sg in current)
        projected_total = sum(sg.net_gex for sg in projected)

        if projected_zg.price > current_zg.price:
            direction = "higher"
        elif projected_zg.price < current_zg.price:
            direction = "lower"
        else:
            direction = "unchanged"

        result = CharmShift(
            symbol=symbol,
            spot_price=spot,
            hours_forward=hours_forward,
            current_zero_gamma=current_zg.price,
            projected_zero_gamma=projected_zg.price,
            shift_direction=direction,
            current_total_gex=current_total,
            projected_total_gex=projected_total,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="estimate_vanna_shift",
        description=(
            "Project how GEX levels shift if IV changes by a given percentage. "
            "Shows current vs projected zero gamma and total GEX. Vanna approx: vega/spot."
        ),
    )
    def estimate_vanna_shift(
        symbol: str = "SPX",
        iv_change_pct: float = 2.0,
    ) -> dict:
        """Project GEX level shifts from an IV change via vanna."""
        chain = schwab_client.get_options_chain(symbol, to_dte=45)
        spot = chain.underlying_price

        current = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, spot
        )
        projected = project_vanna_adjusted_gex(
            chain.call_contracts, chain.put_contracts, spot, iv_change_pct
        )

        current_zg = find_zero_gamma(current)
        projected_zg = find_zero_gamma(projected)
        current_total = sum(sg.net_gex for sg in current)
        projected_total = sum(sg.net_gex for sg in projected)

        result = VannaShift(
            symbol=symbol,
            spot_price=spot,
            iv_change_pct=iv_change_pct,
            current_zero_gamma=current_zg.price,
            projected_zero_gamma=projected_zg.price,
            current_total_gex=current_total,
            projected_total_gex=projected_total,
        )
        return result.model_dump(mode="json")
