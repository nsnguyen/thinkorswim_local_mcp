"""IV skew, butterfly, term structure, ATM/delta finding, and expected move.

All functions are pure computation (no I/O, no side effects).

IV Skew
=======
Skew measures how much more expensive OTM puts are vs OTM calls.
  skew_25d = IV(25-delta put) - IV(25-delta call)
  Positive skew (normal): puts more expensive → downside protection demand.
  Negative skew (inverted): calls more expensive → unusual, often pre-event.

Butterfly = put_25d_IV + call_25d_IV - 2 * ATM_IV
  Measures convexity (wing premium). Higher = fatter tails expected.

Term Structure
==============
ATM IV across expirations reveals the market's time horizon for vol:
  contango:      Longer-dated IV > near-term (normal, calm markets)
  backwardation: Near-term IV > longer-dated (stress, event-driven)
  humped:        Mid-term peak (specific event priced in)

Expected Move
=============
  1SD move = spot * (IV/100) * sqrt(DTE/365)
  Straddle ≈ ATM call mark + ATM put mark (market-implied move)
"""

import math
from collections import defaultdict
from datetime import date

from src.core import VolatilityCalculationError
from src.data.models import OptionContract, TermStructurePoint


def find_atm_contracts(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    expiration: date | None = None,
) -> tuple[OptionContract, OptionContract]:
    """Find the call and put closest to spot price.

    Returns (atm_call, atm_put).
    """
    filtered_calls = filter_contracts_by_expiration(calls, expiration) if expiration else calls
    filtered_puts = filter_contracts_by_expiration(puts, expiration) if expiration else puts

    if not filtered_calls or not filtered_puts:
        raise VolatilityCalculationError("No contracts found for ATM matching")

    atm_call = min(filtered_calls, key=lambda c: abs(c.strike_price - spot))
    atm_put = min(filtered_puts, key=lambda p: abs(p.strike_price - spot))
    return atm_call, atm_put


def calculate_atm_iv(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    expiration: date | None = None,
) -> float:
    """Calculate ATM IV as the average of ATM call and put IVs."""
    atm_call, atm_put = find_atm_contracts(calls, puts, spot, expiration)
    return (atm_call.implied_volatility + atm_put.implied_volatility) / 2


def find_contract_by_delta(
    contracts: list[OptionContract],
    target_delta: float,
    expiration: date | None = None,
) -> OptionContract:
    """Find the contract nearest to target delta.

    For puts, target_delta should be negative (e.g., -0.25).
    For calls, target_delta should be positive (e.g., 0.25).
    """
    filtered = filter_contracts_by_expiration(contracts, expiration) if expiration else contracts
    if not filtered:
        raise VolatilityCalculationError(
            f"No contracts found for delta matching (target={target_delta})"
        )
    return min(filtered, key=lambda c: abs(c.delta - target_delta))


def calculate_skew(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
    expiration: date | None = None,
) -> dict:
    """Calculate IV skew metrics for the given expiration.

    Returns dict with: put_25d, call_25d, skew_25d, skew_10d, skew_40d,
    butterfly, regime.
    """
    atm_iv = calculate_atm_iv(calls, puts, spot, expiration)

    # Find contracts by delta target
    put_25d = find_contract_by_delta(puts, -0.25, expiration)
    call_25d = find_contract_by_delta(calls, 0.25, expiration)
    put_10d = find_contract_by_delta(puts, -0.10, expiration)
    call_10d = find_contract_by_delta(calls, 0.10, expiration)
    put_40d = find_contract_by_delta(puts, -0.40, expiration)
    call_40d = find_contract_by_delta(calls, 0.40, expiration)

    skew_25d = put_25d.implied_volatility - call_25d.implied_volatility
    skew_10d = put_10d.implied_volatility - call_10d.implied_volatility
    skew_40d = put_40d.implied_volatility - call_40d.implied_volatility
    butterfly = (
        put_25d.implied_volatility + call_25d.implied_volatility - 2 * atm_iv
    )

    return {
        "put_25d": put_25d.implied_volatility,
        "call_25d": call_25d.implied_volatility,
        "skew_25d": round(skew_25d, 4),
        "skew_10d": round(skew_10d, 4),
        "skew_40d": round(skew_40d, 4),
        "butterfly": round(butterfly, 4),
        "regime": classify_skew_regime(skew_25d, atm_iv),
    }


