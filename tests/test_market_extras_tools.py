"""Tests for Phase 5 market extras MCP tool registration and chain.

Verifies: all 6 tools registered, each tool calls the correct SchwabClient method,
and returns the expected structure.
"""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.data.models import (
    ExpirationDate,
    Instrument,
    MarketHours,
    MarketMover,
    PriceHistory,
)
from src.data.schwab_client import SchwabClient
from src.tools.market_extras import register_tools
from tests.fixtures.factories import build_quote

# ── Helpers ────────────────────────────────────────────────────────

_EXPECTED_TOOLS = {
    "get_price_history",
    "get_futures_quote",
    "get_market_movers",
    "get_market_hours",
    "search_instruments",
    "get_expiration_dates",
}


def _make_price_history() -> PriceHistory:
    from datetime import UTC, datetime

    from src.data.models import PriceCandle

    return PriceHistory(
        symbol="SPX",
        period_type="day",
        frequency_type="minute",
        candles=[
            PriceCandle(
                datetime=datetime(2026, 3, 28, 9, 30, tzinfo=UTC),
                open=5880.0, high=5920.0, low=5870.0, close=5905.0, volume=1200000,
            ),
        ],
        is_delayed=False,
    )


def _make_market_movers() -> list[MarketMover]:
    return [
        MarketMover(
            symbol="NVDA", description="NVIDIA", last=880.0,
            change=25.0, change_pct=2.92, volume=45000000,
        ),
        MarketMover(
            symbol="TSLA", description="Tesla", last=220.0,
            change=-8.0, change_pct=-3.51, volume=30000000,
        ),
    ]


def _make_market_hours() -> MarketHours:
    return MarketHours(
        market="option",
        is_open=True,
        regular_start="2026-03-28T09:30:00-04:00",
        regular_end="2026-03-28T16:00:00-04:00",
        pre_market_start=None,
        pre_market_end=None,
        post_market_start=None,
        post_market_end=None,
    )


def _make_instruments() -> list[Instrument]:
    return [
        Instrument(
            symbol="SPY", description="SPDR S&P 500 ETF Trust",
            exchange="PACF", asset_type="ETF",
        ),
    ]


def _make_expiration_dates() -> list[ExpirationDate]:
    from datetime import date
    return [
        ExpirationDate(expiration_date=date(2026, 3, 28), dte=0, expiration_type="weekly"),
        ExpirationDate(expiration_date=date(2026, 4, 4), dte=7, expiration_type="weekly"),
        ExpirationDate(expiration_date=date(2026, 4, 17), dte=20, expiration_type="monthly"),
    ]


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_mcp() -> FastMCP:
    """Create a FastMCP instance for tool registration testing."""
    return FastMCP("test-market-extras")


@pytest.fixture
def mock_schwab_client() -> MagicMock:
    """Create a mock SchwabClient with Phase 5 methods configured."""
    client = MagicMock(spec=SchwabClient)
    client.get_price_history.return_value = _make_price_history()
    client.get_quote.return_value = build_quote(symbol="/ES", last=5920.0)
    client.get_market_movers.return_value = _make_market_movers()
    client.get_market_hours.return_value = _make_market_hours()
    client.search_instruments.return_value = _make_instruments()
    client.get_expiration_dates.return_value = _make_expiration_dates()
    return client


@pytest.fixture
def registered_tools(mock_mcp: FastMCP, mock_schwab_client: MagicMock) -> dict:
    """Register market extras tools and return name → handler dict."""
    register_tools(mock_mcp, mock_schwab_client)
    return {name: fn for name, fn in mock_mcp._tool_manager._tools.items()}


# ── Registration Tests ─────────────────────────────────────────────


class TestRegisterTools:
    """Verify all 6 Phase 5 tools are registered."""

    def test_registers_all_expected_tools(self, registered_tools: dict) -> None:
        """All 6 Phase 5 market tools must be registered.

        Missing registration means the tool is unavailable in Claude's context.
        """
        assert _EXPECTED_TOOLS.issubset(set(registered_tools.keys()))

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_TOOLS))
    def test_each_tool_registered(self, registered_tools: dict, tool_name: str) -> None:
        """Each individual Phase 5 tool must be registered.

        Tests each tool name individually for clearer failure messages.
        """
        assert tool_name in registered_tools


# ── Chain Tests ────────────────────────────────────────────────────


