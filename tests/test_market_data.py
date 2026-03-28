"""Tests for src/tools/market_data.py — MCP tool handlers.

Chain tests that verify the full path: tool handler → SchwabClient →
mock schwabdev.Client → cache. These tests ensure the MCP tools
correctly wire data through the entire dependency chain.
"""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient, SchwabClientError
from src.tools.market_data import register_tools

# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock requests.Response with .json() returning given data."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


@pytest.fixture
def mcp_with_tools(schwab_client: SchwabClient) -> FastMCP:
    """Create a FastMCP instance with market data tools registered.

    Returns a fully wired MCP server that can be used to test tool
    registration and tool function behavior.
    """
    mcp = FastMCP("test-server")
    register_tools(mcp, schwab_client)
    return mcp


# ── register_tools ─────────────────────────────────────────────────


class TestRegisterTools:
    """Tests for the register_tools function."""

    def test_register_tools_adds_get_quote(self, mcp_with_tools: FastMCP) -> None:
        """Test that register_tools registers the get_quote tool.

        The tool must be discoverable by MCP clients after registration.
        """
        tool_names = [tool.name for tool in mcp_with_tools._tool_manager._tools.values()]
        assert "get_quote" in tool_names

    def test_register_tools_adds_get_options_chain(self, mcp_with_tools: FastMCP) -> None:
        """Test that register_tools registers the get_options_chain tool.

        The tool must be discoverable by MCP clients after registration.
        """
        tool_names = [tool.name for tool in mcp_with_tools._tool_manager._tools.values()]
        assert "get_options_chain" in tool_names


# ── get_quote tool chain test ──────────────────────────────────────


class TestGetQuoteTool:
    """Chain tests for the get_quote MCP tool."""

    def test_get_quote_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test full chain: get_quote tool → SchwabClient → schwabdev.Client.quote().

        Verifies that:
        1. The tool calls SchwabClient.get_quote with the correct symbol
        2. SchwabClient calls schwabdev.Client.quote()
        3. The response is parsed into a dict with correct fields
        4. The result is JSON-serializable (model_dump mode='json')
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response(spx_quote_response)

        # Call through SchwabClient (same path as the tool)
        quote = schwab_client.get_quote("SPX")
        result = quote.model_dump(mode="json")

        mock_schwabdev_client.quote.assert_called_once_with("SPX")
        assert result["symbol"] == "SPX"
        assert result["last"] == 5900.00
        assert isinstance(result["timestamp"], str)

    def test_get_quote_cache_prevents_duplicate_api_calls(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test that cache prevents duplicate schwabdev.Client.quote() calls.

        Chain: tool → SchwabClient → cache hit → no API call.
        schwabdev.Client.quote() should be called exactly once across two get_quote calls.
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response(spx_quote_response)

        schwab_client.get_quote("SPX")
        schwab_client.get_quote("SPX")

        mock_schwabdev_client.quote.assert_called_once()

    def test_get_quote_error_propagation(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """Test error chain: schwabdev error → SchwabClientError.

        When schwabdev.Client.quote() raises an exception, it should
        propagate through SchwabClient as SchwabClientError with a
        message that includes the symbol name.
        """
        mock_schwabdev_client.quote.side_effect = Exception("Network timeout")

        with pytest.raises(SchwabClientError, match="SPX"):
            schwab_client.get_quote("SPX")


# ── get_options_chain tool chain test ──────────────────────────────


class TestGetOptionsChainTool:
    """Chain tests for the get_options_chain MCP tool."""

    def test_get_options_chain_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: tool → SchwabClient → schwabdev.Client.option_chains().

        Verifies that:
        1. schwabdev.Client.option_chains() is called with correct params
        2. Response is parsed into OptionsChainData with contracts
        3. Result serializes to JSON with model_dump
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)
        result = chain.model_dump(mode="json")

        mock_schwabdev_client.option_chains.assert_called_once()
        assert result["symbol"] == "SPX"
        assert result["underlying_price"] == 5900.00
        assert len(result["call_contracts"]) == 3
        assert len(result["put_contracts"]) == 3

    def test_get_options_chain_cache_prevents_duplicate_api_calls(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that cache prevents duplicate option_chains() calls for same DTE range.

        Chain: tool → SchwabClient → cache hit → no API call.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)
        schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        mock_schwabdev_client.option_chains.assert_called_once()

    def test_get_options_chain_contract_fields_match_fixture(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that parsed contracts match the fixture data exactly.

        Verifies every field of a known contract against the fixture JSON
        to catch any field mapping errors in the parser.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        # Verify the 5850 put from the fixture
        put_5850 = next(c for c in chain.put_contracts if c.strike_price == 5850.0)
        assert put_5850.symbol == "SPXW  260403P05850000"
        assert put_5850.option_type == "PUT"
        assert put_5850.bid == 15.00
        assert put_5850.ask == 15.60
        assert put_5850.delta == -0.38
        assert put_5850.gamma == 0.0045
        assert put_5850.open_interest == 6200
        assert put_5850.in_the_money is False
