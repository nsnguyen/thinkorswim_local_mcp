"""Tests for trade_math core — strategy detection, P&L, POP, breakevens, net greeks.

All math is pure computation with no I/O. Tests verify formulas against known values.
"""

from datetime import date

import pytest

from src.core import TradeMathError
from src.core.trade_math import (
    calculate_breakevens,
    calculate_d2,
    calculate_max_profit_loss,
    calculate_net_credit,
    calculate_net_greeks,
    calculate_pop,
    detect_strategy,
)

# ── Helper to build leg dicts ──────────────────────────────────────


def _leg(
    strike: float,
    option_type: str,
    action: str,
    expiration: date = date(2026, 4, 17),
    bid: float = 2.00,
    ask: float = 2.20,
    delta: float = 0.30,
    gamma: float = 0.02,
    theta: float = -0.05,
    vega: float = 0.15,
    iv: float = 0.20,
) -> dict:
    """Build a leg dict with pricing and greeks."""
    return {
        "strike": strike,
        "option_type": option_type,
        "action": action,
        "expiration": expiration,
        "quantity": 1,
        "bid": bid,
        "ask": ask,
        "mark": (bid + ask) / 2,
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "iv": iv,
    }


# ── Strategy Detection ─────────────────────────────────────────────


class TestDetectStrategy:
    """Test auto-detection of strategy type from legs."""

    def test_long_call(self) -> None:
        """Single long call → 'long_call'.

        Simplest strategy — must identify correctly.
        """
        legs = [_leg(5900, "CALL", "BUY")]
        assert detect_strategy(legs) == "long_call"

    def test_short_call(self) -> None:
        """Single short call → 'short_call'."""
        legs = [_leg(5900, "CALL", "SELL")]
        assert detect_strategy(legs) == "short_call"

    def test_long_put(self) -> None:
        """Single long put → 'long_put'."""
        legs = [_leg(5900, "PUT", "BUY")]
        assert detect_strategy(legs) == "long_put"

    def test_short_put(self) -> None:
        """Single short put → 'short_put'."""
        legs = [_leg(5900, "PUT", "SELL")]
        assert detect_strategy(legs) == "short_put"

    def test_call_vertical_bull(self) -> None:
        """Long lower + short higher call → 'bull_call_spread'."""
        legs = [
            _leg(5800, "CALL", "BUY"),
            _leg(5900, "CALL", "SELL"),
        ]
        assert detect_strategy(legs) == "bull_call_spread"

    def test_call_vertical_bear(self) -> None:
        """Short lower + long higher call → 'bear_call_spread'."""
        legs = [
            _leg(5800, "CALL", "SELL"),
            _leg(5900, "CALL", "BUY"),
        ]
        assert detect_strategy(legs) == "bear_call_spread"

    def test_put_vertical_bull(self) -> None:
        """Short higher + long lower put → 'bull_put_spread'."""
        legs = [
            _leg(5800, "PUT", "BUY"),
            _leg(5900, "PUT", "SELL"),
        ]
        assert detect_strategy(legs) == "bull_put_spread"

    def test_put_vertical_bear(self) -> None:
        """Long higher + short lower put → 'bear_put_spread'."""
        legs = [
            _leg(5800, "PUT", "SELL"),
            _leg(5900, "PUT", "BUY"),
        ]
        assert detect_strategy(legs) == "bear_put_spread"

    def test_iron_condor(self) -> None:
        """4 legs: put spread + call spread → 'iron_condor'.

        Most common multi-leg premium-selling strategy.
        """
        legs = [
            _leg(5700, "PUT", "BUY"),
            _leg(5800, "PUT", "SELL"),
            _leg(5900, "CALL", "SELL"),
            _leg(6000, "CALL", "BUY"),
        ]
        assert detect_strategy(legs) == "iron_condor"

    def test_short_straddle(self) -> None:
        """Short call + short put, same strike → 'short_straddle'."""
        legs = [
            _leg(5900, "CALL", "SELL"),
            _leg(5900, "PUT", "SELL"),
        ]
        assert detect_strategy(legs) == "short_straddle"

    def test_long_straddle(self) -> None:
        """Long call + long put, same strike → 'long_straddle'."""
        legs = [
            _leg(5900, "CALL", "BUY"),
            _leg(5900, "PUT", "BUY"),
        ]
        assert detect_strategy(legs) == "long_straddle"

    def test_short_strangle(self) -> None:
        """Short call + short put, different strikes → 'short_strangle'."""
        legs = [
            _leg(5800, "PUT", "SELL"),
            _leg(6000, "CALL", "SELL"),
        ]
        assert detect_strategy(legs) == "short_strangle"

    def test_long_strangle(self) -> None:
        """Long call + long put, different strikes → 'long_strangle'."""
        legs = [
            _leg(5800, "PUT", "BUY"),
            _leg(6000, "CALL", "BUY"),
        ]
        assert detect_strategy(legs) == "long_strangle"

    def test_calendar_spread(self) -> None:
        """Same strike, different expirations → 'calendar_spread'."""
        legs = [
            _leg(5900, "CALL", "SELL", expiration=date(2026, 4, 17)),
            _leg(5900, "CALL", "BUY", expiration=date(2026, 5, 15)),
        ]
        assert detect_strategy(legs) == "calendar_spread"

    def test_empty_legs_raises(self) -> None:
        """No legs → error."""
        with pytest.raises(TradeMathError):
            detect_strategy([])

    def test_unknown_strategy(self) -> None:
        """Unrecognizable combo → 'custom'."""
        legs = [
            _leg(5700, "CALL", "BUY"),
            _leg(5800, "PUT", "BUY"),
            _leg(5900, "CALL", "SELL"),
        ]
        assert detect_strategy(legs) == "custom"


