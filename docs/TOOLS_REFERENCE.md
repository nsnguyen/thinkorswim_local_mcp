# MCP Tools — Detailed Specification

## Design Philosophy

**The MCP is a data pipeline + calculator. Claude is the brain.**

The MCP server provides raw market data, computed metrics (GEX, IV, greeks), and pure math (P&L, POP, breakevens). It never makes trading decisions, recommendations, or interpretations. Claude uses its intelligence to analyze the data and advise the user.

## Tool Design Principles

1. **Return structured data** — JSON objects that Claude can reason about
2. **Sensible defaults** — Every tool works with minimal parameters
3. **Data + math only** — No opinions, rankings, or recommendations in tool output
4. **Cacheable** — Tools leverage the cache layer; repeated calls are fast
5. **Composable** — Tools can be chained: get_gex_levels → get_options_chain → evaluate_trade

---

## Market Data Tools

### `get_quote`

Get real-time quote for any symbol.

```python
# Parameters
symbol: str          # e.g., "SPX", "AAPL", "$VIX", "/ES"

# Returns
{
    "symbol": "SPX",
    "last": 5250.50,
    "bid": 5250.00,
    "ask": 5251.00,
    "open": 5235.00,
    "high": 5268.00,
    "low": 5228.00,
    "close": 5242.00,      # Previous close
    "volume": 1250000,
    "net_change": 8.50,
    "net_change_pct": 0.16,
    "is_delayed": false,
    "timestamp": "2025-03-26T14:30:00Z"
}
```

---

### `get_options_chain`

Fetch full options chain with greeks, OI, volume.

```python
# Parameters
symbol: str                  # Required — e.g., "SPX"
contract_type: str = "ALL"   # "CALL", "PUT", "ALL"
from_dte: int = 0            # Min days to expiration
to_dte: int = 45             # Max days to expiration
strike_count: int | None     # Number of strikes above/below ATM (None = all)
include_weekly: bool = True  # Include weekly expirations
min_open_interest: int = 0   # Filter low-OI strikes
min_volume: int = 0          # Filter low-volume strikes

# Returns
{
    "symbol": "SPX",
    "underlying_price": 5250.50,
    "total_contracts": 12450,
    "expirations": ["2025-03-26", "2025-03-28", ...],
    "contracts": [
        {
            "symbol": "SPXW  250328C05200000",
            "type": "CALL",
            "strike": 5200.0,
            "expiration": "2025-03-28",
            "dte": 2,
            "bid": 52.30,
            "ask": 53.10,
            "mark": 52.70,
            "last": 52.50,
            "volume": 1250,
            "open_interest": 3200,
            "implied_volatility": 14.5,
            "delta": 0.62,
            "gamma": 0.0089,
            "theta": -2.35,
            "vega": 1.82,
            "rho": 0.15,
            "in_the_money": true
        },
        ...
    ]
}
```

---

### `get_price_history`

Fetch OHLCV candle data.

```python
# Parameters
symbol: str                    # Required
period_type: str = "day"       # "day", "month", "year", "ytd"
period: int = 10               # Lookback period
frequency_type: str = "daily"  # "minute", "daily", "weekly", "monthly"
frequency: int = 1             # 1, 5, 10, 15, 30 (for minute)
extended_hours: bool = True

# Returns
{
    "symbol": "SPX",
    "candles": [
        {
            "datetime": "2025-03-25T00:00:00Z",
            "open": 5235.0,
            "high": 5260.0,
            "low": 5220.0,
            "close": 5242.0,
            "volume": 3500000
        },
        ...
    ]
}
```

---

### `get_futures_quote`

Get quote for a futures contract.

```python
# Parameters
symbol: str   # e.g., "/ES", "/NQ", "/CL", "/GC", "/ZB"

# Returns — same structure as get_quote, plus:
{
    "symbol": "/ES",
    "last": 5255.25,
    "bid": 5255.00,
    "ask": 5255.50,
    "open_interest": 2100000,
    "settlement_price": 5248.00,
    ...
}
```

---

### `get_market_movers`

Top movers by volume, trades, or % change.

