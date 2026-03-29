"""Tests for Phase 4 trade math MCP tools — registration and chain tests.

Verifies: tool registration, evaluate_trade chain, check_alerts chain.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.core.alert_engine import AlertEngine
from src.data.schwab_client import SchwabClient
from src.tools.trade_math import register_tools
from tests.fixtures.factories import (
    build_options_chain_data,
    build_volatility_test_chain,
)

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_mcp() -> FastMCP:
    """Create a FastMCP instance for tool registration testing."""
    return FastMCP("test-trade-math")


@pytest.fixture
def mock_schwab_client() -> MagicMock:
    """Create a mock SchwabClient with realistic option chain data."""
    client = MagicMock(spec=SchwabClient)
    calls, puts = build_volatility_test_chain()
    chain = build_options_chain_data(
        call_contracts=calls,
        put_contracts=puts,
        expirations=[date(2026, 4, 3), date(2026, 4, 10), date(2026, 4, 26)],
        strikes=[5800.0, 5850.0, 5900.0, 5950.0, 6000.0],
    )
    client.get_options_chain.return_value = chain
    return client


@pytest.fixture
def alert_engine(tmp_path) -> AlertEngine:
    """Create an AlertEngine with a temp state directory."""
    return AlertEngine(state_dir=str(tmp_path / "state"))


@pytest.fixture
def registered_tools(
    mock_mcp: FastMCP,
    mock_schwab_client: MagicMock,
    alert_engine: AlertEngine,
) -> dict:
    """Register trade math tools and return a dict of name → handler."""
    register_tools(mock_mcp, mock_schwab_client, alert_engine)
    return {name: fn for name, fn in mock_mcp._tool_manager._tools.items()}


# ── Registration Tests ─────────────────────────────────────────────


class TestRegisterTools:
    """Verify both Phase 4 tools are registered."""

    def test_registers_evaluate_trade(self, registered_tools: dict) -> None:
        """evaluate_trade must be registered for trade analysis."""
        assert "evaluate_trade" in registered_tools

    def test_registers_check_alerts(self, registered_tools: dict) -> None:
        """check_alerts must be registered for monitoring conditions."""
        assert "check_alerts" in registered_tools

    def test_registers_both_tools(self, registered_tools: dict) -> None:
        """Both Phase 4 tools must be registered."""
        expected = {"evaluate_trade", "check_alerts"}
        assert expected.issubset(set(registered_tools.keys()))


# ── Chain Tests ────────────────────────────────────────────────────


class TestEvaluateTradeChain:
    """Test evaluate_trade tool end-to-end."""

    def test_returns_evaluation_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """evaluate_trade should return full evaluation with all fields.

        Verifies the chain: tool → core math → schwab_client → mock API.
        """
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["evaluate_trade"]

        legs = [
            {"strike": 5800.0, "option_type": "PUT", "action": "BUY", "expiration": "2026-04-03"},
            {"strike": 5850.0, "option_type": "PUT", "action": "SELL", "expiration": "2026-04-03"},
        ]
        result = tool.fn(symbol="SPX", legs=legs)

        assert result["symbol"] == "SPX"
        assert "strategy_type" in result
        assert "max_profit" in result
        assert "max_loss" in result
        assert "breakevens" in result
        assert "pop" in result
        assert "net_delta" in result
        assert "net_gamma" in result
        assert "net_theta" in result
        assert "net_vega" in result

    def test_single_leg_works(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """Single leg trade should work without errors."""
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["evaluate_trade"]

        legs = [
            {"strike": 5900.0, "option_type": "CALL", "action": "BUY", "expiration": "2026-04-03"},
        ]
        result = tool.fn(symbol="SPX", legs=legs)
        assert result["strategy_type"] == "long_call"


class TestCheckAlertsChain:
    """Test check_alerts tool end-to-end."""

    def test_add_action(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """Add a condition via the tool."""
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["check_alerts"]

        result = tool.fn(
            action="add",
            condition={"type": "vix_above", "threshold": 20.0},
        )
        assert result["action"] == "add"
        assert result["message"] is not None

    def test_list_action(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """List conditions via the tool."""
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["check_alerts"]

        tool.fn(action="add", condition={"type": "vix_above", "threshold": 20.0})
        result = tool.fn(action="list")
        assert result["action"] == "list"
        assert len(result["conditions"]) == 1

    def test_remove_action(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """Remove a condition via the tool."""
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["check_alerts"]

        tool.fn(action="add", condition={"type": "vix_above", "threshold": 20.0})
        conditions = alert_engine.list_conditions()
        cond_id = conditions[0]["id"]

        result = tool.fn(action="remove", condition={"id": cond_id})
        assert result["action"] == "remove"
        assert len(alert_engine.list_conditions()) == 0

    def test_check_action(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        alert_engine: AlertEngine,
    ) -> None:
        """Check conditions via the tool — should fetch market data and evaluate."""
        register_tools(mock_mcp, mock_schwab_client, alert_engine)
        tool = mock_mcp._tool_manager._tools["check_alerts"]

        tool.fn(
            action="add",
            condition={"type": "price_above", "symbol": "SPX", "threshold": 6000.0},
        )
        result = tool.fn(action="check")
        assert result["action"] == "check"
        assert "results" in result
