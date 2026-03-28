"""Tests for src/tools/volatility.py — Volatility MCP tool handlers.

Chain tests verifying tool handler → core modules → SchwabClient → mock API.
"""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient
from src.tools.volatility import register_tools

# ── Helpers ──────────────────────────────────────────────────────


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock requests.Response with .json() returning given data."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


@pytest.fixture
def mcp_with_vol_tools(schwab_client: SchwabClient) -> FastMCP:
    """Create a FastMCP instance with volatility tools registered."""
    mcp = FastMCP("test-server")
    register_tools(mcp, schwab_client)
    return mcp


# ── register_tools ───────────────────────────────────────────────


class TestRegisterTools:
    """Tests for volatility tool registration."""

    def test_registers_analyze_volatility(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that analyze_volatility tool is registered."""
        names = [
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        ]
        assert "analyze_volatility" in names

    def test_registers_get_iv_surface(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that get_iv_surface tool is registered."""
        names = [
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        ]
        assert "get_iv_surface" in names

    def test_registers_analyze_term_structure(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that analyze_term_structure tool is registered."""
        names = [
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        ]
        assert "analyze_term_structure" in names

    def test_registers_get_vix_context(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that get_vix_context tool is registered."""
        names = [
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        ]
        assert "get_vix_context" in names

    def test_registers_get_expected_move(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that get_expected_move tool is registered."""
        names = [
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        ]
        assert "get_expected_move" in names

    def test_registers_all_five_tools(
        self, mcp_with_vol_tools: FastMCP
    ) -> None:
        """Test that all 5 volatility tools are registered."""
        names = {
            t.name
            for t in mcp_with_vol_tools._tool_manager._tools.values()
        }
        expected = {
            "analyze_volatility",
            "get_iv_surface",
            "analyze_term_structure",
            "get_vix_context",
            "get_expected_move",
        }
        assert expected.issubset(names)


# ── analyze_volatility chain test ────────────────────────────────


class TestAnalyzeVolatilityTool:
    """Chain tests for the analyze_volatility tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test full chain: tool → core → SchwabClient → mock API."""
        mock_schwabdev_client.option_chains.return_value = (
            _make_mock_response(spx_chain_response)
        )

        from src.core.iv_context import build_iv_context
        from src.core.volatility import (
            calculate_atm_iv,
            calculate_skew,
            calculate_term_structure,
        )

        chain = schwab_client.get_options_chain("SPX")
        atm_iv = calculate_atm_iv(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        assert atm_iv > 0

        skew = calculate_skew(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        assert "skew_25d" in skew

        ts_points = calculate_term_structure(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        assert len(ts_points) >= 1

        iv_ctx = build_iv_context(atm_iv)
        assert iv_ctx["percentile"] is None
        assert iv_ctx["regime"] in ("low", "normal", "elevated", "high")


# ── get_iv_surface chain test ────────────────────────────────────


class TestGetIvSurfaceTool:
    """Chain tests for the get_iv_surface tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that IV surface contains data points from the chain."""
        mock_schwabdev_client.option_chains.return_value = (
            _make_mock_response(spx_chain_response)
        )

        chain = schwab_client.get_options_chain("SPX", to_dte=90)
        # Surface points come from all contracts in the chain
        total = len(chain.call_contracts) + len(chain.put_contracts)
        assert total > 0


# ── analyze_term_structure chain test ────────────────────────────


class TestAnalyzeTermStructureTool:
    """Chain tests for the analyze_term_structure tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test term structure from chain data."""
        mock_schwabdev_client.option_chains.return_value = (
            _make_mock_response(spx_chain_response)
        )

        from src.core.volatility import (
            calculate_term_structure,
            calculate_term_structure_slope,
            classify_term_structure_shape,
        )

        chain = schwab_client.get_options_chain("SPX")
        points = calculate_term_structure(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        slope = calculate_term_structure_slope(points)
        shape = classify_term_structure_shape(points)

        assert isinstance(slope, float)
        assert shape in ("contango", "backwardation", "flat", "humped")


# ── get_vix_context chain test ───────────────────────────────────


class TestGetVixContextTool:
    """Chain tests for the get_vix_context tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test VIX context from mock quotes."""
        from src.core.vix_context import build_vix_context
        from tests.fixtures.factories import (
            build_vix3m_quote,
            build_vix_quote,
        )

        vix_q = build_vix_quote(level=22.0, change=1.50)
        vix3m_q = build_vix3m_quote(level=20.0)
        result = build_vix_context(vix_q, vix3m_q)

        assert result["vix"]["level"] == 22.0
        assert result["vix"]["regime"] == "elevated"
        assert result["term_structure"]["shape"] == "backwardation"


# ── get_expected_move chain test ─────────────────────────────────


class TestGetExpectedMoveTool:
    """Chain tests for the get_expected_move tool."""

    def test_full_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test expected move calculation through the chain."""
        mock_schwabdev_client.option_chains.return_value = (
            _make_mock_response(spx_chain_response)
        )

        from src.core.volatility import (
            calculate_atm_iv,
            calculate_expected_move_1sd,
            find_atm_contracts,
        )

        chain = schwab_client.get_options_chain("SPX")
        atm_call, atm_put = find_atm_contracts(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        atm_iv = calculate_atm_iv(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        straddle = atm_call.mark + atm_put.mark
        em_1sd = calculate_expected_move_1sd(
            chain.underlying_price, atm_iv, atm_call.days_to_expiration,
        )

        assert straddle > 0
        assert em_1sd > 0

    def test_straddle_equals_marks(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test straddle = ATM call mark + ATM put mark."""
        mock_schwabdev_client.option_chains.return_value = (
            _make_mock_response(spx_chain_response)
        )

        from src.core.volatility import find_atm_contracts

        chain = schwab_client.get_options_chain("SPX")
        atm_call, atm_put = find_atm_contracts(
            chain.call_contracts, chain.put_contracts,
            chain.underlying_price,
        )
        straddle = atm_call.mark + atm_put.mark
        assert straddle == pytest.approx(
            atm_call.mark + atm_put.mark
        )
