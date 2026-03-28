"""Tests for Phase 3B history MCP tools — registration and chain tests.

Verifies: tool registration, take_snapshot chain, history tool auto-snapshot,
and proper model serialization.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.core.snapshot_store import SnapshotStore
from src.data.schwab_client import SchwabClient
from src.tools.history import register_tools
from tests.fixtures.factories import (
    build_options_chain_data,
    build_vix3m_quote,
    build_vix_quote,
    build_volatility_test_chain,
)

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_mcp() -> FastMCP:
    """Create a FastMCP instance for tool registration testing."""
    return FastMCP("test-history")


@pytest.fixture
def mock_schwab_client() -> MagicMock:
    """Create a mock SchwabClient with realistic returns."""
    client = MagicMock(spec=SchwabClient)
    calls, puts = build_volatility_test_chain()
    chain = build_options_chain_data(
        call_contracts=calls,
        put_contracts=puts,
        expirations=[date(2026, 4, 3), date(2026, 4, 10), date(2026, 4, 26)],
        strikes=[5800.0, 5850.0, 5900.0, 5950.0, 6000.0],
    )
    client.get_options_chain.return_value = chain
    client.get_quote.side_effect = lambda sym: (
        build_vix_quote() if sym == "$VIX" else build_vix3m_quote()
    )
    return client


@pytest.fixture
def store(tmp_path) -> SnapshotStore:
    """Create a SnapshotStore with a temp directory."""
    return SnapshotStore(base_dir=str(tmp_path / "snapshots"))


@pytest.fixture
def registered_tools(
    mock_mcp: FastMCP,
    mock_schwab_client: MagicMock,
    store: SnapshotStore,
) -> dict:
    """Register history tools and return a dict of name → handler."""
    register_tools(mock_mcp, mock_schwab_client, store)
    return {name: fn for name, fn in mock_mcp._tool_manager._tools.items()}


# ── Registration Tests ─────────────────────────────────────────────


class TestRegisterTools:
    """Verify all 5 history tools are registered."""

    def test_registers_take_snapshot(self, registered_tools: dict) -> None:
        """take_snapshot must be registered for manual snapshot capture."""
        assert "take_snapshot" in registered_tools

    def test_registers_get_gex_history(self, registered_tools: dict) -> None:
        """get_gex_history must be registered for GEX trend analysis."""
        assert "get_gex_history" in registered_tools

    def test_registers_get_iv_history(self, registered_tools: dict) -> None:
        """get_iv_history must be registered for IV trend analysis."""
        assert "get_iv_history" in registered_tools

    def test_registers_get_vix_history(self, registered_tools: dict) -> None:
        """get_vix_history must be registered for VIX regime breakdown."""
        assert "get_vix_history" in registered_tools

    def test_registers_get_expected_move_history(self, registered_tools: dict) -> None:
        """get_expected_move_history must be registered for accuracy tracking."""
        assert "get_expected_move_history" in registered_tools

    def test_registers_all_five_tools(self, registered_tools: dict) -> None:
        """All 5 Phase 3B tools must be registered — no more, no fewer."""
        expected = {
            "take_snapshot",
            "get_gex_history",
            "get_iv_history",
            "get_vix_history",
            "get_expected_move_history",
        }
        assert expected.issubset(set(registered_tools.keys()))


# ── Chain Tests ────────────────────────────────────────────────────


class TestTakeSnapshotChain:
    """Test take_snapshot tool end-to-end."""

    def test_saves_all_snapshot_types(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """take_snapshot should save GEX, IV, VIX, and expected move snapshots.

        This is the core data capture — if any type is missed, history is incomplete.
        """
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["take_snapshot"]
        result = tool.fn(symbol="SPX")

        assert result["status"] == "saved"
        assert result["symbol"] == "SPX"

        # All 4 types should have data
        assert len(store.load("SPX", "gex")) == 1
        assert len(store.load("SPX", "iv")) == 1
        assert len(store.load("SPX", "vix")) == 1
        assert len(store.load("SPX", "expected_move")) >= 1

    def test_already_exists(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """Second take_snapshot same day should return 'already_exists'.

        Prevents wasteful duplicate API calls.
        """
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["take_snapshot"]
        tool.fn(symbol="SPX")
        result = tool.fn(symbol="SPX")
        assert result["status"] == "already_exists"


class TestGetGexHistoryChain:
    """Test get_gex_history tool end-to-end."""

    def test_returns_history_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """get_gex_history should return snapshots with trend data.

        Verifies the full chain: auto-snapshot → load → compute trends → serialize.
        """
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["get_gex_history"]
        result = tool.fn(symbol="SPX", days=30)

        assert result["symbol"] == "SPX"
        assert result["days"] == 30
        assert "snapshots" in result
        assert "regime_streak" in result
        assert "zero_gamma_trend" in result
        assert "wall_movement" in result


class TestGetIvHistoryChain:
    """Test get_iv_history tool end-to-end."""

    def test_returns_history_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """get_iv_history should return snapshots with IV trend data."""
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["get_iv_history"]
        result = tool.fn(symbol="SPX", days=30)

        assert result["symbol"] == "SPX"
        assert "snapshots" in result
        assert "iv_trend" in result
        assert "current_vs_history" in result


class TestGetVixHistoryChain:
    """Test get_vix_history tool end-to-end."""

    def test_returns_history_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """get_vix_history should return snapshots with regime breakdown."""
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["get_vix_history"]
        result = tool.fn(days=30)

        assert result["days"] == 30
        assert "snapshots" in result
        assert "regime_history" in result
        assert "backwardation_events" in result


class TestGetExpectedMoveHistoryChain:
    """Test get_expected_move_history tool end-to-end."""

    def test_returns_history_structure(
        self,
        mock_mcp: FastMCP,
        mock_schwab_client: MagicMock,
        store: SnapshotStore,
    ) -> None:
        """get_expected_move_history should return snapshots with accuracy stats."""
        register_tools(mock_mcp, mock_schwab_client, store)
        tool = mock_mcp._tool_manager._tools["get_expected_move_history"]
        result = tool.fn(symbol="SPX", days=30)

        assert result["symbol"] == "SPX"
        assert "snapshots" in result
        assert "accuracy" in result
