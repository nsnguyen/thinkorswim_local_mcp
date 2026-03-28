"""Tests for src/data/schwab_client.py — Schwab API wrapper.

Verifies multi-range DTE fetching, cache integration, contract parsing,
deduplication, and error propagation. Mocks at schwabdev.Client level.
"""

from unittest.mock import MagicMock

import pytest

from src.data.schwab_client import SchwabClient, SchwabClientError

# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock requests.Response with .json() returning given data."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


# ── get_quote ──────────────────────────────────────────────────────


class TestSchwabClientGetQuote:
    """Tests for SchwabClient.get_quote()."""

    def test_get_quote_calls_schwabdev_quote(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test that get_quote() calls schwabdev.Client.quote() with the symbol.

        Verifies the correct method is called with the correct parameter.
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response(spx_quote_response)

        result = schwab_client.get_quote("SPX")

        mock_schwabdev_client.quote.assert_called_once_with("SPX")
        assert result.symbol == "SPX"

    def test_get_quote_returns_correct_values(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test that get_quote() correctly maps Schwab response fields to Quote model.

        Verifies each field is extracted from the correct location in the response.
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response(spx_quote_response)

        quote = schwab_client.get_quote("SPX")

        assert quote.last == 5900.00
        assert quote.bid == 5899.50
        assert quote.ask == 5900.50
        assert quote.open == 5885.00
        assert quote.high == 5910.00
        assert quote.low == 5875.00
        assert quote.close == 5880.00
        assert quote.volume == 1500000
        assert quote.net_change == 20.00
        assert quote.net_change_pct == 0.34
        assert quote.is_delayed is False

    def test_get_quote_caches_result(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_quote_response: dict,
    ) -> None:
        """Test that get_quote() caches the result and serves from cache on second call.

        schwabdev.Client.quote() should only be called once even though
        get_quote() is called twice.
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response(spx_quote_response)

        quote1 = schwab_client.get_quote("SPX")
        quote2 = schwab_client.get_quote("SPX")

        mock_schwabdev_client.quote.assert_called_once()
        assert quote1.last == quote2.last

    def test_get_quote_raises_on_missing_symbol(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """Test that get_quote() raises SchwabClientError when symbol not in response.

        Schwab API may return data for a different symbol or empty response.
        """
        mock_schwabdev_client.quote.return_value = _make_mock_response({"OTHER": {"quote": {}}})

        with pytest.raises(SchwabClientError, match="No quote data returned for SPX"):
            schwab_client.get_quote("SPX")

    def test_get_quote_raises_on_api_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """Test that schwabdev.Client errors propagate as SchwabClientError.

        Network errors, timeouts, etc. from schwabdev should be wrapped
        with a clear message including the symbol.
        """
        mock_schwabdev_client.quote.side_effect = Exception("Connection timeout")

        with pytest.raises(SchwabClientError, match="SPX"):
            schwab_client.get_quote("SPX")


# ── get_options_chain ──────────────────────────────────────────────


class TestSchwabClientGetOptionsChain:
    """Tests for SchwabClient.get_options_chain()."""

    def test_get_options_chain_calls_schwabdev_option_chains(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that get_options_chain() calls schwabdev.Client.option_chains().

        Verifies the Schwab API is called with correct parameters including
        contractType, includeUnderlyingQuote, and strategy.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        mock_schwabdev_client.option_chains.assert_called_once()
        call_kwargs = mock_schwabdev_client.option_chains.call_args
        assert call_kwargs.kwargs["symbol"] == "SPX"
        assert call_kwargs.kwargs["contractType"] == "ALL"
        assert call_kwargs.kwargs["includeUnderlyingQuote"] is True
        assert call_kwargs.kwargs["strategy"] == "SINGLE"

    def test_get_options_chain_returns_correct_structure(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that get_options_chain() returns properly structured OptionsChainData.

        Verifies underlying price, contract counts, expirations, and strikes
        are all correctly extracted from the Schwab response.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        assert chain.symbol == "SPX"
        assert chain.underlying_price == 5900.00
        assert len(chain.call_contracts) == 3  # 5850, 5900, 5950
        assert len(chain.put_contracts) == 3
        assert len(chain.expirations) == 1  # single expiration date
        assert len(chain.strikes) == 3

    def test_get_options_chain_parses_contract_fields(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that individual contract fields are correctly parsed from Schwab response.

        Verifies greeks, pricing, volume, and OI for a specific contract.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        # Find the ATM call (5900 strike)
        atm_call = next(c for c in chain.call_contracts if c.strike_price == 5900.0)
        assert atm_call.symbol == "SPXW  260403C05900000"
        assert atm_call.option_type == "CALL"
        assert atm_call.delta == 0.50
        assert atm_call.gamma == 0.0068
        assert atm_call.theta == -3.50
        assert atm_call.vega == 5.80
        assert atm_call.open_interest == 12000
        assert atm_call.volume == 5200
        assert atm_call.implied_volatility == 15.80

    def test_get_options_chain_caches_per_dte_range(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that second call for same DTE range returns cached data.

        schwabdev.Client.option_chains() should only be called once
        because the second call hits the cache.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain1 = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)
        chain2 = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        mock_schwabdev_client.option_chains.assert_called_once()
        assert len(chain1.call_contracts) == len(chain2.call_contracts)

    def test_get_options_chain_filters_by_min_open_interest(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that min_open_interest filters out low-OI contracts.

        Only contracts with OI >= threshold should be included.
        The fixture has OI values: 8500, 12000, 15000 for calls.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain(
            "SPX", from_dte=0, to_dte=7, min_open_interest=10000
        )

        # Only 5900 (12000 OI) and 5950 (15000 OI) calls should pass
        assert len(chain.call_contracts) == 2
        assert all(c.open_interest >= 10000 for c in chain.call_contracts)

    def test_get_options_chain_filters_by_min_volume(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that min_volume filters out low-volume contracts.

        Only contracts with volume >= threshold should be included.
        The fixture has volume values: 2500, 5200, 3800 for calls.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7, min_volume=4000)

        # Only 5900 (5200 vol) call should pass
        assert len(chain.call_contracts) == 1
        assert chain.call_contracts[0].volume >= 4000

    def test_get_options_chain_deduplicates_across_ranges(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that contracts appearing in overlapping DTE ranges are deduplicated.

        When the same contract symbol appears in multiple range fetches,
        it should only appear once in the result.
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        # Fetch all ranges (None, None) — chain response will be reused for each
        chain = schwab_client.get_options_chain("SPX")

        # Despite multiple range fetches, each contract should appear exactly once
        call_symbols = [c.symbol for c in chain.call_contracts]
        assert len(call_symbols) == len(set(call_symbols))

    def test_get_options_chain_handles_api_failure_gracefully(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """Test that API errors for one DTE range don't crash the entire fetch.

        If one range fails, the chain should still return data from successful ranges.
        Returns empty chain if all ranges fail.
        """
        mock_schwabdev_client.option_chains.side_effect = Exception("API error")

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        assert chain.symbol == "SPX"
        assert len(chain.call_contracts) == 0
        assert len(chain.put_contracts) == 0

    def test_get_options_chain_returns_sorted_strikes(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that the strikes list is sorted ascending.

        Sorted strikes are needed for level extraction in Phase 2 (GEX).
        """
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        assert chain.strikes == sorted(chain.strikes)

    def test_get_options_chain_returns_sorted_expirations(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
        spx_chain_response: dict,
    ) -> None:
        """Test that the expirations list is sorted chronologically."""
        mock_schwabdev_client.option_chains.return_value = _make_mock_response(spx_chain_response)

        chain = schwab_client.get_options_chain("SPX", from_dte=0, to_dte=7)

        assert chain.expirations == sorted(chain.expirations)


# ── DTE Range Logic ────────────────────────────────────────────────


class TestDteRangeLogic:
    """Tests for the internal DTE range selection logic."""

    @pytest.mark.parametrize(
        "from_dte,to_dte,expected_range_count",
        [
            (0, 7, 1),  # single near-term range
            (0, 45, 2),  # near-term + mid-term
            (0, 180, 3),  # near-term + mid-term + medium-term
            (0, 365, 4),  # near through long-term
            (None, None, 5),  # all ranges (full chain)
            (366, 9999, 1),  # LEAPs only
        ],
        ids=[
            "near-term-only",
            "near-and-mid",
            "up-to-180dte",
            "up-to-365dte",
            "all-ranges",
            "leaps-only",
        ],
    )
    def test_dte_range_selection(
        self,
        schwab_client: SchwabClient,
        from_dte: int | None,
        to_dte: int | None,
        expected_range_count: int,
    ) -> None:
        """Test that _get_dte_ranges returns the correct number of range buckets.

        The multi-range strategy splits the full chain into 5 DTE buckets,
        each with its own cache TTL. This test verifies the correct buckets
        are selected based on the requested DTE range.
        """
        ranges = schwab_client._get_dte_ranges(from_dte, to_dte)
        assert len(ranges) == expected_range_count
