"""Tests for Phase 5 market extras SchwabClient methods.

Verifies: get_price_history, get_market_movers, get_market_hours,
search_instruments, get_expiration_dates call correct schwabdev methods
and return typed Pydantic models.
"""

from unittest.mock import MagicMock

import pytest

from src.data.models import (
    ExpirationDate,
    Instrument,
    MarketHours,
    MarketMover,
    PriceHistory,
)
from src.data.schwab_client import SchwabClient, SchwabClientError

# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock requests.Response with .json() returning given data."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


def _price_history_response() -> dict:
    """Build a realistic Schwab price_history API response."""
    return {
        "candles": [
            {"open": 5880.0, "high": 5920.0, "low": 5870.0, "close": 5905.0,
             "volume": 1200000, "datetime": 1743120000000},
            {"open": 5905.0, "high": 5940.0, "low": 5895.0, "close": 5930.0,
             "volume": 980000, "datetime": 1743206400000},
        ],
        "symbol": "SPX",
        "empty": False,
    }


def _movers_response() -> dict:
    """Build a realistic Schwab movers API response."""
    return {
        "screeners": [
            {
                "symbol": "NVDA", "description": "NVIDIA Corporation",
                "lastPrice": 880.0, "change": 25.0, "percentChange": 2.92,
                "totalVolume": 45000000, "direction": "up",
            },
            {
                "symbol": "TSLA", "description": "Tesla Inc.",
                "lastPrice": 220.0, "change": -8.0, "percentChange": -3.51,
                "totalVolume": 30000000, "direction": "down",
            },
            {
                "symbol": "AAPL", "description": "Apple Inc.",
                "lastPrice": 195.0, "change": 3.5, "percentChange": 1.83,
                "totalVolume": 25000000, "direction": "up",
            },
        ]
    }


def _market_hours_response(is_open: bool = True) -> dict:
    """Build a realistic Schwab market_hours API response."""
    return {
        "option": {
            "EQO": {
                "date": "2026-03-28",
                "marketType": "OPTION",
                "isOpen": is_open,
                "sessionHours": {
                    "regularMarket": [
                        {"start": "2026-03-28T09:30:00-04:00", "end": "2026-03-28T16:00:00-04:00"}
                    ],
                    "preMarket": [
                        {"start": "2026-03-28T07:00:00-04:00", "end": "2026-03-28T09:30:00-04:00"}
                    ],
                    "postMarket": [
                        {"start": "2026-03-28T16:00:00-04:00", "end": "2026-03-28T20:00:00-04:00"}
                    ],
                },
            }
        }
    }


def _instruments_response() -> dict:
    """Build a realistic Schwab instruments API response."""
    return {
        "instruments": [
            {
                "symbol": "SPY", "description": "SPDR S&P 500 ETF Trust",
                "exchange": "PACF", "assetType": "ETF", "cusip": "78462F103",
            },
            {
                "symbol": "SPX", "description": "S&P 500 Index",
                "exchange": "IND", "assetType": "INDEX", "cusip": None,
            },
        ]
    }


def _expiration_chain_response() -> dict:
    """Build a realistic Schwab option_expiration_chain API response."""
    return {
        "expirationList": [
            {"expirationDate": "2026-03-28", "daysToExpiration": 0, "expirationType": "W"},
            {"expirationDate": "2026-04-04", "daysToExpiration": 7, "expirationType": "W"},
            {"expirationDate": "2026-04-17", "daysToExpiration": 20, "expirationType": "M"},
            {"expirationDate": "2026-06-19", "daysToExpiration": 83, "expirationType": "Q"},
        ]
    }


# ── get_price_history ──────────────────────────────────────────────


