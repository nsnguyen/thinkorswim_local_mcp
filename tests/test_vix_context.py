"""Tests for src/core/vix_context.py — VIX regime and term structure.

Tests VIX regime classification, VIX/VIX3M term structure ratio,
and the build_vix_context orchestrator.
"""

import pytest

from src.core.vix_context import (
    build_vix_context,
    calculate_vix_term_structure,
    classify_vix_regime,
)
from tests.fixtures.factories import build_vix3m_quote, build_vix_quote

# ── classify_vix_regime ──────────────────────────────────────────


class TestClassifyVixRegime:
    """Tests for VIX regime classification from absolute level."""

    @pytest.mark.parametrize(
        "level,expected",
        [
            (10.0, "low"),
            (11.99, "low"),
            (12.0, "normal"),
            (15.0, "normal"),
            (19.99, "normal"),
            (20.0, "elevated"),
            (25.0, "elevated"),
            (29.99, "elevated"),
            (30.0, "high"),
            (45.0, "high"),
        ],
    )
    def test_regime_thresholds(self, level: float, expected: str) -> None:
        """Test VIX regime at exact boundary values."""
        assert classify_vix_regime(level) == expected


# ── calculate_vix_term_structure ─────────────────────────────────


class TestCalculateVixTermStructure:
    """Tests for VIX/VIX3M term structure."""

    def test_contango(self) -> None:
        """Test contango: VIX < VIX3M (ratio < 0.95, normal market)."""
        ratio, shape = calculate_vix_term_structure(17.0, 20.0)
        assert shape == "contango"
        assert ratio == pytest.approx(0.85)

    def test_backwardation(self) -> None:
        """Test backwardation: VIX > VIX3M (ratio > 1.05, fear/stress)."""
        ratio, shape = calculate_vix_term_structure(25.0, 20.0)
        assert shape == "backwardation"
        assert ratio == pytest.approx(1.25)

    def test_flat(self) -> None:
        """Test flat: VIX ≈ VIX3M (ratio 0.95-1.05)."""
        ratio, shape = calculate_vix_term_structure(19.0, 19.5)
        assert shape == "flat"
        assert 0.95 <= ratio <= 1.05

    def test_known_ratio(self) -> None:
        """Test ratio calculation: 18.5 / 19.2 ≈ 0.9635."""
        ratio, _ = calculate_vix_term_structure(18.5, 19.2)
        assert ratio == pytest.approx(0.9635, abs=0.0001)

    def test_zero_vix3m_returns_backwardation(self) -> None:
        """Test division-by-zero guard when VIX3M is 0."""
        ratio, shape = calculate_vix_term_structure(18.0, 0.0)
        assert shape == "backwardation"
        assert ratio == 999.99


# ── build_vix_context ────────────────────────────────────────────


class TestBuildVixContext:
    """Tests for the build_vix_context orchestrator."""

    def test_returns_correct_structure(self) -> None:
        """Test all fields present in result."""
        vix_q = build_vix_quote(level=18.50, change=-0.80)
        vix3m_q = build_vix3m_quote(level=19.20)
        result = build_vix_context(vix_q, vix3m_q)
        assert "vix" in result
        assert "vix3m" in result
        assert "term_structure" in result

    def test_vix_level_from_quote(self) -> None:
        """Test VIX level extracted from quote's last price."""
        vix_q = build_vix_quote(level=22.50)
        vix3m_q = build_vix3m_quote(level=20.00)
        result = build_vix_context(vix_q, vix3m_q)
        assert result["vix"]["level"] == 22.50

    def test_vix_change_from_quote(self) -> None:
        """Test VIX change extracted from net_change."""
        vix_q = build_vix_quote(level=18.50, change=-0.80)
        vix3m_q = build_vix3m_quote()
        result = build_vix_context(vix_q, vix3m_q)
        assert result["vix"]["change"] == -0.80

    def test_percentile_is_none(self) -> None:
        """Test VIX percentile is None (Phase 3A)."""
        vix_q = build_vix_quote()
        vix3m_q = build_vix3m_quote()
        result = build_vix_context(vix_q, vix3m_q)
        assert result["vix"]["percentile"] is None

    def test_regime_matches_level(self) -> None:
        """Test regime is consistent with VIX level."""
        vix_q = build_vix_quote(level=18.50)
        vix3m_q = build_vix3m_quote()
        result = build_vix_context(vix_q, vix3m_q)
        assert result["vix"]["regime"] == "normal"

    def test_term_structure_from_quotes(self) -> None:
        """Test ratio and shape derived from VIX/VIX3M quotes.

        VIX=18.50 / VIX3M=19.20 = 0.9635, which is between 0.95-1.05 → flat.
        """
        vix_q = build_vix_quote(level=18.50)
        vix3m_q = build_vix3m_quote(level=19.20)
        result = build_vix_context(vix_q, vix3m_q)
        assert result["term_structure"]["ratio"] == pytest.approx(
            0.9635, abs=0.0001
        )
        assert result["term_structure"]["shape"] == "flat"
