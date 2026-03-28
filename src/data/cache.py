"""Disk cache with per-DTE-range TTL for options chain data."""

from pathlib import Path

import diskcache

from src.shared.logging import get_logger

logger = get_logger(__name__)

# DTE range -> cache TTL in seconds
DTE_RANGE_TTLS: list[tuple[int, int, int]] = [
    (0, 7, 60),  # 0-7 DTE: 60s
    (8, 45, 120),  # 8-45 DTE: 120s
    (46, 180, 300),  # 46-180 DTE: 300s
    (181, 365, 600),  # 181-365 DTE: 600s
    (366, 9999, 900),  # 366+ DTE: 900s
]

QUOTE_CACHE_TTL_DEFAULT = 5  # seconds


def get_ttl_for_dte_range(from_dte: int, to_dte: int) -> int:
    """Get cache TTL for a given DTE range based on the shortest-DTE bucket."""
    for range_min, range_max, ttl in DTE_RANGE_TTLS:
        if from_dte >= range_min and from_dte <= range_max:
            return ttl
    return 60  # fallback


class CacheManager:
    """Disk-based cache with TTL support for market data."""

    def __init__(
        self, cache_dir: str = "./cache", quote_ttl: int = QUOTE_CACHE_TTL_DEFAULT
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._quote_ttl = quote_ttl
        self._cache = diskcache.Cache(str(self._cache_dir))
        logger.info("Cache initialized at %s (quote TTL=%ds)", self._cache_dir, self._quote_ttl)

    def get(self, key: str) -> object | None:
        """Get cached value, returns None if expired or missing."""
        return self._cache.get(key)

    def set(self, key: str, value: object, ttl: int) -> None:
        """Set cached value with TTL in seconds."""
        self._cache.set(key, value, expire=ttl)

    def get_chain(self, symbol: str, from_dte: int, to_dte: int) -> dict | None:
        """Get cached options chain for a specific DTE range."""
        key = f"chain:{symbol}:{from_dte}-{to_dte}"
        return self._cache.get(key)

    def set_chain(self, symbol: str, from_dte: int, to_dte: int, data: dict) -> None:
        """Cache options chain data with DTE-range-appropriate TTL."""
        key = f"chain:{symbol}:{from_dte}-{to_dte}"
        ttl = get_ttl_for_dte_range(from_dte, to_dte)
        self._cache.set(key, data, expire=ttl)
        logger.debug("Cached chain %s (TTL=%ds)", key, ttl)

    def get_quote(self, symbol: str) -> dict | None:
        """Get cached quote."""
        key = f"quote:{symbol}"
        return self._cache.get(key)

    def set_quote(self, symbol: str, data: dict, ttl: int | None = None) -> None:
        """Cache quote data with configurable TTL (defaults to instance quote_ttl)."""
        key = f"quote:{symbol}"
        self._cache.set(key, data, expire=ttl if ttl is not None else self._quote_ttl)

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def close(self) -> None:
        """Close the cache."""
        self._cache.close()
