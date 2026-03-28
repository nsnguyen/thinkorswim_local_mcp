"""Shared Schwab API request layer with retry, backoff, and 429 handling.

All Schwab API calls must go through call_schwab_api(). This is the single
entry point for HTTP calls to Schwab — every phase gets retry for free.

schwabdev has zero rate limit handling, no retry logic, and no 429 detection.
This module fills that gap.
"""

import time

from src.shared.logging import get_logger

logger = get_logger(__name__)

# Default retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


class SchwabAPIError(Exception):
    """Raised when a Schwab API call fails after all retries."""


def call_schwab_api(
    client: object,
    method_name: str,
    *args: object,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    **kwargs: object,
) -> dict:
    """Make a Schwab API call with retry, backoff, and 429 handling.

    Args:
        client: A schwabdev.Client instance.
        method_name: Name of the method to call (e.g., "quote", "option_chains").
        *args: Positional arguments forwarded to the client method.
        max_retries: Maximum number of attempts before raising SchwabAPIError.
        base_delay: Initial delay in seconds before first retry.
        backoff_factor: Multiplier applied to delay after each failed attempt.
        **kwargs: Keyword arguments forwarded to the client method.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        SchwabAPIError: If the method doesn't exist, rate limit is hit,
            or all retries are exhausted.
    """
    method = _resolve_method(client, method_name)
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            resp = method(*args, **kwargs)
            _check_rate_limit(resp, method_name)
            return resp.json()
        except SchwabAPIError:
            # 429 rate limit — retry with backoff
            last_exception = SchwabAPIError(
                f"Schwab API rate limit hit on {method_name}. Schwab allows 120 req/min."
            )
            if attempt < max_retries - 1:
                delay = base_delay * (backoff_factor**attempt)
                logger.warning(
                    "Rate limited on %s (attempt %d/%d). Retrying in %.1fs...",
                    method_name,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (backoff_factor**attempt)
                logger.warning(
                    "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    method_name,
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                time.sleep(delay)

    raise SchwabAPIError(
        f"Schwab API call {method_name} failed after {max_retries} attempts: {last_exception}"
    ) from last_exception


def _resolve_method(client: object, method_name: str) -> object:
    """Resolve a method name on the schwabdev client.

    Raises SchwabAPIError if the method doesn't exist.
    """
    method = getattr(client, method_name, None)
    if method is None or not callable(method):
        raise SchwabAPIError(f"schwabdev.Client has no method '{method_name}'")
    return method


def _check_rate_limit(resp: object, method_name: str) -> None:
    """Check if the response indicates a 429 rate limit.

    Raises SchwabAPIError so the retry loop can catch it and back off.
    """
    status_code = getattr(resp, "status_code", None)
    if status_code == 429:
        raise SchwabAPIError(
            f"Schwab API rate limit hit on {method_name}. Schwab allows 120 req/min."
        )
