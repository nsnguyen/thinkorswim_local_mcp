"""MCP tools for Phase 5 market extras: price history, futures, movers, hours, instruments."""

from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient


def register_tools(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    """Register Phase 5 market extras tools with the MCP server."""

    @mcp.tool(
        name="get_price_history",
        description=(
            "Get OHLCV price history candles for a symbol. "
            "Supports equities and ETFs (not futures historical bars). "
            "period_type: 'day'|'month'|'year'|'ytd'. "
            "frequency_type: 'minute'|'daily'|'weekly'|'monthly'. "
            "Default: 1 day of 5-minute bars."
        ),
    )
    def get_price_history(
        symbol: str,
        period_type: str = "day",
        period: int | None = None,
        frequency_type: str = "minute",
        frequency: int = 5,
        extended_hours: bool = False,
    ) -> dict:
        """Fetch OHLCV candles for the given symbol and period."""
        result = schwab_client.get_price_history(
            symbol,
            period_type=period_type,
            period=period,
            frequency_type=frequency_type,
            frequency=frequency,
            extended_hours=extended_hours,
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="get_futures_quote",
        description=(
            "Get a real-time quote for a futures contract. "
            "Common symbols: /ES (S&P 500), /NQ (Nasdaq), /CL (Crude Oil), /GC (Gold). "
            "Use this for overnight futures moves and correlation analysis. "
            "Returns same format as get_quote."
        ),
    )
    def get_futures_quote(symbol: str = "/ES") -> dict:
        """Fetch a real-time quote for a futures symbol."""
        quote = schwab_client.get_quote(symbol)
        return quote.model_dump(mode="json")

    @mcp.tool(
        name="get_market_movers",
        description=(
            "Get top market movers for an index. "
            "index examples: '$SPX', '$COMPX', '$DJI', 'NASDAQ', 'NYSE'. "
            "sort_by: 'VOLUME'|'TRADES'|'PERCENT_CHANGE_UP'|'PERCENT_CHANGE_DOWN'. "
            "Returns symbol, change, change_pct, and volume."
        ),
    )
    def get_market_movers(
        index: str = "$SPX",
        sort_by: str | None = None,
        count: int = 10,
    ) -> dict:
        """Fetch top market movers for the given index."""
        movers = schwab_client.get_market_movers(index, sort_by=sort_by, count=count)
        return {
            "index": index,
            "count": len(movers),
            "movers": [m.model_dump(mode="json") for m in movers],
        }

    @mcp.tool(
        name="get_market_hours",
        description=(
            "Get market session hours and open/closed status. "
            "market: 'equity'|'option'|'future'|'bond'|'forex'. "
            "Returns is_open, regular_start, regular_end, pre/post market times. "
            "Call this before fetching live data to know if market is active."
        ),
    )
    def get_market_hours(market: str = "option", trade_date: str | None = None) -> dict:
        """Fetch session hours and is_open status for the given market type."""
        hours = schwab_client.get_market_hours(market, trade_date=trade_date)
        return hours.model_dump(mode="json")

    @mcp.tool(
        name="search_instruments",
        description=(
            "Search for instruments by symbol or description. "
            "projection: 'symbol-search'|'symbol-regex'|'desc-search'|'desc-regex'|'fundamental'. "
            "Returns symbol, description, exchange, and asset type."
        ),
    )
    def search_instruments(
        query: str,
        projection: str = "symbol-search",
    ) -> dict:
        """Search for instruments matching the given query."""
        instruments = schwab_client.search_instruments(query, projection=projection)
        return {
            "query": query,
            "count": len(instruments),
            "instruments": [inst.model_dump(mode="json") for inst in instruments],
        }

    @mcp.tool(
        name="get_expiration_dates",
        description=(
            "Get all available option expiration dates for a symbol. "
            "Lightweight — uses option_expiration_chain endpoint, not full chain. "
            "Returns expiration dates with DTE and type (weekly/monthly/quarterly/leap). "
            "Use this to find valid expirations before calling get_options_chain."
        ),
    )
    def get_expiration_dates(symbol: str = "SPX") -> dict:
        """Fetch all available option expiration dates for the symbol."""
        expirations = schwab_client.get_expiration_dates(symbol)
        return {
            "symbol": symbol,
            "count": len(expirations),
            "expirations": [exp.model_dump(mode="json") for exp in expirations],
        }
