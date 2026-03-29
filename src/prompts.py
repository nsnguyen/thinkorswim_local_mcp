"""MCP Prompts for Phase 5 — reusable workflow instructions for Claude.

Prompts guide Claude through multi-tool workflows by returning structured
messages that set the context and sequence of tool calls.
"""

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """Register all MCP prompts with the server."""

    @mcp.prompt(
        name="morning_briefing",
        description=(
            "Pre-market briefing: VIX context, GEX regime, futures move, expected range."
        ),
    )
    def morning_briefing() -> list[dict]:
        """Structured pre-market workflow for daily market assessment."""
        return [
            {
                "role": "user",
                "content": (
                    "Run a complete pre-market morning briefing using this sequence:\n\n"
                    "1. **Market status** — call get_market_hours('option') "
                    "to confirm session times\n"
                    "2. **Futures overnight move** — call get_futures_quote('/ES') "
                    "for overnight S&P move\n"
                    "3. **VIX context** — call get_vix_context() for VIX level, "
                    "regime, and VIX/VIX3M term structure\n"
                    "4. **GEX regime** — call get_gex_levels('SPX') for dealer positioning: "
                    "regime (positive/negative), zero gamma level, call wall, put wall\n"
                    "5. **Volatility analysis** — call analyze_volatility('SPX') "
                    "for ATM IV, IV rank, and skew\n"
                    "6. **Expected move** — call get_expected_move('SPX') "
                    "for nearest weekly straddle and 1SD range\n\n"
                    "Synthesize all data into a structured briefing. "
                    "Report facts and numbers only — no trade recommendations."
                ),
            }
        ]

    @mcp.prompt(
        name="iron_condor_scan",
        description=(
            "Scan for iron condor setup using GEX walls, expected move, and IV analysis."
        ),
    )
    def iron_condor_scan(symbol: str = "SPX") -> list[dict]:
        """Multi-tool iron condor candidate workflow for the given symbol."""
        return [
            {
                "role": "user",
                "content": (
                    f"Scan {symbol} for an iron condor setup using this sequence:\n\n"
                    f"1. **GEX levels** — call get_gex_levels('{symbol}') "
                    f"to identify call wall, put wall, and GEX regime\n"
                    f"2. **Expected move** — call get_expected_move('{symbol}') "
                    f"for the straddle price and 1SD range — outer bounds\n"
                    f"3. **Volatility** — call analyze_volatility('{symbol}') "
                    f"to assess IV rank and skew; high IV rank favors credit selling\n"
                    f"4. **Options chain** — call get_options_chain('{symbol}', "
                    f"from_dte=21, to_dte=45) to see available strikes near GEX walls\n"
                    f"5. **Evaluate trade** — call evaluate_trade('{symbol}', legs=[...]) "
                    f"with chosen strikes to get max profit/loss, POP, and breakevens\n\n"
                    f"Report the raw data from each step. "
                    f"Do not recommend a trade — present the numbers."
                ),
            }
        ]

    @mcp.prompt(
        name="regime_check",
        description=(
            "Quick GEX + VIX regime snapshot: positive or negative gamma, "
            "trending or mean-reverting."
        ),
    )
    def regime_check() -> list[dict]:
        """Quick regime assessment combining GEX dealer positioning and VIX fear gauge."""
        return [
            {
                "role": "user",
                "content": (
                    "Perform a quick market regime check:\n\n"
                    "1. **GEX regime** — call get_gex_levels('SPX') and report:\n"
                    "   - Regime type (positive/negative gamma)\n"
                    "   - Zero gamma level vs current spot\n"
                    "   - Call wall and put wall prices\n"
                    "2. **VIX context** — call get_vix_context() and report:\n"
                    "   - VIX level and regime (low/normal/elevated/high)\n"
                    "   - VIX/VIX3M ratio and term structure shape\n\n"
                    "Combine: positive GEX + low VIX = mean-reverting, range-bound. "
                    "Negative GEX + elevated VIX = trending, directional. "
                    "State the regime classification with supporting numbers."
                ),
            }
        ]

    @mcp.prompt(
        name="intraday_levels",
        description=(
            "0DTE intraday key levels: GEX walls, charm shift projection, "
            "expected move for session."
        ),
    )
    def intraday_levels() -> list[dict]:
        """0DTE-focused intraday levels for the current session."""
        return [
            {
                "role": "user",
                "content": (
                    "Identify key intraday levels for today's 0DTE session:\n\n"
                    "1. **0DTE GEX levels** — call get_0dte_levels('SPX') for:\n"
                    "   - 0DTE call wall, put wall, zero gamma, max gamma\n"
                    "2. **Charm shift** — call estimate_charm_shift('SPX', hours_forward=3.0) "
                    "to see how zero gamma is projected to move by EOD\n"
                    "3. **0DTE expected move** — call get_expected_move('SPX') "
                    "for today's 0DTE straddle price and intraday 1SD range\n\n"
                    "Report all levels numerically. Flag any charm shift that would "
                    "move zero gamma by more than 10 points before close."
                ),
            }
        ]