# ── Net Credit/Debit ───────────────────────────────────────────────


class TestCalculateNetCredit:
    """Test net credit/debit calculation."""

    def test_credit_spread(self) -> None:
        """Selling higher premium, buying lower → positive credit.

        Net credit is the bread and butter of premium selling.
        """
        legs = [
            _leg(5800, "PUT", "SELL", bid=8.00, ask=8.40),   # sell at bid = 8.00
            _leg(5700, "PUT", "BUY", bid=3.00, ask=3.20),    # buy at ask = 3.20
        ]
        credit = calculate_net_credit(legs)
        assert credit == pytest.approx(4.80)

    def test_debit_spread(self) -> None:
        """Buying higher premium, selling lower → negative (debit)."""
        legs = [
            _leg(5800, "CALL", "BUY", bid=8.00, ask=8.40),   # buy at ask = 8.40
            _leg(5900, "CALL", "SELL", bid=3.00, ask=3.20),   # sell at bid = 3.00
        ]
        credit = calculate_net_credit(legs)
        assert credit == pytest.approx(-5.40)

    def test_iron_condor_credit(self) -> None:
        """Iron condor: two credit spreads → net credit."""
        legs = [
            _leg(5700, "PUT", "BUY", bid=1.50, ask=1.70),
            _leg(5800, "PUT", "SELL", bid=4.00, ask=4.20),
            _leg(5900, "CALL", "SELL", bid=4.00, ask=4.20),
            _leg(6000, "CALL", "BUY", bid=1.50, ask=1.70),
        ]
        credit = calculate_net_credit(legs)
        # sell 4.00 + 4.00 = 8.00, buy 1.70 + 1.70 = 3.40 → net credit 4.60
        assert credit == pytest.approx(4.60)


# ── Max Profit / Max Loss ──────────────────────────────────────────


class TestCalculateMaxProfitLoss:
    """Test max profit and max loss for various strategies."""

    def test_vertical_spread_credit(self) -> None:
        """Bull put spread: max_profit = credit, max_loss = width - credit.

        This is the fundamental P&L for credit spreads.
        """
        result = calculate_max_profit_loss(
            strategy="bull_put_spread",
            net_credit=4.80,
            legs=[
                _leg(5700, "PUT", "BUY"),
                _leg(5800, "PUT", "SELL"),
            ],
        )
        assert result["max_profit"] == pytest.approx(4.80 * 100)
        assert result["max_loss"] == pytest.approx((100 - 4.80) * 100)

    def test_vertical_spread_debit(self) -> None:
        """Bull call spread: max_profit = width - debit, max_loss = debit."""
        result = calculate_max_profit_loss(
            strategy="bull_call_spread",
            net_credit=-5.40,
            legs=[
                _leg(5800, "CALL", "BUY"),
                _leg(5900, "CALL", "SELL"),
            ],
        )
        assert result["max_profit"] == pytest.approx((100 - 5.40) * 100)
        assert result["max_loss"] == pytest.approx(5.40 * 100)

    def test_iron_condor(self) -> None:
        """Iron condor: max_profit = credit, max_loss = wider_width - credit."""
        result = calculate_max_profit_loss(
            strategy="iron_condor",
            net_credit=4.60,
            legs=[
                _leg(5700, "PUT", "BUY"),
                _leg(5800, "PUT", "SELL"),
                _leg(5900, "CALL", "SELL"),
                _leg(6000, "CALL", "BUY"),
            ],
        )
        assert result["max_profit"] == pytest.approx(4.60 * 100)
        assert result["max_loss"] == pytest.approx((100 - 4.60) * 100)

    def test_short_put(self) -> None:
        """Short put: max_profit = credit, max_loss = (strike - credit) * 100."""
        result = calculate_max_profit_loss(
            strategy="short_put",
            net_credit=8.00,
            legs=[_leg(5800, "PUT", "SELL", bid=8.00, ask=8.20)],
        )
        assert result["max_profit"] == pytest.approx(8.00 * 100)
        assert result["max_loss"] == pytest.approx((5800 - 8.00) * 100)

    def test_long_call(self) -> None:
        """Long call: max_profit = unlimited, max_loss = debit."""
        result = calculate_max_profit_loss(
            strategy="long_call",
            net_credit=-8.40,
            legs=[_leg(5800, "CALL", "BUY", bid=8.00, ask=8.40)],
        )
        assert result["max_profit"] == float("inf")
        assert result["max_loss"] == pytest.approx(8.40 * 100)

    def test_short_straddle(self) -> None:
        """Short straddle: max_profit = total credit, max_loss = unlimited."""
        result = calculate_max_profit_loss(
            strategy="short_straddle",
            net_credit=16.00,
            legs=[
                _leg(5900, "CALL", "SELL", bid=8.00, ask=8.20),
                _leg(5900, "PUT", "SELL", bid=8.00, ask=8.20),
            ],
        )
        assert result["max_profit"] == pytest.approx(16.00 * 100)
        assert result["max_loss"] == float("inf")


