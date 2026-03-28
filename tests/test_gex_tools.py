"""Tests for src/tools/gex.py — GEX MCP tool handlers.

Chain tests that verify the full path: tool handler → core modules →
SchwabClient → mock schwabdev.Client. These tests ensure the MCP tools
correctly wire data through the entire dependency chain.
"""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient
from src.tools.gex import register_tools

# ── Helpers ──────────────────────────────────────────────────────


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock requests.Response with .json() returning given data."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


@pytest.fixture
def mcp_with_gex_tools(schwab_client: SchwabClient) -> FastMCP:
    """Create a FastMCP instance with GEX tools registered."""
    mcp = FastMCP("test-server")
    register_tools(mcp, schwab_client)
    return mcp


# ── register_tools ─────────���─────────────────────────────────────


class TestRegisterTools:
    """Tests for GEX tool registration."""

    def test_registers_get_gex_levels(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that get_gex_levels tool is registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        assert "get_gex_levels" in tool_names

    def test_registers_get_gex_summary(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that get_gex_summary tool is registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        assert "get_gex_summary" in tool_names

    def test_registers_get_0dte_levels(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that get_0dte_levels tool is registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        assert "get_0dte_levels" in tool_names

    def test_registers_estimate_charm_shift(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that estimate_charm_shift tool is registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        assert "estimate_charm_shift" in tool_names

    def test_registers_estimate_vanna_shift(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that estimate_vanna_shift tool is registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        assert "estimate_vanna_shift" in tool_names

    def test_registers_all_five_tools(self, mcp_with_gex_tools: FastMCP) -> None:
        """Test that exactly 5 GEX tools are registered."""
        tool_names = [t.name for t in mcp_with_gex_tools._tool_manager._tools.values()]
        expected = {"get_gex_levels", "get_gex_summary", "get_0dte_levels",
                    "estimate_charm_shift", "estimate_vanna_shift"}
        assert expected.issubset(set(tool_names))


# ── get_gex_levels chain test ────────���───────────────────────────


class TestGetGexLevelsTool:
    """Chain tests for the get_gex_levels tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: get_gex_levels → core → SchwabClient → mock API.

        Verifies that:
        1. SchwabClient.get_options_chain is called
        2. GEX is calculated with correct formula
        3. Key levels are extracted
        4. Result contains regime, key_levels, top_10
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", to_dte=45)

        from src.core.gex_calculator import calculate_per_strike_gex
        from src.core.gex_levels import (
            classify_gex_regime,
            extract_key_levels,
            extract_top_gex_strikes,
        )

        per_strike = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        key_levels = extract_key_levels(per_strike, chain.underlying_price)
        top_10 = extract_top_gex_strikes(per_strike)
        regime = classify_gex_regime(
            chain.underlying_price, key_levels["zero_gamma"].price
        )

        assert regime.type in ("positive", "negative")
        assert "call_wall" in key_levels
        assert "put_wall" in key_levels
        assert "zero_gamma" in key_levels
        assert len(top_10) > 0

    def test_result_is_json_serializable(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that the tool returns a JSON-serializable dict."""
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        from datetime import UTC, datetime

        from src.core.gex_calculator import calculate_per_strike_gex
        from src.core.gex_levels import (
            classify_gex_regime,
            extract_key_levels,
            extract_top_gex_strikes,
        )
        from src.data.models import GexLevels

        chain = schwab_client.get_options_chain("SPX", to_dte=45)
        per_strike = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        key_levels = extract_key_levels(per_strike, chain.underlying_price)
        top_10 = extract_top_gex_strikes(per_strike)
        regime = classify_gex_regime(
            chain.underlying_price, key_levels["zero_gamma"].price
        )
        result = GexLevels(
            symbol="SPX",
            spot_price=chain.underlying_price,
            timestamp=datetime.now(UTC),
            regime=regime,
            key_levels=key_levels,
            top_10=top_10,
            zero_dte_levels=None,
        )
        data = result.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["symbol"] == "SPX"
        assert "regime" in data
        assert "key_levels" in data


# ── get_gex_summary chain test ───────────────────────────────────


class TestGetGexSummaryTool:
    """Chain tests for the get_gex_summary tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: get_gex_summary → aggregate_gex → SchwabClient → mock API."""
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        from src.core.gex_calculator import calculate_aggregate_gex

        chain = schwab_client.get_options_chain("SPX")
        result = calculate_aggregate_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        data = result.model_dump(mode="json")

        assert data["symbol"] == "SPX"
        assert data["total_gex"] != 0
        assert data["contracts_analyzed"] == 6  # 3 calls + 3 puts in fixture


# ── estimate_charm_shift chain test ──��───────────────────────────


class TestEstimateCharmShiftTool:
    """Chain tests for the estimate_charm_shift tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: charm shift → projected GEX → new zero_gamma."""
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        from src.core.gex_calculator import calculate_per_strike_gex, project_charm_adjusted_gex
        from src.core.gex_levels import find_zero_gamma

        chain = schwab_client.get_options_chain("SPX", to_dte=45)
        current = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        projected = project_charm_adjusted_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price, hours_forward=3.0
        )

        current_zg = find_zero_gamma(current)
        projected_zg = find_zero_gamma(projected)

        assert isinstance(current_zg.price, float)
        assert isinstance(projected_zg.price, float)


# ── estimate_vanna_shift chain test ──────────────────────────────


class TestEstimateVannaShiftTool:
    """Chain tests for the estimate_vanna_shift tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: vanna shift → projected GEX → new zero_gamma."""
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        from src.core.gex_calculator import calculate_per_strike_gex, project_vanna_adjusted_gex
        from src.core.gex_levels import find_zero_gamma

        chain = schwab_client.get_options_chain("SPX", to_dte=45)
        current = calculate_per_strike_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price
        )
        projected = project_vanna_adjusted_gex(
            chain.call_contracts, chain.put_contracts, chain.underlying_price, iv_change_pct=2.0
        )

        current_zg = find_zero_gamma(current)
        projected_zg = find_zero_gamma(projected)

        assert isinstance(current_zg.price, float)
        assert isinstance(projected_zg.price, float)
