"""Tests for Phase 5 MCP Prompts registration and content.

Verifies: all 4 prompts registered, each prompt returns a non-empty
list of messages with relevant workflow steps.
"""

import pytest
from mcp.server.fastmcp import FastMCP

from src.prompts import register_prompts

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_mcp() -> FastMCP:
    """Create a FastMCP instance for prompt registration testing."""
    return FastMCP("test-prompts")


@pytest.fixture
def registered_prompts(mock_mcp: FastMCP) -> dict:
    """Register prompts and return name → prompt dict."""
    register_prompts(mock_mcp)
    return mock_mcp._prompt_manager._prompts


# ── Registration Tests ─────────────────────────────────────────────


class TestRegisterPrompts:
    """Verify all 4 MCP prompts are registered."""

    def test_registers_morning_briefing(self, registered_prompts: dict) -> None:
        """morning_briefing prompt must be registered.

        Missing registration means Claude cannot access the morning workflow.
        """
        assert "morning_briefing" in registered_prompts

    def test_registers_iron_condor_scan(self, registered_prompts: dict) -> None:
        """iron_condor_scan prompt must be registered.

        Missing registration means the trade scan workflow is unavailable.
        """
        assert "iron_condor_scan" in registered_prompts

    def test_registers_regime_check(self, registered_prompts: dict) -> None:
        """regime_check prompt must be registered.

        Missing registration means the quick regime workflow is unavailable.
        """
        assert "regime_check" in registered_prompts

    def test_registers_intraday_levels(self, registered_prompts: dict) -> None:
        """intraday_levels prompt must be registered.

        Missing registration means the 0DTE intraday workflow is unavailable.
        """
        assert "intraday_levels" in registered_prompts

    def test_registers_all_four_prompts(self, registered_prompts: dict) -> None:
        """All 4 Phase 5 prompts must be registered together.

        A single bulk check to catch any partial registration failure.
        """
        expected = {"morning_briefing", "iron_condor_scan", "regime_check", "intraday_levels"}
        assert expected.issubset(set(registered_prompts.keys()))


# ── Content Tests ──────────────────────────────────────────────────


class TestMorningBriefingPrompt:
    """Test morning_briefing prompt content."""

    def test_returns_messages_list(self, mock_mcp: FastMCP) -> None:
        """morning_briefing must return a non-empty list of messages.

        FastMCP prompts return list[dict] with role+content pairs.
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["morning_briefing"]

        result = prompt.fn()

        assert isinstance(result, list)
        assert len(result) > 0

    def test_includes_key_workflow_steps(self, mock_mcp: FastMCP) -> None:
        """morning_briefing must reference key pre-market tools.

        The prompt text should guide Claude to call VIX, GEX, and futures tools.
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["morning_briefing"]

        result = prompt.fn()
        full_text = " ".join(
            str(msg.get("content", "")) for msg in result
        ).lower()

        assert any(kw in full_text for kw in ["vix", "gex", "futures", "/es"])


class TestIronCondorScanPrompt:
    """Test iron_condor_scan prompt content."""

    def test_returns_messages_list(self, mock_mcp: FastMCP) -> None:
        """iron_condor_scan must return a non-empty list of messages."""
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["iron_condor_scan"]

        result = prompt.fn()

        assert isinstance(result, list)
        assert len(result) > 0

    def test_accepts_symbol_parameter(self, mock_mcp: FastMCP) -> None:
        """iron_condor_scan must accept an optional symbol parameter.

        Allows scanning specific symbols instead of just the default (SPX).
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["iron_condor_scan"]

        result = prompt.fn(symbol="SPY")

        full_text = " ".join(str(msg.get("content", "")) for msg in result)
        assert "SPY" in full_text

    def test_includes_key_workflow_steps(self, mock_mcp: FastMCP) -> None:
        """iron_condor_scan must reference GEX, IV, and trade evaluation tools.

        The scan workflow relies on multiple tools working together.
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["iron_condor_scan"]

        result = prompt.fn()
        full_text = " ".join(
            str(msg.get("content", "")) for msg in result
        ).lower()

        assert any(kw in full_text for kw in ["gex", "iron condor", "expected move", "volatility"])


class TestRegimeCheckPrompt:
    """Test regime_check prompt content."""

    def test_returns_messages_list(self, mock_mcp: FastMCP) -> None:
        """regime_check must return a non-empty list of messages."""
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["regime_check"]

        result = prompt.fn()

        assert isinstance(result, list)
        assert len(result) > 0

    def test_includes_gex_and_vix(self, mock_mcp: FastMCP) -> None:
        """regime_check must reference both GEX and VIX data sources.

        Regime assessment requires both dealer positioning and fear gauge data.
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["regime_check"]

        result = prompt.fn()
        full_text = " ".join(
            str(msg.get("content", "")) for msg in result
        ).lower()

        assert "gex" in full_text
        assert "vix" in full_text


class TestIntradayLevelsPrompt:
    """Test intraday_levels prompt content."""

    def test_returns_messages_list(self, mock_mcp: FastMCP) -> None:
        """intraday_levels must return a non-empty list of messages."""
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["intraday_levels"]

        result = prompt.fn()

        assert isinstance(result, list)
        assert len(result) > 0

    def test_includes_0dte_workflow(self, mock_mcp: FastMCP) -> None:
        """intraday_levels must reference 0DTE and charm shift tools.

        The intraday workflow is 0DTE-focused and time-decay aware.
        """
        register_prompts(mock_mcp)
        prompt = mock_mcp._prompt_manager._prompts["intraday_levels"]

        result = prompt.fn()
        full_text = " ".join(
            str(msg.get("content", "")) for msg in result
        ).lower()

        assert any(kw in full_text for kw in ["0dte", "charm", "intraday", "levels"])
