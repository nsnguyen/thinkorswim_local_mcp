"""GEX computation engine — per-strike formula, aggregation, DEX/VEX, projections.

All functions are pure computation (no I/O, no side effects).

GEX (Gamma Exposure) Formula
=============================
GEX = sign * |gamma| * OI * 100 * spot^2 * 0.01

  - gamma:  option's gamma (rate of change of delta per $1 move)
  - OI:     open interest (number of contracts outstanding)
  - 100:    contract multiplier (each option = 100 shares)
  - spot^2: converts per-share gamma to dollar gamma (gamma * spot = delta
            change per $1; multiply by spot again = dollar impact)
  - 0.01:   scaling factor (gamma is per $1 move; 0.01 = per 1% move)
  - sign:   +1 for calls, -1 for puts (dealers are short puts, long calls
            from retail flow — so call gamma pushes dealers to buy dips /
            sell rips (stabilizing), put gamma does the opposite)

Why it matters: GEX estimates how much delta-hedging market makers must do.
  - Positive GEX (calls dominate) → dealers hedge against the move →
    mean-reverting, range-bound, "sticky" price action
  - Negative GEX (puts dominate) → dealers hedge with the move →
    trending, volatile, moves accelerate

DEX (Delta Exposure): delta * OI * 100 * spot
  Measures net directional exposure. Delta is already signed by Schwab
  (negative for puts), so no extra sign multiplier needed.

VEX (Vega Exposure): sign * vega * OI * 100
  Measures sensitivity to IV changes. Vega is always positive from
  Schwab, so we apply the call/put sign convention.

Charm & Vanna Projections
=========================
These estimate how GEX shifts over time or with IV changes:

  - Charm (time decay of delta): approximated as -theta / spot
    As time passes, gamma decays → GEX levels shift.
    new_gamma = gamma + charm * (hours / 24)

  - Vanna (IV sensitivity of delta): approximated as vega / spot
    When IV rises/falls, gamma changes → GEX levels shift.
    new_gamma = gamma + vanna * iv_change_pct
"""

from collections import defaultdict
from datetime import UTC, datetime

from src.core import GexCalculationError
from src.data.models import GexSummary, OptionContract, StrikeGex


def calculate_strike_gex(
    gamma: float,
    open_interest: int,
    spot: float,
    is_call: bool,
) -> float:
    """Calculate GEX for a single strike/side.

    Formula: sign * |gamma| * OI * 100 * spot^2 * 0.01

    Example (SPX 5900 call, gamma=0.0068, OI=12,000):
      +1 * 0.0068 * 12000 * 100 * 5900^2 * 0.01 = ~28.4M
      This means market makers must buy/sell ~$28.4M of SPX
      for every 1% move to stay delta-neutral at this strike.
    """
    sign = 1 if is_call else -1
    return sign * abs(gamma) * open_interest * 100 * spot**2 * 0.01


def calculate_per_strike_gex(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    max_dte: int | None = None,
) -> list[StrikeGex]:
    """Calculate per-strike GEX across all contracts, grouped by strike.

    For each strike price, sums call GEX (+) and put GEX (-) across all
    expirations. The net_gex at each strike tells you whether dealers are
    net long or short gamma there — positive = stabilizing, negative = amplifying.

    The resulting list (sorted by strike) is used to find key levels:
    call wall, put wall, zero gamma, max gamma, and HVL.
    """
    if not calls and not puts:
        raise GexCalculationError("No contracts provided for GEX calculation")

    if max_dte is not None:
        filtered_calls = filter_contracts_by_dte(calls, max_dte=max_dte)
        filtered_puts = filter_contracts_by_dte(puts, max_dte=max_dte)
    else:
        filtered_calls = calls
        filtered_puts = puts

    if not filtered_calls and not filtered_puts:
        raise GexCalculationError(f"No contracts remaining after DTE filter (max_dte={max_dte})")

    strike_data: dict[float, dict] = defaultdict(
        lambda: {
            "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0, "put_oi": 0,
            "call_vol": 0, "put_vol": 0,
        }
    )

    for c in filtered_calls:
        d = strike_data[c.strike_price]
        d["call_gex"] += calculate_strike_gex(c.gamma, c.open_interest, spot, is_call=True)
        d["call_oi"] += c.open_interest
        d["call_vol"] += c.volume

    for p in filtered_puts:
        d = strike_data[p.strike_price]
        d["put_gex"] += calculate_strike_gex(p.gamma, p.open_interest, spot, is_call=False)
        d["put_oi"] += p.open_interest
        d["put_vol"] += p.volume

    result = []
    for strike in sorted(strike_data):
        d = strike_data[strike]
        result.append(
            StrikeGex(
                strike=strike,
                call_gex=d["call_gex"],
                put_gex=d["put_gex"],
                net_gex=d["call_gex"] + d["put_gex"],
                call_oi=d["call_oi"],
                put_oi=d["put_oi"],
                total_volume=d["call_vol"] + d["put_vol"],
            )
        )
    return result


def calculate_dex(delta: float, open_interest: int, spot: float) -> float:
    """Calculate Delta Exposure (DEX) for a single contract.

    Formula: delta * OI * 100 * spot
    Delta is already signed (negative for puts) from Schwab.
    """
    return delta * open_interest * 100 * spot