class TestGetPriceHistory:
    """Tests for SchwabClient.get_price_history()."""

    def test_calls_schwabdev_price_history(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_price_history must call schwabdev Client.price_history with correct params.

        Ensures the API method name and required positional arg are correct.
        """
        resp = _make_mock_response(_price_history_response())
        mock_schwabdev_client.price_history.return_value = resp

        schwab_client.get_price_history("SPX")

        mock_schwabdev_client.price_history.assert_called_once()
        call_args = mock_schwabdev_client.price_history.call_args
        assert call_args[0][0] == "SPX"  # first positional arg is symbol

    def test_returns_price_history_model(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_price_history must return a PriceHistory model with candles.

        Verifies the response is correctly parsed into typed Pydantic models.
        """
        resp = _make_mock_response(_price_history_response())
        mock_schwabdev_client.price_history.return_value = resp

        result = schwab_client.get_price_history("SPX")

        assert isinstance(result, PriceHistory)
        assert result.symbol == "SPX"
        assert len(result.candles) == 2
        assert result.candles[0].open == 5880.0
        assert result.candles[0].high == 5920.0
        assert result.candles[0].low == 5870.0
        assert result.candles[0].close == 5905.0
        assert result.candles[0].volume == 1200000

    def test_passes_period_params(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_price_history must pass period and frequency params to schwabdev.

        Ensures custom period/frequency settings are forwarded to the API.
        """
        resp = _make_mock_response(_price_history_response())
        mock_schwabdev_client.price_history.return_value = resp

        schwab_client.get_price_history(
            "AAPL",
            period_type="month",
            period=3,
            frequency_type="daily",
            frequency=1,
        )

        call_kwargs = mock_schwabdev_client.price_history.call_args[1]
        assert call_kwargs["periodType"] == "month"
        assert call_kwargs["period"] == 3
        assert call_kwargs["frequencyType"] == "daily"
        assert call_kwargs["frequency"] == 1

    def test_empty_candles(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_price_history must handle empty candle list gracefully.

        Some symbols or date ranges may return no candle data.
        """
        mock_schwabdev_client.price_history.return_value = _make_mock_response(
            {"candles": [], "symbol": "UNKNOWN", "empty": True}
        )

        result = schwab_client.get_price_history("UNKNOWN")

        assert result.symbol == "UNKNOWN"
        assert result.candles == []

    def test_api_error_raises_schwab_client_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_price_history must raise SchwabClientError on API failure.

        Verifies error wrapping is consistent with other client methods.
        """
        mock_schwabdev_client.price_history.side_effect = Exception("network error")

        with pytest.raises(SchwabClientError, match="SPX"):
            schwab_client.get_price_history("SPX")


# ── get_market_movers ──────────────────────────────────────────────


class TestGetMarketMovers:
    """Tests for SchwabClient.get_market_movers()."""

    def test_calls_schwabdev_movers(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_movers must call schwabdev Client.movers with the index symbol.

        Verifies the API method and positional argument are correct.
        """
        mock_schwabdev_client.movers.return_value = _make_mock_response(_movers_response())

        schwab_client.get_market_movers("$SPX")

        mock_schwabdev_client.movers.assert_called_once()
        call_args = mock_schwabdev_client.movers.call_args
        assert call_args[0][0] == "$SPX"

    def test_returns_mover_list(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_movers must return a list of MarketMover models.

        Verifies each mover has the expected fields from the screeners response.
        """
        mock_schwabdev_client.movers.return_value = _make_mock_response(_movers_response())

        result = schwab_client.get_market_movers("$SPX")

        assert isinstance(result, list)
        assert len(result) == 3
        assert isinstance(result[0], MarketMover)
        assert result[0].symbol == "NVDA"
        assert result[0].description == "NVIDIA Corporation"
        assert result[0].last == 880.0
        assert result[0].change == 25.0
        assert result[0].change_pct == 2.92
        assert result[0].volume == 45000000

    def test_count_limits_results(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_movers must apply count limit after fetching.

        Since schwabdev.movers doesn't have a count param, we slice on our end.
        """
        mock_schwabdev_client.movers.return_value = _make_mock_response(_movers_response())

        result = schwab_client.get_market_movers("$SPX", count=2)

        assert len(result) == 2
        assert result[0].symbol == "NVDA"
        assert result[1].symbol == "TSLA"

    def test_passes_sort_param(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_movers must pass sort_by to schwabdev as 'sort'.

        Verifies the parameter name mapping between our API and schwabdev's API.
        """
        mock_schwabdev_client.movers.return_value = _make_mock_response(_movers_response())

        schwab_client.get_market_movers("$SPX", sort_by="VOLUME")

        call_kwargs = mock_schwabdev_client.movers.call_args[1]
        assert call_kwargs.get("sort") == "VOLUME"

    def test_api_error_raises_schwab_client_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_movers must raise SchwabClientError on API failure."""
        mock_schwabdev_client.movers.side_effect = Exception("timeout")

        with pytest.raises(SchwabClientError, match="\\$SPX"):
            schwab_client.get_market_movers("$SPX")


# ── get_market_hours ──────────────────────────────────────────────


class TestGetMarketHours:
    """Tests for SchwabClient.get_market_hours()."""

    def test_calls_schwabdev_market_hours(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_hours must call schwabdev Client.market_hours with market list.

        Verifies the market type is wrapped in a list for the API call.
        """
        mock_schwabdev_client.market_hours.return_value = _make_mock_response(
            _market_hours_response()
        )

        schwab_client.get_market_hours("option")

        mock_schwabdev_client.market_hours.assert_called_once()
        call_args = mock_schwabdev_client.market_hours.call_args
        assert "option" in call_args[0][0]  # first arg is list of markets

    def test_returns_market_hours_model(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_hours must return a MarketHours model with session times.

        Verifies all session fields are extracted from the nested response structure.
        """
        mock_schwabdev_client.market_hours.return_value = _make_mock_response(
            _market_hours_response(is_open=True)
        )

        result = schwab_client.get_market_hours("option")

        assert isinstance(result, MarketHours)
        assert result.market == "option"
        assert result.is_open is True
        assert result.regular_start is not None
        assert result.regular_end is not None

    def test_market_closed(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_hours must return is_open=False for closed markets.

        Weekends and holidays return isOpen: false without session hours.
        """
        mock_schwabdev_client.market_hours.return_value = _make_mock_response(
            _market_hours_response(is_open=False)
        )

        result = schwab_client.get_market_hours("option")

        assert result.is_open is False

    def test_api_error_raises_schwab_client_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_market_hours must raise SchwabClientError on API failure."""
        mock_schwabdev_client.market_hours.side_effect = Exception("server error")

        with pytest.raises(SchwabClientError, match="option"):
            schwab_client.get_market_hours("option")


# ── search_instruments ────────────────────────────────────────────


class TestSearchInstruments:
    """Tests for SchwabClient.search_instruments()."""

    def test_calls_schwabdev_instruments(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """search_instruments must call schwabdev Client.instruments with query and projection.

        Verifies both required args are passed correctly.
        """
        mock_schwabdev_client.instruments.return_value = _make_mock_response(
            _instruments_response()
        )

        schwab_client.search_instruments("SPY")

        mock_schwabdev_client.instruments.assert_called_once()
        call_args = mock_schwabdev_client.instruments.call_args
        assert "SPY" in str(call_args)

    def test_returns_instrument_list(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """search_instruments must return a list of Instrument models.

        Verifies each instrument has symbol, description, exchange, and asset_type.
        """
        mock_schwabdev_client.instruments.return_value = _make_mock_response(
            _instruments_response()
        )

        result = schwab_client.search_instruments("SPY")

        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], Instrument)
        assert result[0].symbol == "SPY"
        assert result[0].description == "SPDR S&P 500 ETF Trust"
        assert result[0].exchange == "PACF"
        assert result[0].asset_type == "ETF"

    def test_empty_results(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """search_instruments must handle empty result list gracefully.

        Returns empty list without error when no instruments match the query.
        """
        mock_schwabdev_client.instruments.return_value = _make_mock_response(
            {"instruments": []}
        )

        result = schwab_client.search_instruments("ZZZZUNKNOWN")

        assert result == []

    def test_api_error_raises_schwab_client_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """search_instruments must raise SchwabClientError on API failure."""
        mock_schwabdev_client.instruments.side_effect = Exception("not found")

        with pytest.raises(SchwabClientError, match="SPY"):
            schwab_client.search_instruments("SPY")


# ── get_expiration_dates ──────────────────────────────────────────


class TestGetExpirationDates:
    """Tests for SchwabClient.get_expiration_dates()."""

    def test_calls_schwabdev_option_expiration_chain(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_expiration_dates must call schwabdev Client.option_expiration_chain.

        Verifies the correct API method is used (not option_chains which is heavier).
        """
        mock_schwabdev_client.option_expiration_chain.return_value = _make_mock_response(
            _expiration_chain_response()
        )

        schwab_client.get_expiration_dates("SPX")

        mock_schwabdev_client.option_expiration_chain.assert_called_once_with("SPX")

    def test_returns_expiration_list(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_expiration_dates must return a list of ExpirationDate models.

        Verifies all expirations are parsed with correct date and DTE.
        """
        mock_schwabdev_client.option_expiration_chain.return_value = _make_mock_response(
            _expiration_chain_response()
        )

        result = schwab_client.get_expiration_dates("SPX")

        assert isinstance(result, list)
        assert len(result) == 4
        assert isinstance(result[0], ExpirationDate)
        assert result[0].dte == 0  # 0DTE
        assert result[1].dte == 7

    def test_classifies_expiration_types(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_expiration_dates must map Schwab expirationType codes to readable labels.

        W=weekly, M=monthly, Q=quarterly should map to descriptive strings.
        """
        mock_schwabdev_client.option_expiration_chain.return_value = _make_mock_response(
            _expiration_chain_response()
        )

        result = schwab_client.get_expiration_dates("SPX")

        types = [e.expiration_type for e in result]
        assert "weekly" in types
        assert "monthly" in types
        assert "quarterly" in types

    def test_api_error_raises_schwab_client_error(
        self,
        schwab_client: SchwabClient,
        mock_schwabdev_client: MagicMock,
    ) -> None:
        """get_expiration_dates must raise SchwabClientError on API failure."""
        mock_schwabdev_client.option_expiration_chain.side_effect = Exception("API error")

        with pytest.raises(SchwabClientError, match="SPX"):
            schwab_client.get_expiration_dates("SPX")
