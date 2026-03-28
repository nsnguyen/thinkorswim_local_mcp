"""Tests for src/core/gex_calculator.py — GEX computation engine.

Tests the atomic GEX formula, per-strike aggregation, aggregate metrics
(DEX, VEX, theta), DTE filtering, and charm/vanna projections.
"""

import pytest

from src.core import GexCalculationError
from src.core.gex_calculator import (
    calculate_aggregate_gex,
    calculate_dex,
    calculate_per_strike_gex,
    calculate_strike_gex,
    calculate_vex,
    filter_contracts_by_dte,
    project_charm_adjusted_gex,
    project_vanna_adjusted_gex,
)
from tests.fixtures.factories import build_gex_test_chain, build_option_contract

# ── calculate_strike_gex ─────────────────────────────────────────


class TestCalculateStrikeGex:
    """Tests for the atomic GEX formula."""

    def test_call_gex_is_positive(self) -> None:
        """Test that call GEX is positive (calls have +1 sign).

        GEX = +1 * abs(0.0068) * 12000 * 100 * 5900^2 * 0.01
        """
        result = calculate_strike_gex(
            gamma=0.0068, open_interest=12000, spot=5900.0, is_call=True
        )
        assert result > 0

    def test_put_gex_is_negative(self) -> None:
        """Test that put GEX is negative (puts have -1 sign)."""
        result = calculate_strike_gex(
            gamma=0.0068, open_interest=12000, spot=5900.0, is_call=False
        )
        assert result < 0

    def test_known_value(self) -> None:
        """Test GEX formula against a hand-calculated value.

        GEX = sign * abs(gamma) * OI * 100 * spot^2 * 0.01
            = +1 * 0.0068 * 12000 * 100 * 5900^2 * 0.01
            = 0.0068 * 12000 * 100 * 34810000 * 0.01
            = 0.0068 * 12000 * 100 * 348100.0
            = 28,396,560.0
        """
        result = calculate_strike_gex(
            gamma=0.0068, open_interest=12000, spot=5900.0, is_call=True
        )
        expected = 0.0068 * 12000 * 100 * 5900.0**2 * 0.01
        assert result == pytest.approx(expected)

    def test_call_and_put_magnitude_equal(self) -> None:
        """Test that call and put GEX have equal magnitude but opposite signs."""
        call_gex = calculate_strike_gex(gamma=0.005, open_interest=1000, spot=5000.0, is_call=True)
        put_gex = calculate_strike_gex(gamma=0.005, open_interest=1000, spot=5000.0, is_call=False)
        assert call_gex == pytest.approx(-put_gex)

    def test_zero_open_interest_produces_zero_gex(self) -> None:
        """Test that zero OI produces zero GEX regardless of gamma."""
        result = calculate_strike_gex(gamma=0.01, open_interest=0, spot=5900.0, is_call=True)
        assert result == 0.0

    def test_zero_gamma_produces_zero_gex(self) -> None:
        """Test that zero gamma produces zero GEX regardless of OI."""
        result = calculate_strike_gex(gamma=0.0, open_interest=50000, spot=5900.0, is_call=True)
        assert result == 0.0

    @pytest.mark.parametrize(
        "spot,expected_ratio",
        [
            (5900.0, 1.0),
            (11800.0, 4.0),  # double spot → 4x GEX (spot^2)
        ],
    )
    def test_gex_scales_with_spot_squared(self, spot: float, expected_ratio: float) -> None:
        """Test that GEX scales with spot^2."""
        base = calculate_strike_gex(gamma=0.005, open_interest=1000, spot=5900.0, is_call=True)
        scaled = calculate_strike_gex(gamma=0.005, open_interest=1000, spot=spot, is_call=True)
        assert scaled / base == pytest.approx(expected_ratio)


# ── calculate_per_strike_gex ─────────────────────────────────────


