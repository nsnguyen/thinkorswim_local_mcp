"""GEX level extraction — walls, zero gamma, max gamma, HVL, regime classification.

All functions are pure computation (no I/O, no side effects).

Key GEX Levels
==============
These are the price levels where dealer hedging creates notable effects:

  Call Wall:  Strike with highest call OI. Acts as resistance — dealers
              are long gamma here, so they sell into rallies toward this level.

  Put Wall:   Strike with highest put OI. Acts as support — dealers hedge
              by buying dips near this level.

  Zero Gamma: The "gamma flip" level where cumulative net GEX crosses zero.
              Above this: positive gamma (mean-reverting, stable).
              Below this: negative gamma (trending, volatile).
              This is the single most important level for intraday trading.

  Max Gamma:  Strike with highest absolute net GEX. Price tends to be
              "pinned" near this level due to intense dealer hedging.

  HVL:        High Volume Level — strike with most total volume (calls + puts).
              Indicates where the most trading activity is concentrated today.

Regime Classification
=====================
  Positive regime (spot >= zero_gamma): Dealers are net long gamma.
    They buy dips and sell rips → dampens moves → range-bound / mean-reverting.

  Negative regime (spot < zero_gamma): Dealers are net short gamma.
    They sell into dips and buy into rips → amplifies moves → trending / volatile.
"""

from src.core import GexCalculationError
from src.core.gex_calculator import calculate_per_strike_gex, filter_contracts_by_dte
from src.data.models import (
    GexRegime,
    KeyLevel,
    OptionContract,
    StrikeGex,
    TopGexStrike,
    ZeroDteLevels,
)


def extract_key_levels(
    strike_gex: list[StrikeGex],
    spot: float,
) -> dict[str, KeyLevel]:
    """Extract all 5 key GEX levels from per-strike data."""
    if not strike_gex:
        raise GexCalculationError("No strike GEX data for level extraction")

    return {
        "call_wall": find_call_wall(strike_gex),
        "put_wall": find_put_wall(strike_gex),
        "zero_gamma": find_zero_gamma(strike_gex),
        "max_gamma": find_max_gamma(strike_gex),
        "hvl": find_hvl(strike_gex),
    }


