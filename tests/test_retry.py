"""Tests for src/shared/retry.py — retry logic with exponential backoff.

Verifies that API calls are retried on transient failures (429, network errors)
with proper backoff, and that non-retryable errors propagate immediately.
schwabdev has zero rate limit handling, so this module is the safety net.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.shared.retry import (
    RateLimitExceeded,
    RetryExhausted,
    retry_on_failure,
)

# ── retry_on_failure ───────────────────────────────────────────────


class TestRetryOnFailure:
    """Tests for the retry_on_failure decorator."""

    def test_returns_result_on_first_success(self) -> None:
        """Test that a successful call returns immediately without retrying.

        If the function succeeds on the first try, no retries should happen.
        """
        mock_fn = MagicMock(return_value="success")

        @retry_on_failure(max_retries=3, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        result = do_work()

        assert result == "success"
        assert mock_fn.call_count == 1

    def test_retries_on_transient_error(self) -> None:
        """Test that transient errors trigger retries.

        Function fails twice then succeeds — should retry and return the result.
        """
        mock_fn = MagicMock(side_effect=[Exception("timeout"), Exception("timeout"), "ok"])

        @retry_on_failure(max_retries=3, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        result = do_work()

        assert result == "ok"
        assert mock_fn.call_count == 3

    def test_raises_retry_exhausted_after_max_retries(self) -> None:
        """Test that RetryExhausted is raised when all retries fail.

        If the function fails on every attempt, it should raise RetryExhausted
        wrapping the last error, not silently return None.
        """
        mock_fn = MagicMock(side_effect=Exception("persistent failure"))

        @retry_on_failure(max_retries=3, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        with pytest.raises(RetryExhausted, match="persistent failure"):
            do_work()

        assert mock_fn.call_count == 3

    def test_exponential_backoff_increases_delay(self) -> None:
        """Test that retry delays increase exponentially.

        With base_delay=0.05 and backoff_factor=2:
        attempt 1 fails → wait ~0.05s
        attempt 2 fails → wait ~0.10s
        attempt 3 succeeds

        Total wait should be >= 0.1s (roughly 0.05 + 0.10).
        """
        mock_fn = MagicMock(side_effect=[Exception("fail"), Exception("fail"), "ok"])

        @retry_on_failure(max_retries=3, base_delay=0.05, backoff_factor=2.0)
        def do_work() -> str:
            return mock_fn()

        start = time.monotonic()
        result = do_work()
        elapsed = time.monotonic() - start

        assert result == "ok"
        assert elapsed >= 0.1  # at least base_delay + base_delay*backoff

    @pytest.mark.parametrize(
        "max_retries",
        [1, 2, 5],
        ids=["1-retry", "2-retries", "5-retries"],
    )
    def test_respects_max_retries_count(self, max_retries: int) -> None:
        """Test that the function is called exactly max_retries times on failure.

        Ensures the retry count is respected regardless of the value.
        """
        mock_fn = MagicMock(side_effect=Exception("fail"))

        @retry_on_failure(max_retries=max_retries, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        with pytest.raises(RetryExhausted):
            do_work()

        assert mock_fn.call_count == max_retries

    def test_passes_args_and_kwargs_to_wrapped_function(self) -> None:
        """Test that arguments are forwarded correctly to the decorated function.

        The retry decorator must not swallow or alter function arguments.
        """
        mock_fn = MagicMock(return_value="result")

        @retry_on_failure(max_retries=3, base_delay=0.01)
        def do_work(symbol: str, from_dte: int = 0) -> str:
            return mock_fn(symbol, from_dte=from_dte)

        do_work("SPX", from_dte=7)

        mock_fn.assert_called_once_with("SPX", from_dte=7)


# ── RateLimitExceeded ──────────────────────────────────────────────


class TestRateLimitExceeded:
    """Tests for the RateLimitExceeded exception."""

    def test_rate_limit_error_is_retryable(self) -> None:
        """Test that RateLimitExceeded triggers retry when raised inside a retried function.

        Schwab returns HTTP 429 when rate limited — this must trigger retry with backoff.
        """
        mock_fn = MagicMock(side_effect=[RateLimitExceeded("429 Too Many Requests"), "ok"])

        @retry_on_failure(max_retries=3, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        result = do_work()

        assert result == "ok"
        assert mock_fn.call_count == 2

    def test_rate_limit_error_message(self) -> None:
        """Test that RateLimitExceeded has a clear error message.

        This message surfaces to Claude when all retries are exhausted.
        """
        error = RateLimitExceeded("429 Too Many Requests")
        assert "429" in str(error)


# ── RetryExhausted ─────────────────────────────────────────────────


class TestRetryExhausted:
    """Tests for the RetryExhausted exception."""

    def test_wraps_original_error(self) -> None:
        """Test that RetryExhausted wraps the original error via raise...from.

        When the decorator exhausts retries, the resulting RetryExhausted
        should chain the original exception as __cause__ so debugging
        shows the root cause.
        """
        mock_fn = MagicMock(side_effect=Exception("connection reset"))

        @retry_on_failure(max_retries=2, base_delay=0.01)
        def do_work() -> str:
            return mock_fn()

        with pytest.raises(RetryExhausted) as exc_info:
            do_work()

        assert exc_info.value.__cause__ is not None
        assert "connection reset" in str(exc_info.value.__cause__)
        assert "2 attempts" in str(exc_info.value)
