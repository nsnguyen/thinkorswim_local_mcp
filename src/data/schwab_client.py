"""Schwab API client wrapper with multi-range DTE fetching and caching."""

from datetime import UTC, date, datetime, timedelta

import schwabdev

from src.data.cache import DTE_RANGE_TTLS, CacheManager
from src.data.models import (
    ExpirationDate,
    Instrument,
    MarketHours,
    MarketMover,
    OptionContract,
    OptionsChainData,
    PriceCandle,
    PriceHistory,
    Quote,
)
from src.data.token_manager import TokenManager
from src.shared.logging import get_logger
from src.shared.requests import call_schwab_api

logger = get_logger(__name__)


class SchwabClientError(Exception):
    """Raised when a Schwab API call fails."""


class SchwabClient:
    """Wraps schwabdev.Client with caching and typed responses.

    Key features:
    - Multi-range DTE fetching for options chains
    - Per-DTE-range cache TTLs
    - Returns Pydantic models
    """

    def __init__(
        self,
        token_manager: TokenManager,
        cache: CacheManager,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._token_manager = token_manager
        self._cache = cache
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    def _client(self) -> schwabdev.Client:
        """Get the underlying schwabdev.Client from the token manager."""
        return self._token_manager.get_client()

    def _api_call(self, method_name: str, *args: object, **kwargs: object) -> dict:
        """Make a Schwab API call through the shared request layer."""
        return call_schwab_api(
            self._client(),
            method_name,
            *args,
            max_retries=self._max_retries,
            base_delay=self._retry_base_delay,
            **kwargs,
        )

    # ── Quotes ──────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote:
        """Fetch a real-time quote for any symbol (equity, index, futures)."""
        cached = self._cache.get_quote(symbol)
        if cached is not None:
            return Quote.model_validate(cached)

        try:
            data = self._api_call("quote", symbol)
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch quote for {symbol}: {e}") from e

        if symbol not in data:
            raise SchwabClientError(
                f"No quote data returned for {symbol}. Available keys: {list(data.keys())}"
            )

        raw = data[symbol]
        quote_data = raw.get("quote", raw)

        quote = Quote(
            symbol=symbol,
            last=quote_data.get("lastPrice", 0.0),
            bid=quote_data.get("bidPrice", 0.0),
            ask=quote_data.get("askPrice", 0.0),
            open=quote_data.get("openPrice", 0.0),
            high=quote_data.get("highPrice", 0.0),
            low=quote_data.get("lowPrice", 0.0),
            close=quote_data.get("closePrice", 0.0),
            volume=int(quote_data.get("totalVolume", 0)),
            net_change=quote_data.get("netChange", 0.0),
            net_change_pct=quote_data.get("netPercentChange", 0.0),
            is_delayed=quote_data.get("isDelayed", raw.get("realtime", True) is False),
            timestamp=datetime.now(UTC),
        )

        self._cache.set_quote(symbol, quote.model_dump(mode="json"))
        return quote

    # ── Options Chain ───────────────────────────────────────────────

    def get_options_chain(
        self,
        symbol: str,
        contract_type: str = "ALL",
        from_dte: int | None = None,
        to_dte: int | None = None,
        min_open_interest: int = 0,
        min_volume: int = 0,
    ) -> OptionsChainData:
        """Fetch full options chain with multi-range DTE caching.

        If from_dte/to_dte are specified, only fetches the relevant DTE ranges.
        Otherwise fetches all ranges (full chain including LEAPs).
        """
        today = date.today()

        # Determine which DTE ranges to fetch
        ranges_to_fetch = self._get_dte_ranges(from_dte, to_dte)

        all_calls: list[OptionContract] = []
        all_puts: list[OptionContract] = []
        underlying_price = 0.0
        is_delayed = False
        seen_symbols: set[str] = set()

        for range_min, range_max, _ in ranges_to_fetch:
            # Check cache first
            cached = self._cache.get_chain(symbol, range_min, range_max)
            if cached is not None:
                range_data = cached
            else:
                range_data = self._fetch_chain_range(
                    symbol, contract_type, today, range_min, range_max
                )
                if range_data is not None:
                    self._cache.set_chain(symbol, range_min, range_max, range_data)

            if range_data is None:
                continue

            # Extract underlying price from first successful response
            if underlying_price == 0.0:
                underlying_price = range_data.get("underlyingPrice", 0.0)
                if underlying_price == 0.0:
                    underlying = range_data.get("underlying", {})
                    underlying_price = underlying.get("last", 0.0)

            is_delayed = is_delayed or range_data.get("isDelayed", False)

            # Parse contracts, deduplicating across ranges
            calls, puts = self._parse_contracts(
                range_data, symbol, seen_symbols, min_open_interest, min_volume
            )
            all_calls.extend(calls)
            all_puts.extend(puts)

        # Build sorted unique expirations and strikes
        all_contracts = all_calls + all_puts
        expirations = sorted({c.expiration_date for c in all_contracts})
        strikes = sorted({c.strike_price for c in all_contracts})

        return OptionsChainData(
            symbol=symbol,
            underlying_price=underlying_price,
            timestamp=datetime.now(UTC),
            call_contracts=all_calls,
            put_contracts=all_puts,
            expirations=expirations,
            strikes=strikes,
            is_delayed=is_delayed,
        )

    def _get_dte_ranges(
        self, from_dte: int | None, to_dte: int | None
    ) -> list[tuple[int, int, int]]:
        """Determine which DTE range buckets to fetch."""
        if from_dte is None and to_dte is None:
            return list(DTE_RANGE_TTLS)

        f = from_dte or 0
        t = to_dte or 9999

        return [(rmin, rmax, ttl) for rmin, rmax, ttl in DTE_RANGE_TTLS if rmax >= f and rmin <= t]

    def _fetch_chain_range(
        self,
        symbol: str,
        contract_type: str,
        today: date,
        from_dte: int,
        to_dte: int,
    ) -> dict | None:
        """Fetch a single DTE range from the Schwab API."""
        from_date = today + timedelta(days=from_dte)
        to_date = today + timedelta(days=min(to_dte, 3650))  # cap at 10 years

        try:
            data = self._api_call(
                "option_chains",
                symbol=symbol,
                contractType=contract_type,
                includeUnderlyingQuote=True,
                strategy="SINGLE",
                fromDate=from_date.isoformat(),
                toDate=to_date.isoformat(),
            )
        except Exception as e:
            logger.warning(
                "Failed to fetch chain for %s (DTE %d-%d): %s",
                symbol,
                from_dte,
                to_dte,
                e,
            )
            return None

        status = data.get("status")
        if status and status != "SUCCESS":
            logger.warning("Chain fetch status for %s: %s", symbol, status)
            return None

        return data

    def _parse_contracts(
        self,
        data: dict,
        underlying_symbol: str,
        seen_symbols: set[str],
        min_open_interest: int,
        min_volume: int,
    ) -> tuple[list[OptionContract], list[OptionContract]]:
        """Parse call and put contracts from a Schwab chain response."""
        calls = self._parse_exp_date_map(
            data.get("callExpDateMap", {}),
            underlying_symbol,
            "CALL",
            seen_symbols,
            min_open_interest,
            min_volume,
        )
        puts = self._parse_exp_date_map(
            data.get("putExpDateMap", {}),
            underlying_symbol,
            "PUT",
            seen_symbols,
            min_open_interest,
            min_volume,
        )
        return calls, puts

    def _parse_exp_date_map(
        self,
        exp_map: dict,
        underlying_symbol: str,
        option_type: str,
        seen_symbols: set[str],
        min_open_interest: int,
        min_volume: int,
    ) -> list[OptionContract]:
        """Parse an expDateMap (callExpDateMap or putExpDateMap) into contracts."""
        contracts: list[OptionContract] = []

        for exp_key, strikes in exp_map.items():
            # exp_key format: "2026-03-28:3" (date:DTE)
            exp_date_str = exp_key.split(":")[0]
            try:
                exp_date = date.fromisoformat(exp_date_str)
            except ValueError:
                logger.warning("Skipping unparseable expiration: %s", exp_key)
                continue

            for strike_str, contract_list in strikes.items():
                for raw in contract_list:
                    sym = raw.get("symbol", "")
                    if sym in seen_symbols:
                        continue  # deduplicate across DTE ranges
                    seen_symbols.add(sym)

                    oi = int(raw.get("openInterest", 0))
                    vol = int(raw.get("totalVolume", 0))

                    if oi < min_open_interest or vol < min_volume:
                        continue

                    contracts.append(
                        OptionContract(
                            symbol=sym,
                            underlying_symbol=underlying_symbol,
                            option_type=option_type,
                            strike_price=float(raw.get("strikePrice", 0.0)),
                            expiration_date=exp_date,
                            days_to_expiration=int(raw.get("daysToExpiration", 0)),
                            bid=float(raw.get("bid", 0.0)),
                            ask=float(raw.get("ask", 0.0)),
                            last=float(raw.get("last", 0.0)),
                            mark=float(raw.get("mark", 0.0)),
                            volume=vol,
                            open_interest=oi,
                            implied_volatility=float(raw.get("volatility", 0.0)),
                            delta=float(raw.get("delta", 0.0)),
                            gamma=float(raw.get("gamma", 0.0)),
                            theta=float(raw.get("theta", 0.0)),
                            vega=float(raw.get("vega", 0.0)),
                            rho=float(raw.get("rho", 0.0)),
                            in_the_money=bool(raw.get("inTheMoney", False)),
                            multiplier=float(raw.get("multiplier", 100.0)),
                        )
                    )

        return contracts

    # ── Price History ────────────────────────────────────────────────

    def get_price_history(
        self,
        symbol: str,
        period_type: str = "day",
        period: int | None = None,
        frequency_type: str = "minute",
        frequency: int = 5,
        extended_hours: bool = False,
    ) -> PriceHistory:
        """Fetch OHLCV price history candles for a symbol."""
        kwargs: dict = {
            "periodType": period_type,
            "frequencyType": frequency_type,
            "frequency": frequency,
            "needExtendedHoursData": extended_hours,
        }
        if period is not None:
            kwargs["period"] = period

        try:
            data = self._api_call("price_history", symbol, **kwargs)
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch price history for {symbol}: {e}") from e

        candles = [
            PriceCandle(
                datetime=_epoch_ms_to_datetime(c["datetime"]),
                open=float(c.get("open", 0.0)),
                high=float(c.get("high", 0.0)),
                low=float(c.get("low", 0.0)),
                close=float(c.get("close", 0.0)),
                volume=int(c.get("volume", 0)),
            )
            for c in data.get("candles", [])
        ]
        return PriceHistory(
            symbol=data.get("symbol", symbol),
            period_type=period_type,
            frequency_type=frequency_type,
            candles=candles,
        )

    # ── Market Movers ────────────────────────────────────────────────

    def get_market_movers(
        self,
        symbol: str,
        sort_by: str | None = None,
        count: int = 10,
    ) -> list[MarketMover]:
        """Fetch top market movers for an index."""
        kwargs: dict = {}
        if sort_by is not None:
            kwargs["sort"] = sort_by

        try:
            data = self._api_call("movers", symbol, **kwargs)
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch movers for {symbol}: {e}") from e

        movers = [
            MarketMover(
                symbol=m.get("symbol", ""),
                description=m.get("description", ""),
                last=float(m.get("lastPrice", 0.0)),
                change=float(m.get("change", 0.0)),
                change_pct=float(m.get("percentChange", 0.0)),
                volume=int(m.get("totalVolume", 0)),
            )
            for m in data.get("screeners", [])
        ]
        return movers[:count]

    # ── Market Hours ─────────────────────────────────────────────────

    def get_market_hours(self, market: str, trade_date: str | None = None) -> MarketHours:
        """Fetch session hours and open/closed status for a market type."""
        try:
            data = self._api_call("market_hours", [market], date=trade_date)
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch market hours for {market}: {e}") from e

        # Response is nested: {market_type: {exchange_key: {...}}}
        market_data = data.get(market, {})
        inner = next(iter(market_data.values()), {}) if market_data else {}
        is_open = bool(inner.get("isOpen", False))

        session = inner.get("sessionHours", {})
        reg = session.get("regularMarket", [{}])
        pre = session.get("preMarket", [{}])
        post = session.get("postMarket", [{}])

        def _first_start(slots: list) -> str | None:
            return slots[0].get("start") if slots else None

        def _first_end(slots: list) -> str | None:
            return slots[0].get("end") if slots else None

        return MarketHours(
            market=market,
            is_open=is_open,
            regular_start=_first_start(reg),
            regular_end=_first_end(reg),
            pre_market_start=_first_start(pre),
            pre_market_end=_first_end(pre),
            post_market_start=_first_start(post),
            post_market_end=_first_end(post),
        )

    # ── Instrument Search ────────────────────────────────────────────

    def search_instruments(
        self, query: str, projection: str = "symbol-search"
    ) -> list[Instrument]:
        """Search for instruments by symbol or description."""
        try:
            data = self._api_call("instruments", query, projection=projection)
        except Exception as e:
            raise SchwabClientError(f"Failed to search instruments for '{query}': {e}") from e

        return [
            Instrument(
                symbol=inst.get("symbol", ""),
                description=inst.get("description", ""),
                exchange=inst.get("exchange", ""),
                asset_type=inst.get("assetType", ""),
                cusip=inst.get("cusip"),
            )
            for inst in data.get("instruments", [])
        ]

    # ── Expiration Dates ─────────────────────────────────────────────

    def get_expiration_dates(self, symbol: str) -> list[ExpirationDate]:
        """Fetch all available option expiration dates for a symbol."""
        _TYPE_MAP = {"W": "weekly", "M": "monthly", "Q": "quarterly", "S": "leap"}

        try:
            data = self._api_call("option_expiration_chain", symbol)
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch expiration dates for {symbol}: {e}") from e

        from datetime import date as _date

        return [
            ExpirationDate(
                expiration_date=_date.fromisoformat(exp.get("expirationDate", "1970-01-01")),
                dte=int(exp.get("daysToExpiration", 0)),
                expiration_type=_TYPE_MAP.get(exp.get("expirationType", "W"), "weekly"),
            )
            for exp in data.get("expirationList", [])
        ]


def _epoch_ms_to_datetime(epoch_ms: int | float) -> "datetime":
    """Convert epoch milliseconds to UTC datetime."""
    from datetime import UTC, datetime
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
