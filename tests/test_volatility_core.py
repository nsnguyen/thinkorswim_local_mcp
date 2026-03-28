"""Tests for src/core/volatility.py — IV skew, term structure, expected move.

Tests ATM/delta contract finding, skew calculation, term structure analysis,
expected move formula, and helper utilities.
"""

import math
from datetime import date

import pytest

from src.core import VolatilityCalculationError
from src.core.volatility import (
    calculate_atm_iv,
    calculate_expected_move_1sd,
    calculate_skew,
    calculate_term_structure,
    calculate_term_structure_slope,
    classify_skew_regime,
    classify_term_structure_shape,
    filter_contracts_by_expiration,
    find_atm_contracts,
    find_contract_by_delta,
    group_contracts_by_expiration,
)
from src.data.models import TermStructurePoint
from tests.fixtures.factories import (
    build_volatility_test_chain,
)

# ── find_atm_contracts ───────────────────────────────────────────


class TestFindAtmContracts:
    """Tests for ATM contract finding (closest strike to spot)."""

    def test_finds_closest_to_spot(self) -> None:
        """Test ATM at 5900 when spot=5900."""
        calls, puts = build_volatility_test_chain()
        call, put = find_atm_contracts(calls, puts, spot=5900.0)
        assert call.strike_price == 5900.0
        assert put.strike_price == 5900.0

    def test_uses_specified_expiration(self) -> None:
        """Test filtering to a specific expiration."""
        calls, puts = build_volatility_test_chain()
        exp = date(2026, 4, 10)  # 14 DTE
        call, put = find_atm_contracts(calls, puts, spot=5900.0, expiration=exp)
        assert call.expiration_date == exp
        assert put.expiration_date == exp
        assert call.strike_price == 5900.0

    def test_spot_between_strikes(self) -> None:
        """Test ATM when spot is between strikes (picks closest)."""
        calls, puts = build_volatility_test_chain()
        call, put = find_atm_contracts(calls, puts, spot=5880.0)
        # 5880 is closer to 5900 (diff=20) than 5850 (diff=30)
        assert call.strike_price == 5900.0

    def test_empty_contracts_raises(self) -> None:
        """Test empty contracts raises VolatilityCalculationError."""
        with pytest.raises(VolatilityCalculationError):
            find_atm_contracts([], [], spot=5900.0)


# ── calculate_atm_iv ─────────────────────────────────────────────


class TestCalculateAtmIv:
    """Tests for ATM IV calculation."""

    def test_averages_call_and_put_iv(self) -> None:
        """Test ATM IV = average of ATM call and put IV.

        At 7DTE, 5900 strike: call IV=15.80, put IV=15.90 → 15.85.
        """
        calls, puts = build_volatility_test_chain()
        exp = date(2026, 4, 3)  # 7 DTE
        result = calculate_atm_iv(calls, puts, spot=5900.0, expiration=exp)
        assert result == pytest.approx(15.85)

    def test_14dte_atm_iv(self) -> None:
        """Test ATM IV at 14 DTE = 16.50."""
        calls, puts = build_volatility_test_chain()
        result = calculate_atm_iv(
            calls, puts, spot=5900.0, expiration=date(2026, 4, 10)
        )
        assert result == pytest.approx(16.50)

    def test_30dte_atm_iv(self) -> None:
        """Test ATM IV at 30 DTE = 17.20."""
        calls, puts = build_volatility_test_chain()
        result = calculate_atm_iv(
            calls, puts, spot=5900.0, expiration=date(2026, 4, 26)
        )
        assert result == pytest.approx(17.20)


# ── find_contract_by_delta ───────────────────────────────────────


class TestFindContractByDelta:
    """Tests for delta-based contract matching."""

    def test_finds_25d_put(self) -> None:
        """Test finding 25-delta put at 7DTE.

        5800 put has delta=-0.25 (exact match).
        """
        _, puts = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = find_contract_by_delta(puts, target_delta=-0.25, expiration=exp)
        assert result.delta == -0.25
        assert result.strike_price == 5800.0

    def test_finds_25d_call(self) -> None:
        """Test finding 25-delta call at 30DTE.

        6000 call has delta=0.25 (exact match at 30DTE).
        """
        calls, _ = build_volatility_test_chain()
        exp = date(2026, 4, 26)
        result = find_contract_by_delta(calls, target_delta=0.25, expiration=exp)
        assert result.delta == 0.25
        assert result.strike_price == 6000.0

    def test_finds_closest_when_no_exact(self) -> None:
        """Test finding closest delta when no exact match exists.

        At 7DTE, looking for 0.10 delta call: closest is 6000 at 0.18.
        """
        calls, _ = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = find_contract_by_delta(calls, target_delta=0.10, expiration=exp)
        assert result.delta == 0.18

    def test_empty_contracts_raises(self) -> None:
        """Test empty list raises VolatilityCalculationError."""
        with pytest.raises(VolatilityCalculationError):
            find_contract_by_delta([], target_delta=0.25)

    def test_filters_by_expiration(self) -> None:
        """Test that only contracts at given expiration are searched."""
        calls, _ = build_volatility_test_chain()
        exp = date(2026, 4, 26)  # 30 DTE
        result = find_contract_by_delta(calls, target_delta=0.25, expiration=exp)
        assert result.expiration_date == exp