```python
# Parameters
index: str = "$SPX"                    # "$DJI", "$COMPX", "$SPX", "NASDAQ"
sort_by: str = "PERCENT_CHANGE_UP"     # "VOLUME", "TRADES", "PERCENT_CHANGE_DOWN"
count: int = 10

# Returns
{
    "index": "$SPX",
    "movers": [
        {"symbol": "NVDA", "last": 950.0, "change": 45.0, "change_pct": 4.97, "volume": 85000000},
        ...
    ]
}
```

---

### `get_market_hours`

Check if markets are open and trading hours.

```python
# Parameters
market: str = "option"   # "equity", "option", "future", "forex"
date: str | None         # ISO date, default today

# Returns
{
    "market": "option",
    "date": "2025-03-26",
    "is_open": true,
    "session_hours": {
        "pre_market": {"start": "07:00", "end": "09:30"},
        "regular": {"start": "09:30", "end": "16:00"},
        "post_market": {"start": "16:00", "end": "20:00"}
    }
}
```

---

### `search_instruments`

Search for symbols by name or description.

```python
# Parameters
query: str                         # Search term
projection: str = "symbol-search"  # "symbol-regex", "desc-search", "fundamental"

# Returns
{
    "instruments": [
        {"symbol": "SPX", "description": "S&P 500 INDEX", "exchange": "IND", "asset_type": "INDEX"},
        ...
    ]
}
```

---

### `get_expiration_dates`

List available option expiration dates (lightweight).

```python
# Parameters
symbol: str   # e.g., "SPX"

# Returns
{
    "symbol": "SPX",
    "expirations": [
        {"date": "2025-03-26", "dte": 0, "type": "weekly"},
        {"date": "2025-03-28", "dte": 2, "type": "weekly"},
        {"date": "2025-04-04", "dte": 9, "type": "weekly"},
        {"date": "2025-04-17", "dte": 22, "type": "monthly"},
        ...
    ]
}
```

---

## GEX & Analysis Tools

### `get_gex_levels`

The flagship tool. Returns all key GEX levels for trading.

```python
# Parameters
symbol: str = "SPX"
max_dte: int = 45       # Max DTE for level extraction
include_0dte: bool = True

# Returns
{
    "symbol": "SPX",
    "spot_price": 5250.50,
    "timestamp": "2025-03-26T14:30:00Z",

    "regime": {
        "type": "positive",           # "positive" or "negative"
        "zero_gamma": 5180.0,
        "spot_vs_zero_gamma": "above"  # spot is above zero gamma → +GEX
    },

    "key_levels": {
        "call_wall": {"price": 5300.0, "call_oi": 45000, "gex": 125000000},
        "put_wall": {"price": 5100.0, "put_oi": 38000, "gex": -98000000},
        "zero_gamma": {"price": 5180.0},
        "max_gamma": {"price": 5250.0, "gex": 180000000},
        "hvl": {"price": 5250.0, "total_oi": 52000}
    },

    "top_10_gex_strikes": [
        {"rank": 1, "strike": 5250.0, "gex": 180000000, "call_oi": 28000, "put_oi": 24000},
        {"rank": 2, "strike": 5300.0, "gex": 125000000, "call_oi": 45000, "put_oi": 8000},
        ...
    ],

    "0dte_levels": {
        "call_wall": {"price": 5280.0, "call_oi": 12000},
        "put_wall": {"price": 5200.0, "put_oi": 9500},
        "zero_gamma": {"price": 5225.0},
        "max_gamma": {"price": 5250.0}
    },

}
```

---

### `get_gex_summary`

Aggregate GEX metrics across all expirations.

```python
# Parameters
symbol: str = "SPX"

# Returns
{
    "symbol": "SPX",
    "total_gex": 450000000,       # Net dealer gamma ($ per 1% move)
    "gross_gex": 1200000000,      # Total magnitude
    "total_dex": 8500000000,      # Net dollar delta exposure
    "total_vex": 320000000,       # Dollar vega (IV sensitivity)
    "aggregate_theta": -15000000, # Daily time decay ($)
    "call_gex": 680000000,        # Total call-side GEX
    "put_gex": -230000000,        # Total put-side GEX
    "gex_ratio": 2.96,            # call_gex / |put_gex| — >1 = call dominated
    "contracts_analyzed": 12450,
    "expirations_analyzed": 28
}
```

---

### `get_0dte_levels`

Same-day expiration GEX levels only.