class TestCalculatePerStrikeGex:
    """Tests for per-strike GEX aggregation."""

    def test_returns_sorted_by_strike(self) -> None:
        """Test that results are sorted by strike price ascending."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        strikes = [sg.strike for sg in result]
        assert strikes == sorted(strikes)

    def test_net_gex_equals_call_plus_put(self) -> None:
        """Test that net_gex = call_gex + put_gex for each strike."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        for sg in result:
            assert sg.net_gex == pytest.approx(sg.call_gex + sg.put_gex)

    def test_call_gex_positive_put_gex_negative(self) -> None:
        """Test sign convention: call_gex > 0, put_gex < 0."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        for sg in result:
            assert sg.call_gex > 0
            assert sg.put_gex < 0

    def test_oi_matches_input_contracts(self) -> None:
        """Test that call_oi and put_oi match the input contract OI."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        # 5900 strike: call_oi=12000, put_oi=10000
        strike_5900 = next(sg for sg in result if sg.strike == 5900.0)
        assert strike_5900.call_oi == 12000
        assert strike_5900.put_oi == 10000

    def test_volume_aggregation(self) -> None:
        """Test that total_volume = call_volume + put_volume."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        strike_5900 = next(sg for sg in result if sg.strike == 5900.0)
        assert strike_5900.total_volume == 5200 + 4500

    def test_five_strikes_from_test_chain(self) -> None:
        """Test that build_gex_test_chain produces 5 strikes."""
        calls, puts = build_gex_test_chain()
        result = calculate_per_strike_gex(calls, puts, spot=5900.0)
        assert len(result) == 5

    def test_max_dte_filter(self) -> None:
        """Test that max_dte filters out contracts with higher DTE."""
        call_7dte = build_option_contract(strike_price=5900.0, days_to_expiration=7, gamma=0.005)
        call_30dte = build_option_contract(strike_price=5900.0, days_to_expiration=30, gamma=0.003)
        put_7dte = build_option_contract(
            option_type="PUT", strike_price=5900.0, days_to_expiration=7, gamma=0.005
        )
        result = calculate_per_strike_gex(
            [call_7dte, call_30dte], [put_7dte], spot=5900.0, max_dte=7
        )
        # Only the 7DTE call should contribute, not the 30DTE
        assert len(result) == 1
        # With max_dte=7, only 1 call (7dte) contributes to call_gex
        sg = result[0]
        expected_call_gex = calculate_strike_gex(
            gamma=0.005, open_interest=12000, spot=5900.0, is_call=True
        )
        assert sg.call_gex == pytest.approx(expected_call_gex)

    def test_empty_contracts_raises(self) -> None:
        """Test that empty contracts raises GexCalculationError."""
        with pytest.raises(GexCalculationError):
            calculate_per_strike_gex([], [], spot=5900.0)

    def test_aggregates_multiple_expirations_same_strike(self) -> None:
        """Test that contracts at the same strike but different expirations are summed."""
        call_7 = build_option_contract(
            strike_price=5900.0, days_to_expiration=7, gamma=0.005, open_interest=1000
        )
        call_14 = build_option_contract(
            strike_price=5900.0, days_to_expiration=14, gamma=0.003, open_interest=2000
        )
        put_7 = build_option_contract(
            option_type="PUT", strike_price=5900.0, days_to_expiration=7,
            gamma=0.005, open_interest=1500,
        )
        result = calculate_per_strike_gex([call_7, call_14], [put_7], spot=5900.0)
        assert len(result) == 1
        sg = result[0]
        expected_call = (
            calculate_strike_gex(0.005, 1000, 5900.0, True)
            + calculate_strike_gex(0.003, 2000, 5900.0, True)
        )
        assert sg.call_gex == pytest.approx(expected_call)
        assert sg.call_oi == 3000  # 1000 + 2000


# ── calculate_dex / calculate_vex ────────────────────────────────


class TestDexVex:
    """Tests for DEX and VEX formulas."""

    def test_dex_call_positive(self) -> None:
        """Test that call DEX is positive (call delta > 0)."""
        result = calculate_dex(delta=0.50, open_interest=12000, spot=5900.0)
        assert result > 0

    def test_dex_put_negative(self) -> None:
        """Test that put DEX is negative (put delta < 0, already signed)."""
        result = calculate_dex(delta=-0.50, open_interest=12000, spot=5900.0)
        assert result < 0

    def test_dex_known_value(self) -> None:
        """Test DEX = delta * OI * 100 * spot."""
        result = calculate_dex(delta=0.50, open_interest=12000, spot=5900.0)
        expected = 0.50 * 12000 * 100 * 5900.0
        assert result == pytest.approx(expected)

    def test_vex_call_positive(self) -> None:
        """Test that call VEX is positive."""
        result = calculate_vex(vega=5.80, open_interest=12000, is_call=True)
        assert result > 0

    def test_vex_put_negative(self) -> None:
        """Test that put VEX is negative (puts sign = -1)."""
        result = calculate_vex(vega=5.80, open_interest=12000, is_call=False)
        assert result < 0

    def test_vex_known_value(self) -> None:
        """Test VEX = sign * vega * OI * 100."""
        result = calculate_vex(vega=5.80, open_interest=12000, is_call=True)
        expected = 1 * 5.80 * 12000 * 100
        assert result == pytest.approx(expected)


# ── calculate_aggregate_gex ──────────────────────────────────────


class TestCalculateAggregateGex:
    """Tests for aggregate GEX metrics."""

    def test_returns_gex_summary_model(self) -> None:
        """Test that result is a GexSummary with all required fields."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        assert result.symbol == "SPX"
        assert result.total_gex != 0
        assert result.contracts_analyzed == 10  # 5 calls + 5 puts

    def test_total_gex_is_call_plus_put(self) -> None:
        """Test that total_gex = call_gex + put_gex."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        assert result.total_gex == pytest.approx(result.call_gex + result.put_gex)

    def test_gross_gex_is_absolute_sum(self) -> None:
        """Test that gross_gex = abs(call_gex) + abs(put_gex)."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        assert result.gross_gex == pytest.approx(abs(result.call_gex) + abs(result.put_gex))

    def test_call_gex_positive_put_gex_negative(self) -> None:
        """Test sign convention in aggregate: call > 0, put < 0."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        assert result.call_gex > 0
        assert result.put_gex < 0

    def test_gex_ratio_is_call_over_put(self) -> None:
        """Test that gex_ratio = abs(call_gex / put_gex)."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        expected = abs(result.call_gex / result.put_gex)
        assert result.gex_ratio == pytest.approx(expected)

    def test_aggregate_theta_is_negative(self) -> None:
        """Test that aggregate theta is negative (time decay)."""
        calls, puts = build_gex_test_chain()
        result = calculate_aggregate_gex(calls, puts, spot=5900.0)
        assert result.aggregate_theta < 0


