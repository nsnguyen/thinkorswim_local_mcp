"""Tests for src/core/gex_levels.py — GEX level extraction.

Tests key level identification (walls, zero gamma, max gamma, HVL),
top-10 strike ranking, regime classification, and 0DTE level extraction.
"""

import pytest

from src.core import GexCalculationError
from src.core.gex_levels import (
    classify_gex_regime,
    extract_key_levels,
    extract_top_gex_strikes,
    extract_zero_dte_levels,
    find_call_wall,
    find_hvl,
    find_max_gamma,
    find_put_wall,
    find_zero_gamma,
)
from src.data.models import KeyLevel
from tests.fixtures.factories import build_option_contract, build_strike_gex

# ── Helpers ──────────────────────────────────────────────────────


def _make_strike_gex_list() -> list:
    """Create a realistic 5-strike GEX list for testing level extraction.

    Strike layout (spot = 5900):
      5800: high put_oi (put wall candidate), positive net_gex
      5850: moderate, positive net_gex
      5900: highest call_oi (call wall), highest volume (HVL), highest abs(net_gex) (max gamma)
      5950: moderate, negative net_gex (cumulative crosses zero here)
      6000: low activity, negative net_gex
    """
    return [
        build_strike_gex(strike=5800.0, call_gex=500_000, put_gex=-200_000, net_gex=300_000,
                         call_oi=5000, put_oi=15000, total_volume=3000),
        build_strike_gex(strike=5850.0, call_gex=800_000, put_gex=-600_000, net_gex=200_000,
                         call_oi=8500, put_oi=6200, total_volume=4000),
        build_strike_gex(strike=5900.0, call_gex=1_500_000, put_gex=-700_000, net_gex=800_000,
                         call_oi=20000, put_oi=10000, total_volume=12000),
        build_strike_gex(strike=5950.0, call_gex=400_000, put_gex=-1_200_000, net_gex=-800_000,
                         call_oi=9500, put_oi=12000, total_volume=8000),
        build_strike_gex(strike=6000.0, call_gex=200_000, put_gex=-900_000, net_gex=-700_000,
                         call_oi=4000, put_oi=7000, total_volume=2000),
    ]


# ── find_call_wall ───────────────────────────────────────────────


class TestFindCallWall:
    """Tests for call wall detection (max call OI)."""

    def test_finds_strike_with_max_call_oi(self) -> None:
        """Test that call wall is the strike with highest call open interest."""
        strikes = _make_strike_gex_list()
        result = find_call_wall(strikes)
        assert result.price == 5900.0  # call_oi=20000

    def test_returns_key_level_with_correct_fields(self) -> None:
        """Test that call wall returns a KeyLevel with all fields populated."""
        strikes = _make_strike_gex_list()
        result = find_call_wall(strikes)
        assert isinstance(result, KeyLevel)
        assert result.call_oi == 20000
        assert result.gex == 1_500_000  # call_gex at that strike

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            find_call_wall([])


# ── find_put_wall ────────────────────────────────────────────────


class TestFindPutWall:
    """Tests for put wall detection (max put OI)."""

    def test_finds_strike_with_max_put_oi(self) -> None:
        """Test that put wall is the strike with highest put open interest."""
        strikes = _make_strike_gex_list()
        result = find_put_wall(strikes)
        assert result.price == 5800.0  # put_oi=15000

    def test_returns_key_level(self) -> None:
        """Test that put wall returns a KeyLevel."""
        strikes = _make_strike_gex_list()
        result = find_put_wall(strikes)
        assert isinstance(result, KeyLevel)
        assert result.put_oi == 15000

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            find_put_wall([])


# ── find_zero_gamma ──────────────────────────────────────────────


