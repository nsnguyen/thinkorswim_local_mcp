"""Retry logic with exponential backoff for Schwab API calls.

schwabdev has no built-in rate limit handling, retry logic, or 429 detection.
This module provides a retry decorator that handles transient failures
(network errors, HTTP 429 rate limits) with configurable backoff.
"""

import functools
import time
from collections.abc import Callable
from typing import TypeVar

from src.shared.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class RateLimitExceeded(Exception):
    """Raised when Schwab API returns HTTP 429 (Too Many Requests).

    Schwab enforces 120 requests/minute. When exceeded, wait 60 seconds.
    """


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable:
    """Decorator that retries a function on exception with exponential backoff.

    Args:
        max_retries: Maximum number of attempts before raising RetryExhausted.
        base_delay: Initial delay in seconds before first retry.
        backoff_factor: Multiplier applied to delay after each failed attempt.
            delay = base_delay * (backoff_factor ** attempt_number)
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (backoff_factor**attempt)
                        logger.warning(
                            "Attempt %d/%d failed: %s. Retrying in %.2fs...",
                            attempt + 1,
                            max_retries,
                            e,
                            delay,
                        )
                        time.sleep(delay)

            raise RetryExhausted(
                f"Failed after {max_retries} attempts: {last_exception}"
            ) from last_exception

        return wrapper

    return decorator
