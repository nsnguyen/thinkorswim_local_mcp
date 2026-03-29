"""Pure trade math computation — strategy detection, P&L, POP, breakevens, net greeks.

All functions are pure (no I/O, no side effects). POP uses Black-Scholes N(d2).
"""

import math

from src.core import TradeMathError


def detect_strategy(legs: list[dict]) -> str:
    """Auto-detect strategy type from legs.

    Examines leg count, types, actions, strikes, and expirations to classify.
    """
    if not legs:
        raise TradeMathError("Cannot detect strategy: no legs provided")

    n = len(legs)

    if n == 1:
        leg = legs[0]
        action = leg["action"].upper()
        opt_type = leg["option_type"].upper()
        if action == "BUY" and opt_type == "CALL":
            return "long_call"
        if action == "SELL" and opt_type == "CALL":
            return "short_call"
        if action == "BUY" and opt_type == "PUT":
            return "long_put"
        if action == "SELL" and opt_type == "PUT":
            return "short_put"

    if n == 2:
        l1, l2 = legs[0], legs[1]
        types = {l1["option_type"].upper(), l2["option_type"].upper()}
        strikes = {l1["strike"], l2["strike"]}
        exps = {l1["expiration"], l2["expiration"]}

        # Calendar spread: same strike, different expiration
        if len(strikes) == 1 and len(exps) == 2:
            return "calendar_spread"

        # Same type, same expiration, different strikes → vertical
        if len(types) == 1 and len(exps) == 1 and len(strikes) == 2:
            return _classify_vertical(legs)

        # Different types, same expiration → straddle/strangle
        if len(types) == 2 and len(exps) == 1:
            return _classify_straddle_strangle(legs)

    if n == 4:
        return _classify_four_leg(legs)

    return "custom"


def _classify_vertical(legs: list[dict]) -> str:
    """Classify a 2-leg vertical spread."""
    opt_type = legs[0]["option_type"].upper()
    sorted_legs = sorted(legs, key=lambda lg: lg["strike"])
    lower_action = sorted_legs[0]["action"].upper()

    if opt_type == "CALL":
        if lower_action == "BUY":
            return "bull_call_spread"
        return "bear_call_spread"
    else:  # PUT
        if lower_action == "BUY":
            return "bull_put_spread"
        return "bear_put_spread"


def _classify_straddle_strangle(legs: list[dict]) -> str:
    """Classify a 2-leg straddle or strangle."""
    strikes = {lg["strike"] for lg in legs}
    actions = [lg["action"].upper() for lg in legs]

    if len(strikes) == 1:
        # Same strike → straddle
        if all(a == "SELL" for a in actions):
            return "short_straddle"
        if all(a == "BUY" for a in actions):
            return "long_straddle"
    else:
        # Different strikes → strangle
        if all(a == "SELL" for a in actions):
            return "short_strangle"
        if all(a == "BUY" for a in actions):
            return "long_strangle"

    return "custom"


def _classify_four_leg(legs: list[dict]) -> str:
    """Classify a 4-leg strategy (iron condor, iron butterfly, etc.)."""
    puts = [lg for lg in legs if lg["option_type"].upper() == "PUT"]
    calls = [lg for lg in legs if lg["option_type"].upper() == "CALL"]

    if len(puts) == 2 and len(calls) == 2:
        put_sells = [lg for lg in puts if lg["action"].upper() == "SELL"]
        put_buys = [lg for lg in puts if lg["action"].upper() == "BUY"]
        call_sells = [lg for lg in calls if lg["action"].upper() == "SELL"]
        call_buys = [lg for lg in calls if lg["action"].upper() == "BUY"]

        all_one = (
            len(put_sells) == 1 and len(put_buys) == 1
            and len(call_sells) == 1 and len(call_buys) == 1
        )
        if all_one:
            return "iron_condor"

    return "custom"


def calculate_net_credit(legs: list[dict]) -> float:
    """Calculate net credit (positive) or debit (negative) for a trade.

    SELL legs use bid price, BUY legs use ask price.
    """
    total = 0.0
    for leg in legs:
        qty = leg.get("quantity", 1)
        if leg["action"].upper() == "SELL":
            total += leg["bid"] * qty
        else:
            total -= leg["ask"] * qty
    return round(total, 4)