class TestFindZeroGamma:
    """Tests for zero gamma (gamma flip) level detection."""

    def test_finds_interpolated_zero_crossing(self) -> None:
        """Test linear interpolation where cumulative net GEX crosses zero.

        Cumulative GEX walking ascending:
          5800: +300,000 (cumulative: +300,000)
          5850: +200,000 (cumulative: +500,000)
          5900: +800,000 (cumulative: +1,300,000)
          5950: -800,000 (cumulative: +500,000)
          6000: -700,000 (cumulative: -200,000)

        Zero crossing between 5950 (+500,000) and 6000 (-200,000).
        Interpolation: 5950 + 50 * (500000 / (500000 + 200000)) = 5950 + 35.71 = 5985.71
        """
        strikes = _make_strike_gex_list()
        result = find_zero_gamma(strikes)
        assert 5950.0 < result.price < 6000.0

    def test_all_positive_returns_last_strike(self) -> None:
        """Test no zero crossing returns strike with min abs cumulative."""
        strikes = [
            build_strike_gex(strike=5800.0, net_gex=100_000),
            build_strike_gex(strike=5900.0, net_gex=200_000),
            build_strike_gex(strike=6000.0, net_gex=50_000),
        ]
        result = find_zero_gamma(strikes)
        # All cumulative positive; min abs cumulative is at 5800 (100,000)
        assert isinstance(result, KeyLevel)

    def test_returns_key_level(self) -> None:
        """Test return type is KeyLevel."""
        strikes = _make_strike_gex_list()
        result = find_zero_gamma(strikes)
        assert isinstance(result, KeyLevel)

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            find_zero_gamma([])

    def test_single_strike(self) -> None:
        """Test with single strike — returns that strike as zero gamma."""
        strikes = [build_strike_gex(strike=5900.0, net_gex=100_000)]
        result = find_zero_gamma(strikes)
        assert result.price == 5900.0


# ── find_max_gamma ───────────────────────────────────────────────


class TestFindMaxGamma:
    """Tests for max gamma detection (highest abs net_gex)."""

    def test_finds_strike_with_max_abs_net_gex(self) -> None:
        """Test that max gamma is the strike with highest absolute net GEX.

        5900 and 5950 both have abs(net_gex) = 800,000. First one wins.
        """
        strikes = _make_strike_gex_list()
        result = find_max_gamma(strikes)
        assert result.price in (5900.0, 5950.0)

    def test_returns_key_level(self) -> None:
        """Test return type is KeyLevel."""
        strikes = _make_strike_gex_list()
        result = find_max_gamma(strikes)
        assert isinstance(result, KeyLevel)

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            find_max_gamma([])


# ── find_hvl ─────────────────────────────────────────────────────


class TestFindHvl:
    """Tests for HVL detection (highest total volume)."""

    def test_finds_strike_with_max_volume(self) -> None:
        """Test that HVL is the strike with highest total volume."""
        strikes = _make_strike_gex_list()
        result = find_hvl(strikes)
        assert result.price == 5900.0  # total_volume=12000

    def test_returns_key_level(self) -> None:
        """Test return type is KeyLevel."""
        strikes = _make_strike_gex_list()
        result = find_hvl(strikes)
        assert isinstance(result, KeyLevel)

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            find_hvl([])


# ── extract_key_levels ───────────────────────────────────────────


