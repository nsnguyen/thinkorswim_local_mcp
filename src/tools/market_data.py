"""MCP tools for market data: get_quote and get_options_chain."""

from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient


def register_tools(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    """Register market data tools with the MCP server."""

    @mcp.tool(
        name="get_quote",
        description=(
            "Get a real-time quote for any symbol. "
            "Supports equities (AAPL), indices (SPX), futures (/ES), and VIX ($VIX). "
            "Returns last price, bid/ask, OHLC, volume, and net change."
        ),
    )
    def get_quote(symbol: str) -> dict:
        """Fetch a real-time quote for the given symbol."""
        quote = schwab_client.get_quote(symbol)
        return quote.model_dump(mode="json")

    @mcp.tool(
        name="get_options_chain",
        description=(
            "Get the full options chain for a symbol with greeks, OI, and volume. "
            "Fetches across all DTE ranges (including LEAPs) with smart caching. "
            "Use from_dte/to_dte to narrow the range. "
            "Use min_open_interest/min_volume to filter low-activity contracts."
        ),
    )
    def get_options_chain(
        symbol: str,
        contract_type: str = "ALL",
        from_dte: int | None = None,
        to_dte: int | None = None,
        min_open_interest: int = 0,
        min_volume: int = 0,
    ) -> dict:
        """Fetch the options chain with multi-range DTE caching.

        Args:
            symbol: Underlying symbol (e.g., SPX, AAPL, SPY)
            contract_type: "ALL", "CALL", or "PUT"
            from_dte: Minimum days to expiration (None = 0)
            to_dte: Maximum days to expiration (None = all)
            min_open_interest: Filter contracts below this OI threshold
            min_volume: Filter contracts below this volume threshold
        """
        chain = schwab_client.get_options_chain(
            symbol=symbol,
            contract_type=contract_type,
            from_dte=from_dte,
            to_dte=to_dte,
            min_open_interest=min_open_interest,
            min_volume=min_volume,
        )
        return chain.model_dump(mode="json")
