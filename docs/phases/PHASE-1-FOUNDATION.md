# Phase 1 — Foundation

**Goal:** Minimal working MCP server that Claude can connect to and fetch live market data.

## Deliverables

1. Project scaffolding (pyproject.toml, deps, directory structure)
2. OAuth 2.0 token manager using `schwabdev`
3. Schwab client wrapper with disk cache (per-DTE-range TTL)
4. Pydantic data models (OptionContract, OptionsChainData, Quote)
5. MCP server entry point (stdio transport)
6. Two working tools: `get_quote`, `get_options_chain`
7. Claude Desktop integration config

## Files to Create

```
src/
├── __init__.py
├── server.py                    # MCP server, tool registration, stdio
│
├── tools/
│   ├── __init__.py
│   └── market_data.py           # get_quote, get_options_chain
│
├── data/
│   ├── __init__.py
│   ├── schwab_client.py         # schwabdev wrapper, multi-range fetch
│   ├── cache.py                 # diskcache with per-DTE-range TTL
│   ├── models.py                # Pydantic v2 data models
│   └── token_manager.py         # OAuth 2.0 token lifecycle

pyproject.toml
requirements.txt
.env.example
```

## Implementation Details

### server.py
- Use `mcp` Python SDK with stdio transport
- Register tools from `tools/` modules
- Load config from `.env`
- Initialize Schwab client on startup

### data/token_manager.py
- Wrap `schwabdev` token handling
- Store tokens at configurable path (`TOKEN_PATH`)
- Auto-refresh access tokens (30 min lifetime)
- Detect expired refresh tokens (7 day lifetime) and prompt re-auth

### data/schwab_client.py
- Wrap `schwabdev.Client`
- Multi-range DTE fetching for options chains:
  - 0-7 DTE → 60s cache TTL
  - 8-45 DTE → 120s cache TTL
  - 46-180 DTE → 300s cache TTL
  - 181-365 DTE → 600s cache TTL
  - 366+ DTE → 900s cache TTL
- Merge + deduplicate contracts across ranges
- Return typed Pydantic models

### data/models.py
Port from `gex-tool-thinkorswim/src/data/data_models.py`, convert to Pydantic v2:

```python
class OptionContract(BaseModel):
    symbol: str
    underlying_symbol: str
    option_type: str              # "CALL" | "PUT"
    strike_price: float
    expiration_date: date
    days_to_expiration: int
    bid: float
    ask: float
    last: float
    mark: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    in_the_money: bool
    multiplier: float = 100.0

class OptionsChainData(BaseModel):
    symbol: str
    underlying_price: float
    timestamp: datetime
    call_contracts: list[OptionContract]
    put_contracts: list[OptionContract]
    expirations: list[date]
    strikes: list[float]
    is_delayed: bool

class Quote(BaseModel):
    symbol: str
    last: float
    bid: float
    ask: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    net_change: float
    net_change_pct: float
    is_delayed: bool
    timestamp: datetime
```

### tools/market_data.py — `get_quote`
- Input: `symbol: str`
- Calls `schwab_client.get_quote(symbol)`
- Returns Quote model as JSON

### tools/market_data.py — `get_options_chain`
- Input: `symbol`, `contract_type`, `from_dte`, `to_dte`, `min_open_interest`, `min_volume`
- Calls `schwab_client.get_options_chain(...)` with multi-range caching
- Returns OptionsChainData as JSON

## Definition of Done

- [ ] `python -m src.server` starts without error
- [ ] Claude Desktop connects via MCP config
- [ ] `get_quote("SPX")` returns live quote
- [ ] `get_quote("/ES")` returns futures quote
- [ ] `get_quote("$VIX")` returns VIX quote
- [ ] `get_options_chain("SPX")` returns full chain with greeks
- [ ] Cache prevents duplicate API calls within TTL
- [ ] Token auto-refresh works (no manual intervention for 7 days)

## Dependencies

```
mcp>=1.0.0
schwabdev>=3.0.0
pydantic>=2.0
diskcache>=5.6
python-dotenv>=1.0
httpx>=0.24
```
