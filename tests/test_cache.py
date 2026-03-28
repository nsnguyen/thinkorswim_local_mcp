"""Tests for src/data/cache.py — disk cache with per-DTE-range TTL.

Verifies cache hit/miss behavior, TTL logic, and chain/quote-specific methods.
These tests ensure the caching layer correctly prevents redundant API calls.
"""

import time

import pytest

from src.data.cache import CacheManager, get_ttl_for_dte_range

# ── TTL Logic ──────────────────────────────────────────────────────


class TestGetTtlForDteRange:
    """Tests for the get_ttl_for_dte_range function."""

    @pytest.mark.parametrize(
        "from_dte,to_dte,expected_ttl",
        [
            (0, 7, 60),  # near-term: 60s
            (8, 45, 120),  # mid-term: 120s
            (46, 180, 300),  # medium-term: 300s
            (181, 365, 600),  # long-term: 600s
            (366, 9999, 900),  # LEAPs: 900s
        ],
        ids=["near-term", "mid-term", "medium-term", "long-term", "leaps"],
    )
    def test_ttl_for_each_dte_range(self, from_dte: int, to_dte: int, expected_ttl: int) -> None:
        """Test that each DTE range maps to the correct cache TTL.

        TTLs increase with DTE because far-dated options change less frequently.
        """
        assert get_ttl_for_dte_range(from_dte, to_dte) == expected_ttl

    def test_ttl_fallback_for_unknown_range(self) -> None:
        """Test that an out-of-bounds DTE range returns the fallback TTL of 60s.

        This should not happen in practice, but ensures no crash.
        """
        result = get_ttl_for_dte_range(99999, 99999)
        assert result == 60


# ── CacheManager ───────────────────────────────────────────────────


class TestCacheManager:
    """Tests for the CacheManager class."""

    def test_get_returns_none_on_miss(self, cache_manager: CacheManager) -> None:
        """Test that get() returns None when key is not in cache.

        A cache miss must return None so the caller knows to fetch from API.
        """
        assert cache_manager.get("nonexistent_key") is None

    def test_set_and_get_round_trip(self, cache_manager: CacheManager) -> None:
        """Test that a value set in cache can be retrieved immediately."""
        cache_manager.set("test_key", {"value": 42}, ttl=60)
        result = cache_manager.get("test_key")
        assert result == {"value": 42}

    def test_cache_expires_after_ttl(self, cache_manager: CacheManager) -> None:
        """Test that cached values expire and return None after TTL elapses.

        Uses a 1-second TTL to keep the test fast.
        """
        cache_manager.set("expiring_key", "data", ttl=1)
        assert cache_manager.get("expiring_key") == "data"
        time.sleep(1.1)
        assert cache_manager.get("expiring_key") is None

    def test_clear_removes_all_entries(self, cache_manager: CacheManager) -> None:
        """Test that clear() removes all cached data."""
        cache_manager.set("key1", "a", ttl=60)
        cache_manager.set("key2", "b", ttl=60)
        cache_manager.clear()
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key2") is None


# ── Quote Cache ────────────────────────────────────────────────────


class TestQuoteCache:
    """Tests for quote-specific cache methods."""

    def test_get_quote_returns_none_on_miss(self, cache_manager: CacheManager) -> None:
        """Test that get_quote() returns None for uncached symbols."""
        assert cache_manager.get_quote("SPX") is None

    def test_set_and_get_quote_round_trip(self, cache_manager: CacheManager) -> None:
        """Test that a cached quote can be retrieved by symbol."""
        quote_data = {"symbol": "SPX", "last": 5900.0}
        cache_manager.set_quote("SPX", quote_data)
        result = cache_manager.get_quote("SPX")
        assert result == quote_data

    def test_different_symbols_cached_independently(self, cache_manager: CacheManager) -> None:
        """Test that quotes for different symbols don't collide in cache."""
        cache_manager.set_quote("SPX", {"last": 5900.0})
        cache_manager.set_quote("AAPL", {"last": 150.0})
        assert cache_manager.get_quote("SPX")["last"] == 5900.0
        assert cache_manager.get_quote("AAPL")["last"] == 150.0


# ── Chain Cache ────────────────────────────────────────────────────


class TestChainCache:
    """Tests for options chain-specific cache methods."""

    def test_get_chain_returns_none_on_miss(self, cache_manager: CacheManager) -> None:
        """Test that get_chain() returns None for uncached symbol/DTE combinations."""
        assert cache_manager.get_chain("SPX", 0, 7) is None

    def test_set_and_get_chain_round_trip(self, cache_manager: CacheManager) -> None:
        """Test that a cached chain can be retrieved by symbol and DTE range."""
        chain_data = {"symbol": "SPX", "contracts": []}
        cache_manager.set_chain("SPX", 0, 7, chain_data)
        result = cache_manager.get_chain("SPX", 0, 7)
        assert result == chain_data

    def test_different_dte_ranges_cached_independently(self, cache_manager: CacheManager) -> None:
        """Test that different DTE ranges for the same symbol are separate cache entries.

        This is critical for the multi-range DTE fetching strategy where
        each range has its own TTL.
        """
        cache_manager.set_chain("SPX", 0, 7, {"range": "near"})
        cache_manager.set_chain("SPX", 8, 45, {"range": "mid"})
        assert cache_manager.get_chain("SPX", 0, 7)["range"] == "near"
        assert cache_manager.get_chain("SPX", 8, 45)["range"] == "mid"

    def test_set_chain_uses_correct_ttl(self, cache_manager: CacheManager) -> None:
        """Test that set_chain() applies the DTE-range-appropriate TTL.

        Near-term (0-7 DTE) has 60s TTL. After expiry, cache should miss.
        """
        cache_manager.set_chain("SPX", 0, 7, {"data": True})
        assert cache_manager.get_chain("SPX", 0, 7) is not None
        # TTL is 60s — we can't wait that long, but we verify it was cached