# ── filter_contracts_by_dte ──────────────────────────────────────


class TestFilterContractsByDte:
    """Tests for DTE filtering utility."""

    def test_max_dte_filter(self) -> None:
        """Test filtering contracts by max DTE."""
        contracts = [
            build_option_contract(days_to_expiration=0),
            build_option_contract(days_to_expiration=7),
            build_option_contract(days_to_expiration=30),
        ]
        result = filter_contracts_by_dte(contracts, max_dte=7)
        assert len(result) == 2
        assert all(c.days_to_expiration <= 7 for c in result)

    def test_min_dte_filter(self) -> None:
        """Test filtering contracts by min DTE."""
        contracts = [
            build_option_contract(days_to_expiration=0),
            build_option_contract(days_to_expiration=7),
            build_option_contract(days_to_expiration=30),
        ]
        result = filter_contracts_by_dte(contracts, min_dte=7)
        assert len(result) == 2
        assert all(c.days_to_expiration >= 7 for c in result)

    def test_no_filter_returns_all(self) -> None:
        """Test that no filter returns all contracts."""
        contracts = [
            build_option_contract(days_to_expiration=0),
            build_option_contract(days_to_expiration=365),
        ]
        result = filter_contracts_by_dte(contracts)
        assert len(result) == 2

    def test_zero_dte_only(self) -> None:
        """Test filtering for exactly 0DTE contracts."""
        contracts = [
            build_option_contract(days_to_expiration=0),
            build_option_contract(days_to_expiration=1),
        ]
        result = filter_contracts_by_dte(contracts, max_dte=0, min_dte=0)
        assert len(result) == 1
        assert result[0].days_to_expiration == 0