def classify_skew_regime(skew_25d: float, atm_iv: float) -> str:
    """Classify skew regime from 25d skew and ATM IV.

    Uses ratio = skew_25d / atm_iv:
      steep_skew:  ratio > 0.35 (extreme put demand)
      normal_skew: 0.15 <= ratio <= 0.35
      flat_skew:   0.0 <= ratio < 0.15 (low skew, complacent)
      inverted:    ratio < 0.0 (calls more expensive, unusual)
    """
    if atm_iv == 0:
        return "flat_skew"
    ratio = skew_25d / atm_iv
    if ratio < 0:
        return "inverted"
    elif ratio < 0.15:
        return "flat_skew"
    elif ratio <= 0.35:
        return "normal_skew"
    else:
        return "steep_skew"


def calculate_term_structure(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot: float,
) -> list[TermStructurePoint]:
    """Calculate ATM IV for each expiration in the chain.

    Groups contracts by expiration, finds ATM for each,
    returns sorted list of TermStructurePoint (ascending DTE).
    """
    if not calls and not puts:
        raise VolatilityCalculationError("No contracts for term structure")

    call_groups = group_contracts_by_expiration(calls)
    put_groups = group_contracts_by_expiration(puts)

    # Use expirations present in both calls and puts
    common_exps = sorted(set(call_groups) & set(put_groups))
    if not common_exps:
        raise VolatilityCalculationError(
            "No common expirations between calls and puts"
        )

    points = []
    for exp in common_exps:
        atm_iv = calculate_atm_iv(
            call_groups[exp], put_groups[exp], spot, expiration=None
        )
        dte = call_groups[exp][0].days_to_expiration
        points.append(
            TermStructurePoint(expiration=exp, dte=dte, atm_iv=round(atm_iv, 2))
        )
    return sorted(points, key=lambda p: p.dte)


def calculate_term_structure_slope(
    points: list[TermStructurePoint],
) -> float:
    """Simple linear regression slope: ATM IV vs DTE.

    slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    Returns 0.0 if fewer than 2 points.
    """
    n = len(points)
    if n < 2:
        return 0.0

    sum_x = sum(p.dte for p in points)
    sum_y = sum(p.atm_iv for p in points)
    sum_xy = sum(p.dte * p.atm_iv for p in points)
    sum_x2 = sum(p.dte**2 for p in points)

    denom = n * sum_x2 - sum_x**2
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def classify_term_structure_shape(
    points: list[TermStructurePoint],
) -> str:
    """Classify term structure shape.

    Checks for humped first (peak at interior point), then uses slope.
    """
    if len(points) < 2:
        return "flat"

    # Check for humped: max IV at interior point
    if len(points) >= 3:
        max_idx = max(range(len(points)), key=lambda i: points[i].atm_iv)
        if 0 < max_idx < len(points) - 1:
            return "humped"

    slope = calculate_term_structure_slope(points)
    threshold = 0.02
    if slope > threshold:
        return "contango"
    elif slope < -threshold:
        return "backwardation"
    else:
        return "flat"


def calculate_expected_move_1sd(
    spot: float,
    atm_iv: float,
    dte: int,
) -> float:
    """Calculate 1 standard deviation expected move.

    EM = spot * (atm_iv / 100) * sqrt(dte / 365)
    """
    if dte == 0:
        return 0.0
    return spot * (atm_iv / 100) * math.sqrt(dte / 365)


def filter_contracts_by_expiration(
    contracts: list[OptionContract],
    expiration: date,
) -> list[OptionContract]:
    """Filter contracts to a single expiration date."""
    return [c for c in contracts if c.expiration_date == expiration]


def group_contracts_by_expiration(
    contracts: list[OptionContract],
) -> dict[date, list[OptionContract]]:
    """Group contracts by expiration date."""
    groups: dict[date, list[OptionContract]] = defaultdict(list)
    for c in contracts:
        groups[c.expiration_date].append(c)
    return dict(groups)
