"""Tests for src/core/iv_context.py — IV context and regime classification.

History-dependent functions return None in Phase 3A.
classify_iv_regime and build_iv_context are fully functional.
"""

import pytest

from src.core.iv_context import (
    build_iv_context,
    calculate_iv_percentile,
    calculate_iv_rank,
    calculate_iv_rv_premium,
    calculate_realized_volatility,
    classify_iv_regime,
)

# ── classify_iv_regime ───────────────────────────────────────────


class TestClassifyIvRegime:
    """Tests for IV regime classification from absolute ATM IV level."""

    @pytest.mark.parametrize(
        "atm_iv,expected",
        [
            (10.0, "low"),
            (14.99, "low"),
            (15.0, "normal"),
            (20.0, "normal"),
            (24.99, "normal"),
            (25.0, "elevated"),
            (30.0, "elevated"),
            (34.99, "elevated"),
            (35.0, "high"),
            (50.0, "high"),
        ],
    )
    def test_regime_thresholds(self, atm_iv: float, expected: str) -> None:
        """Test IV regime classification at exact boundary values."""
        assert classify_iv_regime(atm_iv) == expected


# ── calculate_iv_percentile ──────────────────────────────────────


class TestCalculateIvPercentile:
    """Tests for IV percentile calculation."""

    def test_returns_none_when_no_history(self) -> None:
        """Test that None history returns None (Phase 3A)."""
        assert calculate_iv_percentile(15.0, None) is None

    def test_returns_none_when_empty_history(self) -> None:
        """Test that empty history returns None."""
        assert calculate_iv_percentile(15.0, []) is None

    def test_known_percentile(self) -> None:
        """Test percentile with known history (Phase 3B prep)."""
        history = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        result = calculate_iv_percentile(15.0, history)
        assert result is not None
        assert 0 <= result <= 100


# ── calculate_iv_rank ────────────────────────────────────────────


class TestCalculateIvRank:
    """Tests for IV rank: (current - min) / (max - min)."""

    def test_returns_none_when_no_history(self) -> None:
        """Test that None history returns None (Phase 3A)."""
        assert calculate_iv_rank(15.0, None) is None

    def test_returns_none_when_empty_history(self) -> None:
        """Test that empty history returns None."""
        assert calculate_iv_rank(15.0, []) is None

    def test_known_rank(self) -> None:
        """Test rank with known history (Phase 3B prep).

        history min=10, max=20, current=15 → rank = (15-10)/(20-10) = 0.5
        """
        history = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        result = calculate_iv_rank(15.0, history)
        assert result == pytest.approx(50.0)

    def test_rank_at_min(self) -> None:
        """Test rank when current equals min → 0."""
        result = calculate_iv_rank(10.0, [10.0, 15.0, 20.0])
        assert result == pytest.approx(0.0)

    def test_rank_at_max(self) -> None:
        """Test rank when current equals max → 100."""
        result = calculate_iv_rank(20.0, [10.0, 15.0, 20.0])
        assert result == pytest.approx(100.0)

    def test_flat_history(self) -> None:
        """Test rank when min == max → returns 0."""
        result = calculate_iv_rank(15.0, [15.0, 15.0, 15.0])
        assert result == pytest.approx(0.0)


# ── calculate_realized_volatility ────────────────────────────────


class TestCalculateRealizedVolatility:
    """Tests for realized volatility calculation."""

    def test_returns_none_when_no_data(self) -> None:
        """Test that None input returns None (Phase 3A)."""
        assert calculate_realized_volatility(None) is None

    def test_returns_none_when_insufficient_data(self) -> None:
        """Test that fewer than window+1 data points returns None."""
        assert calculate_realized_volatility([100.0, 101.0], window=20) is None

    def test_known_value(self) -> None:
        """Test RV with known daily closes (Phase 3B prep)."""
        # 21 close prices (enough for 20-day window)
        closes = [100.0 + i * 0.5 for i in range(21)]
        result = calculate_realized_volatility(closes, window=20)
        assert result is not None
        assert result > 0


# ── calculate_iv_rv_premium ──────────────────────────────────────


class TestCalculateIvRvPremium:
    """Tests for IV minus RV premium."""

    def test_returns_none_when_rv_none(self) -> None:
        """Test that None RV returns None (Phase 3A)."""
        assert calculate_iv_rv_premium(15.0, None) is None

    def test_known_premium(self) -> None:
        """Test premium = IV - RV."""
        result = calculate_iv_rv_premium(18.0, 12.0)
        assert result == pytest.approx(6.0)


# ── build_iv_context ─────────────────────────────────────────────


class TestBuildIvContext:
    """Tests for the build_iv_context orchestrator."""

    def test_all_none_without_history(self) -> None:
        """Test Phase 3A default: all history fields are None."""
        result = build_iv_context(atm_iv=15.85)
        assert result["percentile"] is None
        assert result["rank"] is None
        assert result["rv_20d"] is None
        assert result["iv_rv_premium"] is None

    def test_regime_from_atm_iv(self) -> None:
        """Test that regime is derived from atm_iv."""
        result = build_iv_context(atm_iv=15.85)
        assert result["regime"] == "normal"

    def test_low_regime(self) -> None:
        """Test low regime for IV < 15."""
        result = build_iv_context(atm_iv=12.0)
        assert result["regime"] == "low"

    def test_elevated_regime(self) -> None:
        """Test elevated regime for IV 25-35."""
        result = build_iv_context(atm_iv=28.0)
        assert result["regime"] == "elevated"