# ── project_charm_adjusted_gex ───────────────────────────────────


class TestProjectCharmAdjustedGex:
    """Tests for charm-adjusted GEX projections."""

    def test_returns_strike_gex_list(self) -> None:
        """Test that charm projection returns list of StrikeGex."""
        calls, puts = build_gex_test_chain()
        result = project_charm_adjusted_gex(calls, puts, spot=5900.0, hours_forward=3.0)
        assert len(result) > 0
        assert result[0].strike == 5800.0  # sorted ascending

    def test_charm_changes_gex_values(self) -> None:
        """Test that charm projection produces different GEX than current.

        With theta != 0, the projected GEX should differ from current.
        """
        calls, puts = build_gex_test_chain()
        current = calculate_per_strike_gex(calls, puts, spot=5900.0)
        projected = project_charm_adjusted_gex(calls, puts, spot=5900.0, hours_forward=3.0)
        # At least one strike should have different net_gex
        current_gex = {sg.strike: sg.net_gex for sg in current}
        projected_gex = {sg.strike: sg.net_gex for sg in projected}
        differences = [
            abs(current_gex[s] - projected_gex[s]) for s in current_gex
        ]
        assert any(d > 0 for d in differences)

    def test_zero_hours_returns_same_as_current(self) -> None:
        """Test that 0 hours forward produces identical GEX to current."""
        calls, puts = build_gex_test_chain()
        current = calculate_per_strike_gex(calls, puts, spot=5900.0)
        projected = project_charm_adjusted_gex(calls, puts, spot=5900.0, hours_forward=0.0)
        for c, p in zip(current, projected):
            assert c.net_gex == pytest.approx(p.net_gex)


# ── project_vanna_adjusted_gex ───────────────────────────────────


class TestProjectVannaAdjustedGex:
    """Tests for vanna-adjusted GEX projections."""

    def test_returns_strike_gex_list(self) -> None:
        """Test that vanna projection returns list of StrikeGex."""
        calls, puts = build_gex_test_chain()
        result = project_vanna_adjusted_gex(calls, puts, spot=5900.0, iv_change_pct=2.0)
        assert len(result) > 0

    def test_vanna_changes_gex_values(self) -> None:
        """Test that IV change produces different GEX than current."""
        calls, puts = build_gex_test_chain()
        current = calculate_per_strike_gex(calls, puts, spot=5900.0)
        projected = project_vanna_adjusted_gex(calls, puts, spot=5900.0, iv_change_pct=2.0)
        current_gex = {sg.strike: sg.net_gex for sg in current}
        projected_gex = {sg.strike: sg.net_gex for sg in projected}
        differences = [abs(current_gex[s] - projected_gex[s]) for s in current_gex]
        assert any(d > 0 for d in differences)

    def test_zero_iv_change_returns_same_as_current(self) -> None:
        """Test that 0% IV change produces identical GEX to current."""
        calls, puts = build_gex_test_chain()
        current = calculate_per_strike_gex(calls, puts, spot=5900.0)
        projected = project_vanna_adjusted_gex(calls, puts, spot=5900.0, iv_change_pct=0.0)
        for c, p in zip(current, projected):
            assert c.net_gex == pytest.approx(p.net_gex)
