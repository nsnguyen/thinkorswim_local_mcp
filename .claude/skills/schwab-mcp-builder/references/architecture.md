# Schwab Options MCP Server — Architecture Reference

## Design Philosophy

MCP = calculator (data + math, no opinions). Claude = analyst (decisions, interpretation, trading recommendations).

The MCP server never outputs opinions, recommendations, or interpretations. It returns numbers, labels (based on thresholds), and structured data.

## 4-Layer Architecture

```
Layer 1: src/tools/        → MCP tool handlers (Claude-facing interface, orchestrates core)
Layer 2: src/core/         → Pure math & calculations (GEX, IV, trade math — no I/O)
Layer 3: src/data/         → Data access (Schwab client, cache, tokens, Pydantic models)
Layer 4: Schwab REST API   → External data source (120 req/min hard limit)
```

Data flows down (tools → core → data → API), results flow up.

## Directory Structure

```
src/
├── __init__.py
├── __main__.py              # python -m src entry point
├── server.py                # FastMCP server (stdio), loads .env, wires components
├── shared/                  # Cross-cutting utilities (DRY)
│   ├── __init__.py
│   ├── logging.py           # Shared logging configuration
│   ├── retry.py             # Request retry logic
│   └── timing.py            # Performance timing utilities
├── tools/                   # Layer 1 — MCP tool handlers
│   ├── __init__.py
│   ├── market_data.py       # get_quote, get_options_chain
│   ├── gex.py               # get_gex_levels, get_gex_summary, get_0dte_levels
│   ├── volatility.py        # analyze_volatility, get_iv_surface, get_vix_context
│   ├── trade_math.py        # evaluate_trade, check_alerts
│   └── history.py           # get_gex_history, get_iv_history, take_snapshot
├── core/                    # Layer 2 — Pure computation (no I/O, no opinions)
│   ├── __init__.py
│   ├── gex_calculator.py    # Per-strike GEX formula, aggregation
│   ├── gex_levels.py        # Level extraction (walls, zero gamma, HVL)
│   ├── volatility.py        # IV skew, butterfly, term structure
│   ├── iv_context.py        # IV percentile, rank, realized vol
│   ├── vix_context.py       # VIX regime, percentile, term structure
│   ├── trade_math.py        # POP (Black-Scholes), P&L, breakevens
│   └── snapshot_store.py    # Daily Parquet snapshots
└── data/                    # Layer 3 — Data access
    ├── __init__.py
    ├── schwab_client.py     # Schwab API wrapper, multi-range DTE fetch
    ├── cache.py             # diskcache with per-DTE-range TTL
    ├── models.py            # Pydantic v2 data models
    └── token_manager.py     # OAuth 2.0 token lifecycle

tests/                       # Flat test structure
├── conftest.py              # Shared pytest fixtures, mock client factory
├── fixtures/                # Reusable test data
│   ├── spx_chain_response.json      # Real Schwab API response shape
│   ├── spx_quote_response.json      # Real Schwab quote response
│   └── factories.py                 # Python factory functions for Pydantic models
├── test_cache.py
├── test_schwab_client.py
├── test_token_manager.py
├── test_market_data.py
├── test_gex_calculator.py
├── test_gex_levels.py
└── ...

scripts/
├── start.sh                 # Setup (if needed) + start MCP server
└── authenticate.py          # One-time Schwab OAuth login
```

## Tool Wiring Pattern

Tool handlers in `src/tools/` orchestrate core modules directly. No service layer.

```python
# src/tools/gex.py — tool orchestrates core directly
def get_gex_levels(symbol: str, max_dte: int = 45) -> dict:
    chain = schwab_client.get_options_chain(symbol, to_dte=max_dte)
    per_strike = gex_calculator.calculate(chain)
    levels = gex_levels.extract(per_strike, chain.underlying_price)
    return levels.model_dump(mode="json")
```

Tools registered via `register_tools(mcp, dependency)` in each tool module, wired in `src/server.py`.

## Schwab API Constraints

- 120 requests/minute (HTTP 429 on exceed)
- Access token: 30 min (auto-refreshes via schwabdev)
- Refresh token: 7 days (must re-run authenticate.py)
- Open Interest: end-of-day only (always stale intraday)
- No futures options chains via REST
- Chain response: callExpDateMap/putExpDateMap nested by "expiration:DTE" → "strike" → [contracts]

## Caching Strategy

Per-DTE-range TTLs via diskcache:
- 0-7 DTE: 60s
- 8-45 DTE: 120s
- 46-180 DTE: 300s
- 181-365 DTE: 600s
- 366+ DTE: 900s
- Quotes: 15s
