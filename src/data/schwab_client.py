"""Schwab API client wrapper with multi-range DTE fetching and caching."""

import logging
from datetime import date, datetime, timedelta, timezone

from src.data.cache import CacheManager, DTE_RANGE_TTLS, QUOTE_CACHE_TTL
from src.data.models import OptionContract, OptionsChainData, Quote
from src.data.token_manager import TokenManager

logger = logging.getLogger(__name__)


class SchwabClientError(Exception):
    """Raised when a Schwab API call fails."""


class SchwabClient:
    """Wraps schwabdev.Client with caching and typed responses.

    Key features:
    - Multi-range DTE fetching for options chains
    - Per-DTE-range cache TTLs
    - Returns Pydantic models
    """

    def __init__(self, token_manager: TokenManager, cache: CacheManager):
        self._token_manager = token_manager
        self._cache = cache

    def _client(self):
        return self._token_manager.get_client()

    # ── Quotes ──────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote:
        """Fetch a real-time quote for any symbol (equity, index, futures)."""
        cached = self._cache.get_quote(symbol)
        if cached is not None:
            return Quote.model_validate(cached)

        try:
            resp = self._client().quote(symbol)
            data = resp.json()
        except Exception as e:
            raise SchwabClientError(f"Failed to fetch quote for {symbol}: {e}") from e

        if symbol not in data:
            raise SchwabClientError(
                f"No quote data returned for {symbol}. "
                f"Available keys: {list(data.keys())}"
            )

        raw = data[symbol]
        quote_data = raw.get("quote", raw)
        ref_data = raw.get("reference", {})

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
            timestamp=datetime.now(timezone.utc),
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
                range_data, symbol, seen_symbols,
                min_open_interest, min_volume
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
            timestamp=datetime.now(timezone.utc),
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

        return [
            (rmin, rmax, ttl)
            for rmin, rmax, ttl in DTE_RANGE_TTLS
            if rmax >= f and rmin <= t
        ]

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
            resp = self._client().option_chains(
                symbol=symbol,
                contractType=contract_type,
                includeUnderlyingQuote=True,
                strategy="SINGLE",
                fromDate=from_date.isoformat(),
                toDate=to_date.isoformat(),
            )
            data = resp.json()
        except Exception as e:
            logger.warning(
                "Failed to fetch chain for %s (DTE %d-%d): %s",
                symbol, from_dte, to_dte, e,
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