def calculate_max_profit_loss(
    strategy: str,
    net_credit: float,
    legs: list[dict],
) -> dict:
    """Calculate max profit and max loss for a strategy.

    Returns dict with max_profit and max_loss (in dollars, includes multiplier).
    """
    multiplier = 100.0

    if strategy in ("long_call", "long_strangle", "long_straddle"):
        return {
            "max_profit": float("inf"),
            "max_loss": abs(net_credit) * multiplier,
        }

    if strategy == "long_put":
        strike = legs[0]["strike"]
        return {
            "max_profit": (strike - abs(net_credit)) * multiplier,
            "max_loss": abs(net_credit) * multiplier,
        }

    if strategy in ("short_call", "short_strangle"):
        return {
            "max_profit": net_credit * multiplier,
            "max_loss": float("inf"),
        }

    if strategy == "short_straddle":
        return {
            "max_profit": net_credit * multiplier,
            "max_loss": float("inf"),
        }

    if strategy == "short_put":
        strike = legs[0]["strike"]
        return {
            "max_profit": net_credit * multiplier,
            "max_loss": (strike - net_credit) * multiplier,
        }

    # Spreads (verticals, iron condor)
    if strategy in ("bull_put_spread", "bear_call_spread"):
        width = _spread_width(legs)
        return {
            "max_profit": net_credit * multiplier,
            "max_loss": (width - net_credit) * multiplier,
        }

    if strategy in ("bull_call_spread", "bear_put_spread"):
        width = _spread_width(legs)
        debit = abs(net_credit)
        return {
            "max_profit": (width - debit) * multiplier,
            "max_loss": debit * multiplier,
        }

    if strategy == "iron_condor":
        width = _iron_condor_width(legs)
        return {
            "max_profit": net_credit * multiplier,
            "max_loss": (width - net_credit) * multiplier,
        }

    # Custom / unknown — can't compute
    return {
        "max_profit": float("inf"),
        "max_loss": float("inf"),
    }


def _spread_width(legs: list[dict]) -> float:
    """Get the width between strikes of a 2-leg spread."""
    strikes = sorted(lg["strike"] for lg in legs)
    return strikes[1] - strikes[0]


def _iron_condor_width(legs: list[dict]) -> float:
    """Get the wider side width of an iron condor."""
    puts = sorted(
        [lg for lg in legs if lg["option_type"].upper() == "PUT"],
        key=lambda lg: lg["strike"],
    )
    calls = sorted(
        [lg for lg in legs if lg["option_type"].upper() == "CALL"],
        key=lambda lg: lg["strike"],
    )
    put_width = puts[1]["strike"] - puts[0]["strike"]
    call_width = calls[1]["strike"] - calls[0]["strike"]
    return max(put_width, call_width)


def calculate_breakevens(
    strategy: str,
    net_credit: float,
    legs: list[dict],
) -> list[float]:
    """Calculate breakeven prices for a strategy."""
    if strategy in ("short_put", "bull_put_spread"):
        short_put = _find_short_leg(legs, "PUT")
        return [short_put["strike"] - net_credit]

    if strategy in ("short_call", "bear_call_spread"):
        short_call = _find_short_leg(legs, "CALL")
        return [short_call["strike"] + net_credit]

    if strategy == "long_call":
        return [legs[0]["strike"] + abs(net_credit)]

    if strategy == "long_put":
        return [legs[0]["strike"] - abs(net_credit)]

    if strategy in ("bull_call_spread",):
        long_call = _find_long_leg(legs, "CALL")
        return [long_call["strike"] + abs(net_credit)]

    if strategy in ("bear_put_spread",):
        long_put = _find_long_leg(legs, "PUT")
        return [long_put["strike"] - abs(net_credit)]

    if strategy == "iron_condor":
        short_put = _find_short_leg(legs, "PUT")
        short_call = _find_short_leg(legs, "CALL")
        return sorted([
            short_put["strike"] - net_credit,
            short_call["strike"] + net_credit,
        ])

    if strategy in ("short_straddle", "short_strangle"):
        short_put = [lg for lg in legs if lg["option_type"].upper() == "PUT"][0]
        short_call = [lg for lg in legs if lg["option_type"].upper() == "CALL"][0]
        return sorted([
            short_put["strike"] - net_credit,
            short_call["strike"] + net_credit,
        ])

    if strategy in ("long_straddle", "long_strangle"):
        long_put = [lg for lg in legs if lg["option_type"].upper() == "PUT"][0]
        long_call = [lg for lg in legs if lg["option_type"].upper() == "CALL"][0]
        debit = abs(net_credit)
        return sorted([
            long_put["strike"] - debit,
            long_call["strike"] + debit,
        ])

    return []


