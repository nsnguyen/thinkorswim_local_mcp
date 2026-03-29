"""Core computation modules — pure math, no I/O."""


class GexCalculationError(Exception):
    """Raised when GEX calculation encounters invalid or insufficient data."""


class VolatilityCalculationError(Exception):
    """Raised when volatility calculation encounters invalid or insufficient data."""


class SnapshotStoreError(Exception):
    """Raised when snapshot store operations fail."""


class TradeMathError(Exception):
    """Raised when trade evaluation encounters invalid data."""


class AlertEngineError(Exception):
    """Raised when alert engine operations fail."""