```python
# Parameters
symbol: str = "SPX"

# Returns — same structure as get_gex_levels but only 0DTE contracts
```

---

### `analyze_volatility`

Comprehensive IV analysis.

```python
# Parameters
symbol: str = "SPX"

# Returns
{
    "symbol": "SPX",
    "atm_iv": 14.5,

    "iv_context": {
        "iv_percentile": 35,       # vs 60-day history (0-100)
        "iv_rank": 0.28,           # (current - min) / (max - min)
        "realized_vol_20d": 12.8,  # 20-day historical vol
        "iv_rv_premium": 1.7,      # ATM IV - RV
        "iv_rv_regime": "fair"     # "rich" (>5%), "fair" (-5 to 5%), "cheap" (<-5%)
    },

    "skew": {
        "25d_skew": 4.2,          # put_25d_IV - call_25d_IV
        "10d_skew": 8.1,          # deep OTM skew
        "40d_skew": 2.1,          # near-ATM skew
        "butterfly_25d": 1.8,     # wing curvature
        "skew_regime": "normal"   # "steep", "normal", "flat", "inverted"
    },

    "term_structure": {
        "shape": "contango",      # "contango", "backwardation", "flat"
        "slope": 2.3,             # back_iv - front_iv
        "by_expiration": [
            {"expiration": "2025-03-28", "dte": 2, "atm_iv": 13.2},
            {"expiration": "2025-04-04", "dte": 9, "atm_iv": 14.1},
            {"expiration": "2025-04-17", "dte": 22, "atm_iv": 15.5},
            ...
        ]
    }
}
```

---

### `get_vix_context`

VIX regime and context.

```python
# Parameters — none required

# Returns
{
    "vix": {
        "level": 18.5,
        "change": -0.8,
        "percentile": 42,          # vs 1-year history
        "regime": "moderate"       # "low", "moderate", "elevated", "spike"
    },
    "vix3m": {
        "level": 19.2
    },
    "term_structure": {
        "vix_vix3m_ratio": 0.96,
        "shape": "contango"        # "contango", "backwardation", "flat"
    }
}
```

---

### `get_iv_surface`

IV across strikes and expirations (for visualization context).

```python
# Parameters
symbol: str = "SPX"
num_strikes: int = 20       # Strikes above/below ATM
max_dte: int = 90

# Returns
{
    "symbol": "SPX",
    "spot": 5250.50,
    "surface": [
        {"strike": 5100, "dte": 2, "iv": 18.2, "delta": -0.15},
        {"strike": 5100, "dte": 9, "iv": 16.8, "delta": -0.18},
        {"strike": 5200, "dte": 2, "iv": 14.8, "delta": -0.35},
        ...
    ]
}
```

---

### `estimate_charm_shift`

Project how GEX levels shift over time (time decay effect on gamma).

```python
# Parameters
symbol: str = "SPX"
hours_forward: float = 3.0    # How many hours to project

# Returns
{
    "current_zero_gamma": 5180.0,
    "projected_zero_gamma": 5195.0,
    "shift_direction": "up",
    "current_total_gex": 450000000,
    "projected_total_gex": 380000000
}
```

---

### `estimate_vanna_shift`

Project how GEX levels shift if IV changes.

```python
# Parameters
symbol: str = "SPX"
iv_change_pct: float = 2.0    # e.g., +2 = VIX goes up 2 points

# Returns
{
    "current_zero_gamma": 5180.0,
    "projected_zero_gamma": 5160.0,
    "iv_change_applied": 2.0,
    "current_total_gex": 450000000,
    "projected_total_gex": 320000000
}
```

---

## Trade Math Tools (Pure Calculation — No Opinions)

### `evaluate_trade`

Calculate P&L, breakevens, POP, and net greeks for a trade that **Claude has selected**.

Claude picks the strikes and structure. This tool just does the math to verify.