# ── calculate_skew ───────────────────────────────────────────────


class TestCalculateSkew:
    """Tests for IV skew calculation."""

    def test_skew_25d_formula(self) -> None:
        """Test 25d skew = put_25d_IV - call_25d_IV.

        At 7DTE: 25d put (5800, IV=17.50), 25d call (6000, IV=14.50).
        skew_25d = 17.50 - 14.50 = 3.0
        """
        calls, puts = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = calculate_skew(calls, puts, spot=5900.0, expiration=exp)
        assert result["skew_25d"] == pytest.approx(3.0)

    def test_butterfly_formula(self) -> None:
        """Test butterfly = put_25d_IV + call_25d_IV - 2*ATM_IV.

        17.50 + 14.50 - 2*15.85 = 32.00 - 31.70 = 0.30
        """
        calls, puts = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = calculate_skew(calls, puts, spot=5900.0, expiration=exp)
        assert result["butterfly"] == pytest.approx(0.30)

    def test_skew_has_all_fields(self) -> None:
        """Test that skew result contains all required fields."""
        calls, puts = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = calculate_skew(calls, puts, spot=5900.0, expiration=exp)
        assert "put_25d" in result
        assert "call_25d" in result
        assert "skew_25d" in result
        assert "skew_10d" in result
        assert "skew_40d" in result
        assert "butterfly" in result
        assert "regime" in result


# ── classify_skew_regime ─────────────────────────────────────────


class TestClassifySkewRegime:
    """Tests for skew regime classification."""

    @pytest.mark.parametrize(
        "skew_25d,atm_iv,expected",
        [
            (7.0, 15.0, "steep_skew"),   # ratio 0.467 > 0.35
            (4.0, 16.0, "normal_skew"),  # ratio 0.25
            (1.5, 16.0, "flat_skew"),    # ratio 0.094 < 0.15
            (-1.0, 16.0, "inverted"),    # negative skew
        ],
    )
    def test_regimes(
        self, skew_25d: float, atm_iv: float, expected: str
    ) -> None:
        """Test skew regime classification at various ratios."""
        assert classify_skew_regime(skew_25d, atm_iv) == expected

    def test_zero_atm_iv_returns_flat(self) -> None:
        """Test division by zero guard → flat_skew."""
        assert classify_skew_regime(3.0, 0.0) == "flat_skew"


# ── calculate_term_structure ─────────────────────────────────────


class TestCalculateTermStructure:
    """Tests for ATM IV term structure calculation."""

    def test_returns_sorted_by_dte(self) -> None:
        """Test points are sorted by DTE ascending."""
        calls, puts = build_volatility_test_chain()
        result = calculate_term_structure(calls, puts, spot=5900.0)
        dtes = [p.dte for p in result]
        assert dtes == sorted(dtes)

    def test_atm_iv_per_expiration(self) -> None:
        """Test ATM IV values match expected for each expiration."""
        calls, puts = build_volatility_test_chain()
        result = calculate_term_structure(calls, puts, spot=5900.0)
        iv_by_dte = {p.dte: p.atm_iv for p in result}
        assert iv_by_dte[7] == pytest.approx(15.85)
        assert iv_by_dte[14] == pytest.approx(16.50)
        assert iv_by_dte[30] == pytest.approx(17.20)

    def test_three_expirations(self) -> None:
        """Test that 3 expirations produce 3 points."""
        calls, puts = build_volatility_test_chain()
        result = calculate_term_structure(calls, puts, spot=5900.0)
        assert len(result) == 3

    def test_empty_chain_raises(self) -> None:
        """Test empty contracts raises VolatilityCalculationError."""
        with pytest.raises(VolatilityCalculationError):
            calculate_term_structure([], [], spot=5900.0)


# ── calculate_term_structure_slope ───────────────────────────────