def find_call_wall(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the strike with highest call open interest (call wall / resistance)."""
    if not strike_gex:
        raise GexCalculationError("No strike data for call wall")
    best = max(strike_gex, key=lambda sg: sg.call_oi)
    return KeyLevel(price=best.strike, gex=best.call_gex, call_oi=best.call_oi, put_oi=best.put_oi)


def find_put_wall(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the strike with highest put open interest (put wall / support)."""
    if not strike_gex:
        raise GexCalculationError("No strike data for put wall")
    best = max(strike_gex, key=lambda sg: sg.put_oi)
    return KeyLevel(price=best.strike, gex=best.put_gex, call_oi=best.call_oi, put_oi=best.put_oi)


def find_zero_gamma(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the gamma flip level where cumulative net GEX crosses zero.

    Walks strikes ascending, accumulates net_gex. When the sign flips,
    linearly interpolates the exact crossing point. If no crossing,
    returns the strike with minimum absolute cumulative GEX.
    """
    if not strike_gex:
        raise GexCalculationError("No strike data for zero gamma")

    if len(strike_gex) == 1:
        sg = strike_gex[0]
        return KeyLevel(price=sg.strike, gex=sg.net_gex, call_oi=sg.call_oi, put_oi=sg.put_oi)

    # Walk strikes ascending, accumulating net GEX at each step.
    # Where cumulative GEX flips sign = the gamma flip / zero gamma level.
    #
    # Example with 3 strikes:
    #   5850: net_gex = +500K  → cumulative = +500K
    #   5900: net_gex = +300K  → cumulative = +800K
    #   5950: net_gex = -1.2M  → cumulative = -400K  ← sign flip!
    #
    # The zero crossing is between 5900 (+800K) and 5950 (-400K).
    # We linearly interpolate: 5900 + 50 * (800K / (800K + 400K)) = 5933.33
    cumulative = []
    running = 0.0
    for sg in strike_gex:
        running += sg.net_gex
        cumulative.append(running)

    # Look for sign change (product of adjacent values < 0 = opposite signs)
    for i in range(len(cumulative) - 1):
        if cumulative[i] * cumulative[i + 1] < 0:
            # Linear interpolation: weight by distance to zero
            s1 = strike_gex[i].strike
            s2 = strike_gex[i + 1].strike
            c1 = abs(cumulative[i])
            c2 = abs(cumulative[i + 1])
            zero_price = s1 + (s2 - s1) * (c1 / (c1 + c2))

            # Interpolate OI from the two surrounding strikes
            sg1 = strike_gex[i]
            sg2 = strike_gex[i + 1]
            return KeyLevel(
                price=round(zero_price, 2),
                gex=0.0,
                call_oi=sg1.call_oi + sg2.call_oi,
                put_oi=sg1.put_oi + sg2.put_oi,
            )

    # No crossing — return strike with minimum absolute cumulative
    min_idx = min(range(len(cumulative)), key=lambda i: abs(cumulative[i]))
    sg = strike_gex[min_idx]
    return KeyLevel(price=sg.strike, gex=sg.net_gex, call_oi=sg.call_oi, put_oi=sg.put_oi)


def find_max_gamma(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the strike with highest absolute net GEX (max gamma)."""
    if not strike_gex:
        raise GexCalculationError("No strike data for max gamma")
    best = max(strike_gex, key=lambda sg: abs(sg.net_gex))
    return KeyLevel(price=best.strike, gex=best.net_gex, call_oi=best.call_oi, put_oi=best.put_oi)


def find_hvl(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the strike with highest total volume (High Volume Level)."""
    if not strike_gex:
        raise GexCalculationError("No strike data for HVL")
    best = max(strike_gex, key=lambda sg: sg.total_volume)
    return KeyLevel(price=best.strike, gex=best.net_gex, call_oi=best.call_oi, put_oi=best.put_oi)


def extract_top_gex_strikes(
    strike_gex: list[StrikeGex],
    count: int = 10,
) -> list[TopGexStrike]:
    """Extract top N strikes ranked by absolute net GEX."""
    sorted_strikes = sorted(strike_gex, key=lambda sg: abs(sg.net_gex), reverse=True)
    return [
        TopGexStrike(
            rank=i + 1,
            strike=sg.strike,
            net_gex=sg.net_gex,
            call_oi=sg.call_oi,
            put_oi=sg.put_oi,
        )
        for i, sg in enumerate(sorted_strikes[:count])
    ]


def classify_gex_regime(spot: float, zero_gamma: float) -> GexRegime:
    """Classify GEX regime based on spot price vs zero gamma level.

    Positive (spot >= zero_gamma): dealers long gamma → mean-reverting
    Negative (spot < zero_gamma):  dealers short gamma → trending
    """
    regime_type = "positive" if spot >= zero_gamma else "negative"
    return GexRegime(
        type=regime_type,
        zero_gamma=zero_gamma,
        spot_vs_zero_gamma=spot - zero_gamma,
    )


def extract_zero_dte_levels(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
) -> ZeroDteLevels | None:
    """Extract key levels from 0DTE contracts only.

    Returns None if no 0DTE contracts exist.
    """
    zero_calls = filter_contracts_by_dte(calls, max_dte=0, min_dte=0)
    zero_puts = filter_contracts_by_dte(puts, max_dte=0, min_dte=0)

    if not zero_calls and not zero_puts:
        return None

    per_strike = calculate_per_strike_gex(zero_calls, zero_puts, spot)
    return ZeroDteLevels(
        call_wall=find_call_wall(per_strike),
        put_wall=find_put_wall(per_strike),
        zero_gamma=find_zero_gamma(per_strike),
        max_gamma=find_max_gamma(per_strike),
    )