```python
# Parameters
symbol: str
legs: list[dict]   # [{"strike": 5300, "type": "CALL", "action": "SELL", "expiration": "2025-03-28"}, ...]

# Returns
{
    "strategy_type": "iron_condor",   # auto-detected from legs
    "max_profit": 270,
    "max_loss": 2230,
    "breakeven_upper": 5327.70,
    "breakeven_lower": 5147.30,
    "pop": 82.5,                      # Probability of profit (%)
    "expected_value": 45.00,
    "risk_reward_ratio": 8.3,         # max_loss / max_profit
    "greeks": {
        "net_delta": -0.02,
        "net_gamma": -0.003,
        "net_theta": 12.50,
        "net_vega": -8.20
    },
    "legs": [
        {"strike": 5325, "type": "CALL", "action": "SELL", "bid": 2.40, "ask": 2.60, "delta": 0.08, "gamma": 0.002},
        {"strike": 5350, "type": "CALL", "action": "BUY", "bid": 1.00, "ask": 1.10, "delta": 0.04, "gamma": 0.001},
        {"strike": 5150, "type": "PUT", "action": "SELL", "bid": 3.10, "ask": 3.30, "delta": -0.09, "gamma": 0.002},
        {"strike": 5125, "type": "PUT", "action": "BUY", "bid": 1.70, "ask": 1.80, "delta": -0.05, "gamma": 0.001}
    ]
}
```

---

### `check_alerts`

Evaluate alert conditions against current market data.

```python
# Parameters
action: str = "check"          # "check", "add", "remove", "list"
condition: dict | None = None  # For "add": {"type": "gex_flip", "symbol": "SPX"}

# Condition types:
# - {"type": "gex_flip", "symbol": "SPX"}
# - {"type": "iv_rank_above", "symbol": "SPX", "threshold": 50}
# - {"type": "vix_above", "threshold": 25}
# - {"type": "wall_breach", "symbol": "SPX", "wall": "call"}  # spot crossed call wall
# - {"type": "price_level", "symbol": "SPX", "above": 5300}

# Returns (for "check")
{
    "timestamp": "2025-03-26T14:30:00Z",
    "alerts_triggered": [
        {
            "type": "gex_flip",
            "symbol": "SPX",
            "triggered": true,
            "previous_regime": "positive",
            "current_regime": "negative",
            "zero_gamma": 5180.0,
            "spot": 5165.0,
            "triggered_at": "2025-03-26T11:42:00Z"
        }
    ],
    "alerts_clear": [
        {"type": "vix_above", "triggered": false, "current_value": 18.5, "threshold": 25}
    ]
}
```

---

## MCP Resources

Resources provide context Claude can read passively.

### `schwab://market-status`
```json
{
    "equity": {"is_open": true, "session": "regular", "closes_at": "16:00 ET"},
    "options": {"is_open": true, "session": "regular", "closes_at": "16:00 ET"},
    "futures": {"is_open": true, "session": "regular", "closes_at": "16:00 ET"}
}
```

### `schwab://vix-dashboard`
```json
{
    "vix": 18.5,
    "vix_change": -0.8,
    "vix_percentile": 42,
    "vix_regime": "moderate",
    "vix3m": 19.2,
    "term_structure": "contango"
}
```

### `schwab://gex-regime/{symbol}`
```json
{
    "symbol": "SPX",
    "regime": "positive",
    "zero_gamma": 5180.0,
    "spot": 5250.5,
    "spot_vs_zero_gamma": "above",
    "call_wall": 5300.0,
    "put_wall": 5100.0
}
```

---

## MCP Prompts

### `morning_briefing`

Pre-market analysis workflow.

**What it does:**
1. Checks market hours and pre-market data
2. Fetches VIX context
3. Calculates GEX levels for SPX
4. Analyzes volatility regime
5. Returns structured briefing for Claude to interpret

**Output template:**
```
## Morning Briefing — {date}

### Market Status
- S&P 500: {price} ({change})
- /ES Futures: {price} ({change})

### VIX Context
- VIX: {level} ({regime}) — {percentile}th percentile
- Term Structure: {shape}

### GEX Regime
- Regime: {positive/negative}
- Zero Gamma: {level}
- Call Wall: {level} | Put Wall: {level}

### Volatility
- ATM IV: {iv}% | IV Rank: {rank}
- Skew: {regime}
- IV-RV Premium: {premium}

### Today's Trading Zones
- Resistance: {levels}
- Support: {levels}
- Range: {put_wall} — {call_wall}

### Recommendation
{Based on regime + IV + VIX, suggest today's approach}
```

### `iron_condor_scan`

Automated iron condor search tuned to current conditions.

### `regime_check`

Quick 30-second regime assessment.

### `intraday_levels`

0DTE levels with charm-adjusted projections.
