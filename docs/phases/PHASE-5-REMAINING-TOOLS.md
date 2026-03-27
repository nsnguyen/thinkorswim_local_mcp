# Phase 5 — Remaining Market Data Tools, Prompts & Polish

**Goal:** Complete all market data tools, add MCP prompts for common workflows, harden error handling, add futures support.

**Depends on:** Phases 1-4

## Deliverables

1. Remaining market data tools (price history, movers, hours, instruments, expirations)
2. MCP prompts for common workflows
3. Futures quote support
4. Error handling and edge cases
5. Tests

## Remaining Market Data Tools

### `get_price_history`
- Input: `symbol`, `period_type`, `period`, `frequency_type`, `frequency`, `extended_hours`
- Returns: OHLCV candles
- Note: equities/ETFs only — no futures historical bars via REST

### `get_futures_quote`
- Input: `symbol` (e.g., "/ES", "/NQ", "/CL", "/GC")
- Same as `get_quote` but documented separately for discoverability
- Claude uses this for overnight /ES moves, correlation analysis

### `get_market_movers`
- Input: `index`, `sort_by`, `count`
- Returns: top movers with price, change, volume

### `get_market_hours`
- Input: `market`, `date`
- Returns: is_open, session hours
- Useful for Claude to know if market is open before fetching live data

### `search_instruments`
- Input: `query`, `projection`
- Returns: matching symbols with description, exchange, asset type

### `get_expiration_dates`
- Input: `symbol`
- Returns: all available expirations with DTE and type (weekly/monthly)
- Lightweight — doesn't fetch full chain

## MCP Prompts

Prompts are reusable workflows that structure how Claude uses multiple tools together.

### `morning_briefing`
Guides Claude through pre-market analysis:
1. Check market hours
2. Get /ES futures quote (overnight move)
3. Get VIX context
4. Get GEX levels for SPX
5. Analyze volatility
6. Get expected move for nearest weekly

Claude synthesizes all this into a morning briefing.

### `iron_condor_scan`
Guides Claude through finding iron condor candidates:
1. Get GEX levels (identify walls and regime)
2. Get expected move (set outer bounds)
3. Analyze volatility (assess if selling is favorable)
4. Get options chain (filtered to target DTE)
5. Claude selects strikes based on all the above
6. Evaluate trade (verify the math)

### `regime_check`
Quick regime assessment:
1. Get GEX levels
2. Get VIX context
3. Claude interprets: +GEX or -GEX? Trending or mean-reverting?

### `intraday_levels`
0DTE-focused for intraday trading:
1. Get 0DTE levels
2. Estimate charm shift (how levels move by EOD)
3. Get expected move for 0DTE
4. Claude identifies key levels for the rest of the session

## Error Handling

### Schwab API Errors
- **401 Unauthorized:** Auto-refresh token, retry once. If still fails, surface "re-auth required" message.
- **429 Rate Limited:** Wait 60s, retry. Log warning.
- **500 Server Error:** Retry with backoff (1s, 2s, 4s). Max 3 retries.
- **Network timeout:** 10s timeout, retry once.

### Data Edge Cases
- **Market closed:** Return last cached data with `is_stale: true` flag
- **No 0DTE expiration:** Return empty result (not an error — some days have no 0DTE)
- **Symbol not found:** Return clear error with suggestion to use `search_instruments`
- **No open interest (pre-market):** OI is EOD-only. Use cached OI from previous day, flag as stale.
- **Missing greeks:** Some deep OTM options may have zero gamma. Filter from GEX calc (they contribute nothing).

### MCP Protocol Errors
- Tool input validation via Pydantic — return clear error messages
- Never crash the server — catch exceptions, return error response

## Tests

### Unit Tests
- GEX formula correctness
- Zero gamma interpolation
- POP calculation against known values
- Strategy auto-detection
- IV skew calculation
- Alert condition evaluation

### Integration Tests (mock mode)
- Full tool round-trip with mock Schwab responses
- Cache hit/miss behavior
- Token refresh flow
- Alert state persistence

## Definition of Done

- [ ] All 20 MCP tools working
- [ ] All 4 MCP resources working
- [ ] All 4 MCP prompts defined
- [ ] `get_price_history` returns candles
- [ ] `get_futures_quote("/ES")` returns futures quote
- [ ] `get_market_movers("$SPX")` returns movers
- [ ] `get_market_hours("option")` returns hours
- [ ] Error handling for all Schwab API error codes
- [ ] Graceful handling of market-closed scenarios
- [ ] Unit test coverage for core calculations
- [ ] Integration test with mock Schwab responses
- [ ] README with setup instructions