class TestExtractKeyLevels:
    """Tests for the extract_key_levels orchestrator."""

    def test_returns_all_five_levels(self) -> None:
        """Test that all 5 key levels are present in the result."""
        strikes = _make_strike_gex_list()
        result = extract_key_levels(strikes, spot=5900.0)
        assert set(result.keys()) == {"call_wall", "put_wall", "zero_gamma", "max_gamma", "hvl"}

    def test_all_values_are_key_levels(self) -> None:
        """Test that all values in the result are KeyLevel instances."""
        strikes = _make_strike_gex_list()
        result = extract_key_levels(strikes, spot=5900.0)
        for level in result.values():
            assert isinstance(level, KeyLevel)

    def test_empty_list_raises(self) -> None:
        """Test that empty input raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            extract_key_levels([], spot=5900.0)


# ── extract_top_gex_strikes ─────────────────────────────────────


class TestExtractTopGexStrikes:
    """Tests for top GEX strike ranking."""

    def test_returns_sorted_by_abs_net_gex_descending(self) -> None:
        """Test that top strikes are ranked by abs(net_gex) descending."""
        strikes = _make_strike_gex_list()
        result = extract_top_gex_strikes(strikes, count=5)
        gex_values = [abs(s.net_gex) for s in result]
        assert gex_values == sorted(gex_values, reverse=True)

    def test_ranks_start_at_one(self) -> None:
        """Test that ranking starts at 1."""
        strikes = _make_strike_gex_list()
        result = extract_top_gex_strikes(strikes, count=3)
        assert result[0].rank == 1
        assert result[1].rank == 2
        assert result[2].rank == 3

    def test_count_limits_results(self) -> None:
        """Test that count parameter limits number of results."""
        strikes = _make_strike_gex_list()
        result = extract_top_gex_strikes(strikes, count=3)
        assert len(result) == 3

    def test_count_exceeds_available_strikes(self) -> None:
        """Test that requesting more than available returns all strikes."""
        strikes = _make_strike_gex_list()
        result = extract_top_gex_strikes(strikes, count=10)
        assert len(result) == 5  # only 5 strikes available

    def test_empty_list_returns_empty(self) -> None:
        """Test that empty input returns empty list."""
        result = extract_top_gex_strikes([], count=10)
        assert result == []


# ── classify_gex_regime ──────────────────────────────────────────


class TestClassifyGexRegime:
    """Tests for GEX regime classification."""

    @pytest.mark.parametrize(
        "spot,zero_gamma,expected_type",
        [
            (5900.0, 5800.0, "positive"),  # spot above zero gamma
            (5700.0, 5800.0, "negative"),  # spot below zero gamma
            (5800.0, 5800.0, "positive"),  # spot exactly at zero gamma → positive
        ],
    )
    def test_regime_classification(
        self, spot: float, zero_gamma: float, expected_type: str
    ) -> None:
        """Test regime type based on spot vs zero gamma position."""
        result = classify_gex_regime(spot, zero_gamma)
        assert result.type == expected_type

    def test_spot_vs_zero_gamma_distance(self) -> None:
        """Test that spot_vs_zero_gamma is the signed distance."""
        result = classify_gex_regime(spot=5900.0, zero_gamma=5850.0)
        assert result.spot_vs_zero_gamma == pytest.approx(50.0)
        assert result.zero_gamma == 5850.0


# ── extract_zero_dte_levels ──────────────────────────────────────


class TestExtractZeroDteLevels:
    """Tests for 0DTE level extraction."""

    def test_returns_none_when_no_zero_dte(self) -> None:
        """Test that None is returned when no 0DTE contracts exist."""
        calls = [build_option_contract(days_to_expiration=7)]
        puts = [build_option_contract(option_type="PUT", days_to_expiration=7)]
        result = extract_zero_dte_levels(calls, puts, spot=5900.0)
        assert result is None

    def test_returns_levels_for_zero_dte_contracts(self) -> None:
        """Test that ZeroDteLevels is returned when 0DTE contracts exist."""
        calls = [
            build_option_contract(
                strike_price=5850.0, days_to_expiration=0,
                gamma=0.005, open_interest=5000,
            ),
            build_option_contract(
                strike_price=5900.0, days_to_expiration=0,
                gamma=0.008, open_interest=10000,
            ),
        ]
        puts = [
            build_option_contract(
                option_type="PUT", strike_price=5850.0,
                days_to_expiration=0, gamma=0.005, open_interest=8000,
            ),
            build_option_contract(
                option_type="PUT", strike_price=5900.0,
                days_to_expiration=0, gamma=0.008, open_interest=6000,
            ),
        ]
        result = extract_zero_dte_levels(calls, puts, spot=5900.0)
        assert result is not None
        assert isinstance(result.call_wall, KeyLevel)
        assert isinstance(result.put_wall, KeyLevel)
        assert isinstance(result.zero_gamma, KeyLevel)
        assert isinstance(result.max_gamma, KeyLevel)

    def test_ignores_non_zero_dte_contracts(self) -> None:
        """Test that non-0DTE contracts are excluded from 0DTE levels."""
        calls = [
            build_option_contract(
                strike_price=5900.0, days_to_expiration=0,
                gamma=0.008, open_interest=10000,
            ),
            build_option_contract(
                strike_price=5900.0, days_to_expiration=7,
                gamma=0.005, open_interest=50000,
            ),
        ]
        puts = [
            build_option_contract(
                option_type="PUT", strike_price=5900.0,
                days_to_expiration=0, gamma=0.008, open_interest=8000,
            ),
        ]
        result = extract_zero_dte_levels(calls, puts, spot=5900.0)
        assert result is not None
        # call_oi should only reflect 0DTE (10000), not 7DTE (50000)
        assert result.call_wall.call_oi == 10000
