"""IV context — percentile, rank, realized vol, and regime classification.

History-dependent fields return None until Phase 3B provides historical data.
All functions are pure computation (no I/O, no side effects).
"""

import math
import statistics


def classify_iv_regime(atm_iv: float) -> str:
    """Classify IV regime from absolute ATM IV level.

    Used when percentile is unavailable (Phase 3A).
    Thresholds:
      low:      ATM IV < 15
      normal:   15 <= ATM IV < 25
      elevated: 25 <= ATM IV < 35
      high:     ATM IV >= 35
    """
    if atm_iv < 15:
        return "low"
    elif atm_iv < 25:
        return "normal"
    elif atm_iv < 35:
        return "elevated"
    else:
        return "high"


def calculate_iv_percentile(
    current_iv: float,
    iv_history: list[float] | None,
) -> float | None:
    """Calculate IV percentile rank vs historical IV values.

    Percentile = % of historical values below current IV.
    Returns None if iv_history is None or empty.
    """
    if not iv_history:
        return None
    count_below = sum(1 for v in iv_history if v < current_iv)
    return round(count_below / len(iv_history) * 100, 2)


def calculate_iv_rank(
    current_iv: float,
    iv_history: list[float] | None,
) -> float | None:
    """Calculate IV rank: (current - min) / (max - min) * 100.

    Returns None if iv_history is None or empty.
    Returns 0 if min == max (flat history).
    """
    if not iv_history:
        return None
    min_iv = min(iv_history)
    max_iv = max(iv_history)
    if max_iv == min_iv:
        return 0.0
    return round((current_iv - min_iv) / (max_iv - min_iv) * 100, 2)


def calculate_realized_volatility(
    daily_closes: list[float] | None,
    window: int = 20,
) -> float | None:
    """Calculate realized volatility from daily close prices.

    RV = stdev(ln(close_t / close_{t-1})) * sqrt(252) * 100

    Needs at least window+1 data points (window returns).
    Returns None if daily_closes is None or insufficient data.
    """
    if not daily_closes or len(daily_closes) < window + 1:
        return None
    # Use the last window+1 closes
    closes = daily_closes[-(window + 1):]
    log_returns = [
        math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
    ]
    return statistics.stdev(log_returns) * math.sqrt(252) * 100


def calculate_iv_rv_premium(
    atm_iv: float,
    rv_20d: float | None,
) -> float | None:
    """Calculate IV minus RV premium.

    Returns None if rv_20d is None.
    """
    if rv_20d is None:
        return None
    return atm_iv - rv_20d


def build_iv_context(
    atm_iv: float,
    iv_history: list[float] | None = None,
    daily_closes: list[float] | None = None,
) -> dict:
    """Build the full IV context dict.

    In Phase 3A, history params are None so percentile/rank/rv/premium
    are all None. Regime is always computed from absolute IV level.
    """
    rv_20d = calculate_realized_volatility(daily_closes)
    return {
        "percentile": calculate_iv_percentile(atm_iv, iv_history),
        "rank": calculate_iv_rank(atm_iv, iv_history),
        "rv_20d": rv_20d,
        "iv_rv_premium": calculate_iv_rv_premium(atm_iv, rv_20d),
        "regime": classify_iv_regime(atm_iv),
    }