# ── Breakevens ─────────────────────────────────────────────────────


class TestCalculateBreakevens:
    """Test breakeven calculation for various strategies."""

    def test_bull_put_spread(self) -> None:
        """Bull put spread breakeven = short_strike - credit."""
        breakevens = calculate_breakevens(
            strategy="bull_put_spread",
            net_credit=4.80,
            legs=[
                _leg(5700, "PUT", "BUY"),
                _leg(5800, "PUT", "SELL"),
            ],
        )
        assert breakevens == [pytest.approx(5795.20)]

    def test_bull_call_spread(self) -> None:
        """Bull call spread breakeven = long_strike + debit."""
        breakevens = calculate_breakevens(
            strategy="bull_call_spread",
            net_credit=-5.40,
            legs=[
                _leg(5800, "CALL", "BUY"),
                _leg(5900, "CALL", "SELL"),
            ],
        )
        assert breakevens == [pytest.approx(5805.40)]

    def test_iron_condor_two_breakevens(self) -> None:
        """Iron condor has two breakevens: lower and upper."""
        breakevens = calculate_breakevens(
            strategy="iron_condor",
            net_credit=4.60,
            legs=[
                _leg(5700, "PUT", "BUY"),
                _leg(5800, "PUT", "SELL"),
                _leg(5900, "CALL", "SELL"),
                _leg(6000, "CALL", "BUY"),
            ],
        )
        assert len(breakevens) == 2
        assert breakevens[0] == pytest.approx(5795.40)   # put_short - credit
        assert breakevens[1] == pytest.approx(5904.60)    # call_short + credit

    def test_short_straddle_two_breakevens(self) -> None:
        """Short straddle breakevens = strike ± credit."""
        breakevens = calculate_breakevens(
            strategy="short_straddle",
            net_credit=16.00,
            legs=[
                _leg(5900, "CALL", "SELL"),
                _leg(5900, "PUT", "SELL"),
            ],
        )
        assert len(breakevens) == 2
        assert breakevens[0] == pytest.approx(5884.00)
        assert breakevens[1] == pytest.approx(5916.00)

    def test_short_put(self) -> None:
        """Short put breakeven = strike - credit."""
        breakevens = calculate_breakevens(
            strategy="short_put",
            net_credit=8.00,
            legs=[_leg(5800, "PUT", "SELL")],
        )
        assert breakevens == [pytest.approx(5792.00)]

    def test_long_call(self) -> None:
        """Long call breakeven = strike + debit."""
        breakevens = calculate_breakevens(
            strategy="long_call",
            net_credit=-8.40,
            legs=[_leg(5800, "CALL", "BUY")],
        )
        assert breakevens == [pytest.approx(5808.40)]


# ── POP (Black-Scholes) ───────────────────────────────────────────


class TestCalculateD2:
    """Test the d2 component of Black-Scholes."""

    def test_known_d2(self) -> None:
        """Verify d2 formula against hand-calculated value.

        d2 = (ln(S/K) + (r - σ²/2) × T) / (σ × √T)
        S=5900, K=5800, σ=0.20, T=21/365, r=0.05
        """
        d2 = calculate_d2(
            spot=5900.0, breakeven=5800.0, iv=0.20, dte_years=21 / 365, r=0.05,
        )
        # ln(5900/5800) = 0.01712
        # (0.05 - 0.02) * 0.05753 = 0.001726
        # σ√T = 0.20 * 0.23987 = 0.04797
        # d2 = (0.01712 + 0.001726) / 0.04797 = 0.3930
        assert d2 == pytest.approx(0.393, abs=0.01)

    def test_atm_d2(self) -> None:
        """ATM (S=K): d2 should be near zero (slightly negative due to σ²/2)."""
        d2 = calculate_d2(spot=5900.0, breakeven=5900.0, iv=0.20, dte_years=30 / 365, r=0.0)
        assert abs(d2) < 0.1