class TestCalculateTermStructureSlope:
    """Tests for OLS regression slope of ATM IV vs DTE."""

    def test_contango_positive_slope(self) -> None:
        """Test contango (back > front) produces positive slope."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=15.85),
            TermStructurePoint(expiration=date(2026, 4, 10), dte=14, atm_iv=16.50),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=17.20),
        ]
        slope = calculate_term_structure_slope(points)
        assert slope > 0

    def test_backwardation_negative_slope(self) -> None:
        """Test backwardation (front > back) produces negative slope."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=20.0),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=16.0),
        ]
        slope = calculate_term_structure_slope(points)
        assert slope < 0

    def test_single_point_returns_zero(self) -> None:
        """Test that single point returns 0 slope."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=15.0),
        ]
        assert calculate_term_structure_slope(points) == 0.0

    def test_empty_returns_zero(self) -> None:
        """Test that empty list returns 0 slope."""
        assert calculate_term_structure_slope([]) == 0.0


# ── classify_term_structure_shape ────────────────────────────────


class TestClassifyTermStructureShape:
    """Tests for term structure shape classification."""

    def test_contango(self) -> None:
        """Test contango classification (positive slope, monotonic)."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=15.0),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=18.0),
        ]
        assert classify_term_structure_shape(points) == "contango"

    def test_backwardation(self) -> None:
        """Test backwardation classification (negative slope)."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=22.0),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=16.0),
        ]
        assert classify_term_structure_shape(points) == "backwardation"

    def test_flat(self) -> None:
        """Test flat classification (near-zero slope)."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=16.0),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=16.1),
        ]
        assert classify_term_structure_shape(points) == "flat"

    def test_humped(self) -> None:
        """Test humped classification (peak at interior expiration)."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=16.0),
            TermStructurePoint(expiration=date(2026, 4, 10), dte=14, atm_iv=20.0),
            TermStructurePoint(expiration=date(2026, 4, 26), dte=30, atm_iv=17.0),
        ]
        assert classify_term_structure_shape(points) == "humped"

    def test_single_point_is_flat(self) -> None:
        """Test single point returns flat."""
        points = [
            TermStructurePoint(expiration=date(2026, 4, 3), dte=7, atm_iv=15.0),
        ]
        assert classify_term_structure_shape(points) == "flat"


# ── calculate_expected_move_1sd ──────────────────────────────────


class TestCalculateExpectedMove1sd:
    """Tests for 1SD expected move formula."""

    def test_known_value(self) -> None:
        """Test EM = spot * (iv/100) * sqrt(dte/365).

        5900 * (15.85/100) * sqrt(7/365) ≈ 129.55
        """
        result = calculate_expected_move_1sd(
            spot=5900.0, atm_iv=15.85, dte=7
        )
        expected = 5900.0 * (15.85 / 100) * math.sqrt(7 / 365)
        assert result == pytest.approx(expected)

    def test_zero_dte_returns_zero(self) -> None:
        """Test that 0 DTE produces 0 expected move."""
        result = calculate_expected_move_1sd(spot=5900.0, atm_iv=15.0, dte=0)
        assert result == 0.0

    def test_higher_iv_larger_move(self) -> None:
        """Test that higher IV produces larger expected move."""
        low = calculate_expected_move_1sd(spot=5900.0, atm_iv=15.0, dte=7)
        high = calculate_expected_move_1sd(spot=5900.0, atm_iv=30.0, dte=7)
        assert high > low


# ── filter / group helpers ───────────────────────────────────────


class TestFilterContractsByExpiration:
    """Tests for expiration filtering."""

    def test_filters_correctly(self) -> None:
        """Test only matching expiration returned."""
        calls, _ = build_volatility_test_chain()
        exp = date(2026, 4, 3)
        result = filter_contracts_by_expiration(calls, exp)
        assert all(c.expiration_date == exp for c in result)
        assert len(result) == 5  # 5 strikes at this expiration

    def test_no_match_returns_empty(self) -> None:
        """Test non-existent expiration returns empty list."""
        calls, _ = build_volatility_test_chain()
        result = filter_contracts_by_expiration(calls, date(2099, 1, 1))
        assert result == []


class TestGroupContractsByExpiration:
    """Tests for expiration grouping."""

    def test_groups_correctly(self) -> None:
        """Test 3 groups from 3 expirations."""
        calls, _ = build_volatility_test_chain()
        result = group_contracts_by_expiration(calls)
        assert len(result) == 3

    def test_empty_returns_empty(self) -> None:
        """Test empty list returns empty dict."""
        result = group_contracts_by_expiration([])
        assert result == {}
