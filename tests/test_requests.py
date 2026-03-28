"""Tests for src/shared/requests.py — shared Schwab API request layer.

Verifies that all Schwab API calls go through a single function that
handles retries, backoff, and 429 rate limit detection. This is the
single entry point for all HTTP calls to Schwab — future phases get
retry for free by using this module.
"""

from unittest.mock import MagicMock

import pytest

from src.shared.requests import SchwabAPIError, call_schwab_api

# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response with .json() and .status_code."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    return resp


# ── call_schwab_api ────────────────────────────────────────────────


class TestCallSchwabApi:
    """Tests for the call_schwab_api function."""

    def test_calls_correct_method_on_client(self) -> None:
        """Test that call_schwab_api calls the named method on the schwabdev client.

        Verifies the method name is resolved and called correctly.
        """
        client = MagicMock()
        client.quote.return_value = _make_mock_response({"SPX": {}})

        call_schwab_api(client, "quote", "SPX")

        client.quote.assert_called_once_with("SPX")

    def test_returns_parsed_json(self) -> None:
        """Test that call_schwab_api returns the parsed JSON from the response.

        The caller should get a dict, not a requests.Response object.
        """
        client = MagicMock()
        client.quote.return_value = _make_mock_response({"SPX": {"quote": {"lastPrice": 5900}}})

        result = call_schwab_api(client, "quote", "SPX")

        assert result == {"SPX": {"quote": {"lastPrice": 5900}}}

    def test_passes_args_and_kwargs(self) -> None:
        """Test that positional and keyword arguments are forwarded to the client method.

        Options chain calls use many kwargs — all must be forwarded correctly.
        """
        client = MagicMock()
        client.option_chains.return_value = _make_mock_response({"status": "SUCCESS"})

        call_schwab_api(
            client,
            "option_chains",
            symbol="SPX",
            contractType="ALL",
            includeUnderlyingQuote=True,
        )

        client.option_chains.assert_called_once_with(
            symbol="SPX",
            contractType="ALL",
            includeUnderlyingQuote=True,
        )

    def test_retries_on_transient_error(self) -> None:
        """Test that transient errors trigger retries.

        First call fails, second succeeds — should return the successful result.
        """
        client = MagicMock()
        client.quote.side_effect = [
            Exception("connection reset"),
            _make_mock_response({"SPX": {}}),
        ]

        result = call_schwab_api(client, "quote", "SPX", max_retries=3, base_delay=0.01)

        assert result == {"SPX": {}}
        assert client.quote.call_count == 2

    def test_raises_schwab_api_error_on_429(self) -> None:
        """Test that HTTP 429 responses raise SchwabAPIError.

        Schwab returns 429 when rate limited (120 req/min exceeded).
        The error should be clear about what happened.
        """
        client = MagicMock()
        resp_429 = _make_mock_response({}, status_code=429)
        client.quote.return_value = resp_429

        with pytest.raises(SchwabAPIError, match="rate limit"):
            call_schwab_api(client, "quote", "SPX", max_retries=1, base_delay=0.01)

    def test_retries_on_429_before_raising(self) -> None:
        """Test that 429 errors trigger retries before giving up.

        First call returns 429, second call succeeds — should retry and return.
        """
        client = MagicMock()
        resp_429 = _make_mock_response({}, status_code=429)
        resp_ok = _make_mock_response({"SPX": {}}, status_code=200)
        client.quote.side_effect = [resp_429, resp_ok]

        result = call_schwab_api(client, "quote", "SPX", max_retries=3, base_delay=0.01)

        assert result == {"SPX": {}}
        assert client.quote.call_count == 2

    def test_raises_schwab_api_error_after_all_retries_exhausted(self) -> None:
        """Test that SchwabAPIError is raised when all retries fail.

        After max_retries attempts, should raise with a clear message
        including the method name and last error.
        """
        client = MagicMock()
        client.quote.side_effect = Exception("timeout")

        with pytest.raises(SchwabAPIError, match="quote"):
            call_schwab_api(client, "quote", "SPX", max_retries=2, base_delay=0.01)

        assert client.quote.call_count == 2

    def test_raises_schwab_api_error_on_invalid_method(self) -> None:
        """Test that calling a non-existent method raises SchwabAPIError.

        If the method name is wrong, the error should be immediate and clear.
        """
        client = MagicMock(spec=[])  # no methods

        with pytest.raises(SchwabAPIError, match="nonexistent_method"):
            call_schwab_api(client, "nonexistent_method")

    def test_default_retry_settings(self) -> None:
        """Test that default retry settings are used when not specified.

        Ensures the function works with no explicit retry configuration.
        """
        client = MagicMock()
        client.quote.return_value = _make_mock_response({"SPX": {}})

        result = call_schwab_api(client, "quote", "SPX")

        assert result == {"SPX": {}}