class TestCalculatePop:
    """Test probability of profit calculation."""

    def test_short_put_pop(self) -> None:
        """Short put with breakeven well below spot should have high POP.

        POP = N(d2) where d2 is computed from spot vs breakeven.
        """
        pop = calculate_pop(
            spot=5900.0,
            breakevens=[5795.0],
            iv=0.20,
            dte_years=21 / 365,
            strategy="short_put",
        )
        assert 0.60 < pop < 0.95  # should be reasonably high

    def test_iron_condor_pop(self) -> None:
        """Iron condor POP = N(d2_upper) - N(d2_lower).

        Both breakevens far from spot → high POP.
        """
        pop = calculate_pop(
            spot=5900.0,
            breakevens=[5795.0, 5905.0],
            iv=0.20,
            dte_years=21 / 365,
            strategy="iron_condor",
        )
        assert 0.01 < pop < 0.99

    def test_long_call_pop(self) -> None:
        """Long call breakeven above spot → lower POP."""
        pop = calculate_pop(
            spot=5900.0,
            breakevens=[5950.0],
            iv=0.20,
            dte_years=21 / 365,
            strategy="long_call",
        )
        assert 0.10 < pop < 0.60

    def test_pop_bounds(self) -> None:
        """POP must always be between 0 and 1."""
        pop = calculate_pop(
            spot=5900.0,
            breakevens=[100.0],  # extreme breakeven
            iv=0.20,
            dte_years=30 / 365,
            strategy="short_put",
        )
        assert 0.0 <= pop <= 1.0


# ── Net Greeks ─────────────────────────────────────────────────────


class TestCalculateNetGreeks:
    """Test net greek aggregation across legs."""

    def test_single_long_leg(self) -> None:
        """Long leg: greeks contribute positively.

        Net greeks are how Claude gauges directional risk.
        """
        legs = [_leg(5900, "CALL", "BUY", delta=0.50, gamma=0.02, theta=-0.10, vega=0.30)]
        greeks = calculate_net_greeks(legs)
        assert greeks["net_delta"] == pytest.approx(0.50)
        assert greeks["net_gamma"] == pytest.approx(0.02)
        assert greeks["net_theta"] == pytest.approx(-0.10)
        assert greeks["net_vega"] == pytest.approx(0.30)

    def test_single_short_leg(self) -> None:
        """Short leg: greeks flip sign."""
        legs = [_leg(5900, "CALL", "SELL", delta=0.50, gamma=0.02, theta=-0.10, vega=0.30)]
        greeks = calculate_net_greeks(legs)
        assert greeks["net_delta"] == pytest.approx(-0.50)
        assert greeks["net_theta"] == pytest.approx(0.10)
        assert greeks["net_vega"] == pytest.approx(-0.30)

    def test_iron_condor_greeks(self) -> None:
        """Iron condor: near-zero delta, positive theta, negative vega."""
        legs = [
            _leg(5700, "PUT", "BUY", delta=-0.10, gamma=0.01, theta=-0.03, vega=0.08),
            _leg(5800, "PUT", "SELL", delta=-0.25, gamma=0.02, theta=-0.06, vega=0.15),
            _leg(5900, "CALL", "SELL", delta=0.25, gamma=0.02, theta=-0.06, vega=0.15),
            _leg(6000, "CALL", "BUY", delta=0.10, gamma=0.01, theta=-0.03, vega=0.08),
        ]
        greeks = calculate_net_greeks(legs)
        # Long: +(-0.10) + +(0.10) = 0; Short: -(-0.25) + -(0.25) = 0
        assert abs(greeks["net_delta"]) < 0.01
        # Theta: sell legs have neg theta that flips positive
        assert greeks["net_theta"] > 0

    def test_quantity_multiplier(self) -> None:
        """Quantity > 1 should multiply greeks."""
        legs = [_leg(5900, "CALL", "BUY", delta=0.50, gamma=0.02, theta=-0.10, vega=0.30)]
        legs[0]["quantity"] = 3
        greeks = calculate_net_greeks(legs)
        assert greeks["net_delta"] == pytest.approx(1.50)
        assert greeks["net_vega"] == pytest.approx(0.90)