def _find_short_leg(legs: list[dict], opt_type: str) -> dict:
    """Find the SELL leg of a given type."""
    for leg in legs:
        if leg["action"].upper() == "SELL" and leg["option_type"].upper() == opt_type:
            return leg
    raise TradeMathError(f"No short {opt_type} leg found")


def _find_long_leg(legs: list[dict], opt_type: str) -> dict:
    """Find the BUY leg of a given type."""
    for leg in legs:
        if leg["action"].upper() == "BUY" and leg["option_type"].upper() == opt_type:
            return leg
    raise TradeMathError(f"No long {opt_type} leg found")


def calculate_d2(
    spot: float,
    breakeven: float,
    iv: float,
    dte_years: float,
    r: float = 0.05,
) -> float:
    """Calculate d2 from the Black-Scholes formula.

    d2 = (ln(S/K) + (r - σ²/2) × T) / (σ × √T)
    """
    if dte_years <= 0 or iv <= 0:
        return 0.0

    sqrt_t = math.sqrt(dte_years)
    d2 = (math.log(spot / breakeven) + (r - iv**2 / 2) * dte_years) / (iv * sqrt_t)
    return d2


def _norm_cdf(x: float) -> float:
    """Standard normal CDF — N(x) using math.erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def calculate_pop(
    spot: float,
    breakevens: list[float],
    iv: float,
    dte_years: float,
    strategy: str,
    r: float = 0.05,
) -> float:
    """Calculate probability of profit using Black-Scholes N(d2).

    For single-breakeven credit strategies: POP = N(d2) where d2 uses the breakeven.
    For two-breakeven strategies: POP = N(d2_upper) - N(d2_lower).
    For debit strategies: POP = 1 - N(d2) (probability price moves past breakeven).
    """
    if not breakevens:
        return 0.0

    if len(breakevens) == 2:
        # Two breakevens (iron condor, straddle, strangle)
        lower, upper = sorted(breakevens)
        d2_lower = calculate_d2(spot, lower, iv, dte_years, r)
        d2_upper = calculate_d2(spot, upper, iv, dte_years, r)

        # N(d2) = P(S_T > K), so P(lower < S_T < upper) = N(d2_lower) - N(d2_upper)
        prob_in_range = _norm_cdf(d2_lower) - _norm_cdf(d2_upper)

        if strategy in ("short_straddle", "short_strangle", "iron_condor"):
            return max(0.0, min(1.0, prob_in_range))
        else:
            return max(0.0, min(1.0, 1.0 - prob_in_range))

    # Single breakeven
    be = breakevens[0]
    d2 = calculate_d2(spot, be, iv, dte_years, r)

    # Credit puts / bull put spread: profit when price stays ABOVE breakeven
    if strategy in ("short_put", "bull_put_spread"):
        return _norm_cdf(d2)

    # Credit calls / bear call spread: profit when price stays BELOW breakeven
    if strategy in ("short_call", "bear_call_spread"):
        return 1.0 - _norm_cdf(d2)

    # Debit calls / bull call spread: profit when price goes ABOVE breakeven
    if strategy in ("long_call", "bull_call_spread"):
        return _norm_cdf(d2)

    # Debit puts / bear put spread: profit when price goes BELOW breakeven
    if strategy in ("long_put", "bear_put_spread"):
        return 1.0 - _norm_cdf(d2)

    return 0.5


def calculate_net_greeks(legs: list[dict]) -> dict:
    """Calculate net greeks across all legs.

    sign = +1 for BUY, -1 for SELL. Quantity multiplies.
    """
    net = {"net_delta": 0.0, "net_gamma": 0.0, "net_theta": 0.0, "net_vega": 0.0}

    for leg in legs:
        sign = 1.0 if leg["action"].upper() == "BUY" else -1.0
        qty = leg.get("quantity", 1)
        net["net_delta"] += leg["delta"] * sign * qty
        net["net_gamma"] += leg["gamma"] * sign * qty
        net["net_theta"] += leg["theta"] * sign * qty
        net["net_vega"] += leg["vega"] * sign * qty

    return {k: round(v, 6) for k, v in net.items()}
