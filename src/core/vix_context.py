"""VIX regime classification and term structure.

All functions are pure computation (no I/O, no side effects).

VIX Regime Thresholds
=====================
  low:      VIX < 12  (complacency, low hedging demand)
  normal:   12-20     (typical market conditions)
  elevated: 20-30     (heightened fear, increased hedging)
  high:     >= 30     (crisis levels, extreme fear)

VIX Term Structure
==================
  VIX / VIX3M ratio reveals market's near-term vs medium-term fear:
  contango (ratio < 0.95):      Normal — near-term fear lower than medium-term
  flat (0.95-1.05):             Neutral — similar fear across horizons
  backwardation (ratio > 1.05): Stress — near-term fear exceeds medium-term
"""

from src.data.models import Quote


def classify_vix_regime(vix_level: float) -> str:
    """Classify VIX regime from absolute level."""
    if vix_level < 12:
        return "low"
    elif vix_level < 20:
        return "normal"
    elif vix_level < 30:
        return "elevated"
    else:
        return "high"


def calculate_vix_term_structure(
    vix_level: float,
    vix3m_level: float,
) -> tuple[float, str]:
    """Calculate VIX/VIX3M ratio and classify term structure shape.

    Returns (ratio, shape).
    """
    if vix3m_level == 0:
        return 999.99, "backwardation"

    ratio = round(vix_level / vix3m_level, 4)
    if ratio < 0.95:
        shape = "contango"
    elif ratio > 1.05:
        shape = "backwardation"
    else:
        shape = "flat"
    return ratio, shape


def build_vix_context(vix_quote: Quote, vix3m_quote: Quote) -> dict:
    """Build the full VIX context dict from VIX and VIX3M quotes."""
    ratio, shape = calculate_vix_term_structure(
        vix_quote.last, vix3m_quote.last
    )
    return {
        "vix": {
            "level": vix_quote.last,
            "change": vix_quote.net_change,
            "percentile": None,  # Phase 3B
            "regime": classify_vix_regime(vix_quote.last),
        },
        "vix3m": {
            "level": vix3m_quote.last,
        },
        "term_structure": {
            "ratio": ratio,
            "shape": shape,
        },
    }