class TestGetPriceHistoryChain:
    """Test get_price_history tool end-to-end."""

    def test_calls_schwab_client_method(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_price_history must call schwab_client.get_price_history.

        Verifies the tool delegates to the correct client method.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_price_history"]

        tool.fn(symbol="SPX")

        mock_schwab_client.get_price_history.assert_called_once()

    def test_returns_candles_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_price_history must return a dict with candles list.

        Verifies the tool serializes the PriceHistory model correctly.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_price_history"]

        result = tool.fn(symbol="SPX")

        assert "symbol" in result
        assert "candles" in result
        assert isinstance(result["candles"], list)
        assert len(result["candles"]) == 1

    def test_passes_period_params(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_price_history must forward period/frequency params to the client.

        Verifies parameter forwarding from tool to client method.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_price_history"]

        tool.fn(symbol="AAPL", period_type="month", period=1, frequency_type="daily", frequency=1)

        call_kwargs = mock_schwab_client.get_price_history.call_args[1]
        assert call_kwargs.get("period_type") == "month"


class TestGetFuturesQuoteChain:
    """Test get_futures_quote tool end-to-end."""

    def test_calls_get_quote(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_futures_quote must delegate to schwab_client.get_quote.

        The tool is a thin wrapper over get_quote for discoverability.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_futures_quote"]

        tool.fn(symbol="/ES")

        mock_schwab_client.get_quote.assert_called_once_with("/ES")

    def test_returns_quote_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_futures_quote must return a Quote-shaped dict.

        Verifies the tool returns the same format as get_quote.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_futures_quote"]

        result = tool.fn(symbol="/ES")

        assert result["symbol"] == "/ES"
        assert "last" in result
        assert "bid" in result
        assert "ask" in result


class TestGetMarketMoversChain:
    """Test get_market_movers tool end-to-end."""

    def test_returns_movers_list(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_market_movers must return a list of mover dicts.

        Verifies the movers are serialized correctly from Pydantic models.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_market_movers"]

        result = tool.fn(index="$SPX")

        assert "movers" in result
        assert isinstance(result["movers"], list)
        assert result["movers"][0]["symbol"] == "NVDA"

    def test_passes_count_to_client(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_market_movers must pass count parameter to the client method.

        Ensures the tool doesn't silently ignore user-specified count limits.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_market_movers"]

        tool.fn(index="$SPX", count=5)

        call_kwargs = mock_schwab_client.get_market_movers.call_args[1]
        assert call_kwargs.get("count") == 5


class TestGetMarketHoursChain:
    """Test get_market_hours tool end-to-end."""

    def test_returns_market_hours_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_market_hours must return a dict with is_open and session times.

        Verifies the MarketHours model is serialized correctly.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_market_hours"]

        result = tool.fn(market="option")

        assert "market" in result
        assert "is_open" in result
        assert result["is_open"] is True
        assert "regular_start" in result

    def test_passes_market_to_client(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_market_hours must pass market type to the client method."""
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_market_hours"]

        tool.fn(market="equity")

        call_args = mock_schwab_client.get_market_hours.call_args
        assert "equity" in str(call_args)


class TestSearchInstrumentsChain:
    """Test search_instruments tool end-to-end."""

    def test_returns_instruments_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """search_instruments must return a dict with instruments list.

        Verifies the Instrument models are serialized correctly.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["search_instruments"]

        result = tool.fn(query="SPY")

        assert "instruments" in result
        assert isinstance(result["instruments"], list)
        assert result["instruments"][0]["symbol"] == "SPY"

    def test_passes_query_to_client(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """search_instruments must pass query and projection to the client method."""
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["search_instruments"]

        tool.fn(query="Apple", projection="desc-search")

        call_args = mock_schwab_client.search_instruments.call_args
        assert "Apple" in str(call_args)


class TestGetExpirationDatesChain:
    """Test get_expiration_dates tool end-to-end."""

    def test_returns_expiration_list(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_expiration_dates must return a dict with expirations list.

        Verifies the ExpirationDate models are serialized correctly.
        """
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_expiration_dates"]

        result = tool.fn(symbol="SPX")

        assert "symbol" in result
        assert "expirations" in result
        assert isinstance(result["expirations"], list)
        assert len(result["expirations"]) == 3

    def test_passes_symbol_to_client(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
    ) -> None:
        """get_expiration_dates must pass symbol to the client method."""
        register_tools(mock_mcp, mock_schwab_client)
        tool = mock_mcp._tool_manager._tools["get_expiration_dates"]

        tool.fn(symbol="AAPL")

        mock_schwab_client.get_expiration_dates.assert_called_once_with("AAPL")
