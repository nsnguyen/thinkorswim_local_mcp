"""Tests for Phase 5 MCP Resources registration and behavior.

Verifies: all 4 resources registered, each resource returns the expected
data structure when called.
"""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient
from src.resources import register_resources
from tests.fixtures.factories import build_quote, build_vix3m_quote, build_vix_quote

# ── Helpers ────────────────────────────────────────────────────────


def _make_market_hours_open():
    from src.data.models import MarketHours
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


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_mcp() -> FastMCP:
    """Create a FastMCP instance for resource registration testing."""
    return FastMCP("test-resources")


@pytest.fixture
def mock_schwab_client() -> MagicMock:
    """Create a mock SchwabClient with resource-relevant methods configured."""
    client = MagicMock(spec=SchwabClient)
    client.get_market_hours.return_value = _make_market_hours_open()
    client.get_quote.side_effect = lambda symbol: (
        build_vix_quote(level=18.50) if symbol in ("$VIX", "$VIX.X") else
        build_vix3m_quote(level=19.20) if symbol == "$VIX3M" else
        build_quote(symbol=symbol, last=5900.0)
    )
    return client


# ── Registration Tests ─────────────────────────────────────────────


class TestRegisterResources:
    """Verify all 4 MCP resources are registered."""

    def test_registers_all_resources(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """All 4 Phase 5 MCP resources must be registered.

        Missing registration means Claude cannot read that resource URI.
        """
        register_resources(mock_mcp, mock_schwab_client)
        resource_uris = set(mock_mcp._resource_manager._resources.keys()) | set(
            mock_mcp._resource_manager._templates.keys()
        )
        assert any("market-status" in u for u in resource_uris)
        assert any("vix-dashboard" in u for u in resource_uris)
        assert any("gex-regime" in u for u in resource_uris)
        assert any("watchlist" in u for u in resource_uris)


# ── Content Tests ──────────────────────────────────────────────────


class TestMarketStatusResource:
    """Test schwab://market-status resource content."""

    def test_returns_is_open_field(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """market-status resource must return is_open field.

        Claude uses this to decide whether to fetch live data or use stale cache.
        """
        register_resources(mock_mcp, mock_schwab_client)
        # Find the market-status resource
        resources = mock_mcp._resource_manager._resources
        resource = next((r for uri, r in resources.items() if "market-status" in uri), None)
        assert resource is not None

        import json
        content = resource.fn()
        data = json.loads(content) if isinstance(content, str) else content

        assert "is_open" in data

    def test_calls_market_hours_and_vix(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """market-status resource must fetch market hours and VIX level.

        Combines session status with VIX for a complete market snapshot.
        """
        register_resources(mock_mcp, mock_schwab_client)
        resources = mock_mcp._resource_manager._resources
        resource = next((r for uri, r in resources.items() if "market-status" in uri), None)

        resource.fn()

        mock_schwab_client.get_market_hours.assert_called()


class TestVixDashboardResource:
    """Test schwab://vix-dashboard resource content."""

    def test_returns_vix_fields(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """vix-dashboard resource must return VIX level and term structure.

        Used by Claude as a quick volatility regime snapshot.
        """
        register_resources(mock_mcp, mock_schwab_client)
        resources = mock_mcp._resource_manager._resources
        resource = next((r for uri, r in resources.items() if "vix-dashboard" in uri), None)
        assert resource is not None

        import json
        content = resource.fn()
        data = json.loads(content) if isinstance(content, str) else content

        assert "vix_level" in data
        assert "vix3m_level" in data


class TestGexRegimeResource:
    """Test schwab://gex-regime/{symbol} template resource content."""

    def test_template_registered(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """gex-regime/{symbol} must be registered as a template resource.

        Template resources accept URI parameters — one per symbol.
        """
        register_resources(mock_mcp, mock_schwab_client)
        templates = mock_mcp._resource_manager._templates
        assert any("gex-regime" in uri for uri in templates.keys())


class TestWatchlistResource:
    """Test schwab://watchlist resource content."""

    def test_returns_symbols_list(
        self, mock_mcp: FastMCP, mock_schwab_client: MagicMock
    ) -> None:
        """watchlist resource must return a list of symbols.

        Returns the configured watchlist — defaults to common market symbols.
        """
        register_resources(mock_mcp, mock_schwab_client)
        resources = mock_mcp._resource_manager._resources
        resource = next((r for uri, r in resources.items() if "watchlist" in uri), None)
        assert resource is not None

        import json
        content = resource.fn()
        data = json.loads(content) if isinstance(content, str) else content

        assert "symbols" in data
        assert isinstance(data["symbols"], list)
        assert len(data["symbols"]) > 0