def calculate_vex(vega: float, open_interest: int, is_call: bool) -> float:
    """Calculate Vega Exposure (VEX) for a single contract.

    Formula: sign * vega * OI * 100
    Vega is always positive from Schwab, so we apply call/put sign.
    """
    sign = 1 if is_call else -1
    return sign * vega * open_interest * 100


def calculate_aggregate_gex(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
) -> GexSummary:
    """Calculate aggregate GEX, DEX, VEX, and theta across all contracts.

    Key metrics:
      total_gex:  call_gex + put_gex (net gamma exposure, positive = stable)
      gross_gex:  |call_gex| + |put_gex| (total hedging activity)
      gex_ratio:  |call_gex / put_gex| (>1 = call-dominated, <1 = put-dominated)
      total_dex:  net delta exposure (directional bias of dealer hedging)
      total_vex:  net vega exposure (sensitivity to IV changes)
      agg_theta:  total time decay across all contracts * OI * 100
    """
    call_gex = sum(calculate_strike_gex(c.gamma, c.open_interest, spot, True) for c in calls)
    put_gex = sum(calculate_strike_gex(p.gamma, p.open_interest, spot, False) for p in puts)
    total_gex = call_gex + put_gex
    gross_gex = abs(call_gex) + abs(put_gex)

    total_dex = sum(calculate_dex(c.delta, c.open_interest, spot) for c in calls) + sum(
        calculate_dex(p.delta, p.open_interest, spot) for p in puts
    )
    total_vex = sum(calculate_vex(c.vega, c.open_interest, True) for c in calls) + sum(
        calculate_vex(p.vega, p.open_interest, False) for p in puts
    )
    aggregate_theta = sum(c.theta * c.open_interest * 100 for c in calls) + sum(
        p.theta * p.open_interest * 100 for p in puts
    )

    gex_ratio = abs(call_gex / put_gex) if put_gex != 0 else 999.99

    return GexSummary(
        symbol=calls[0].underlying_symbol if calls else puts[0].underlying_symbol,
        spot_price=spot,
        timestamp=datetime.now(UTC),
        total_gex=total_gex,
        gross_gex=gross_gex,
        total_dex=total_dex,
        total_vex=total_vex,
        aggregate_theta=aggregate_theta,
        call_gex=call_gex,
        put_gex=put_gex,
        gex_ratio=gex_ratio,
        contracts_analyzed=len(calls) + len(puts),
    )


def filter_contracts_by_dte(
    contracts: list[OptionContract],
    max_dte: int | None = None,
    min_dte: int | None = None,
) -> list[OptionContract]:
    """Filter contracts by days to expiration range."""
    result = contracts
    if max_dte is not None:
        result = [c for c in result if c.days_to_expiration <= max_dte]
    if min_dte is not None:
        result = [c for c in result if c.days_to_expiration >= min_dte]
    return result


def project_charm_adjusted_gex(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    hours_forward: float,
    max_dte: int | None = None,
) -> list[StrikeGex]:
    """Project GEX after charm decay over the given hours.

    Charm approximation: charm = -theta / spot
    Gamma adjustment: new_gamma = gamma + charm * (hours / 24)
    """
    adjusted_calls = _apply_gamma_adjustment(calls, spot, charm_hours=hours_forward)
    adjusted_puts = _apply_gamma_adjustment(puts, spot, charm_hours=hours_forward)
    return calculate_per_strike_gex(adjusted_calls, adjusted_puts, spot, max_dte=max_dte)


def project_vanna_adjusted_gex(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    iv_change_pct: float,
    max_dte: int | None = None,
) -> list[StrikeGex]:
    """Project GEX after an IV change via vanna.

    Vanna approximation: vanna = vega / spot
    Gamma adjustment: new_gamma = gamma + vanna * iv_change_pct
    """
    adjusted_calls = _apply_gamma_adjustment(calls, spot, iv_change_pct=iv_change_pct)
    adjusted_puts = _apply_gamma_adjustment(puts, spot, iv_change_pct=iv_change_pct)
    return calculate_per_strike_gex(adjusted_calls, adjusted_puts, spot, max_dte=max_dte)


def _apply_gamma_adjustment(
    contracts: list[OptionContract],
    spot: float,
    charm_hours: float = 0.0,
    iv_change_pct: float = 0.0,
) -> list[OptionContract]:
    """Create copies of contracts with gamma adjusted for charm and/or vanna.

    Charm adjustment (time decay effect on gamma):
      charm = -theta / spot  (how much gamma changes per day)
      gamma_change = charm * (hours / 24)  (fraction of a day)

    Vanna adjustment (IV change effect on gamma):
      vanna = vega / spot  (how much gamma changes per 1% IV move)
      gamma_change = vanna * iv_change_pct

    Both adjustments are additive. Gamma is floored at 0 (can't go negative).
    """
    adjusted = []
    for c in contracts:
        charm = -c.theta / spot if spot != 0 else 0.0
        vanna = c.vega / spot if spot != 0 else 0.0
        gamma_adj = charm * (charm_hours / 24.0) + vanna * iv_change_pct
        new_gamma = max(c.gamma + gamma_adj, 0.0)
        adjusted.append(c.model_copy(update={"gamma": new_gamma}))
    return adjusted
