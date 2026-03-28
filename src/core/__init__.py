"""Core computation modules — pure math, no I/O."""


class GexCalculationError(Exception):
    """Raised when GEX calculation encounters invalid or insufficient data."""


class VolatilityCalculationError(Exception):
    """Raised when volatility calculation encounters invalid or insufficient data."""
