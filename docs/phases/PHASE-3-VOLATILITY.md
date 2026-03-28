# Phase 3 — Volatility & Context

**Goal:** Full IV analysis and VIX context. Claude can assess volatility regime and term structure.

**Depends on:** Phase 1 (Schwab client), Phase 2 (GEX engine for regime context)

## Deliverables

1. IV skew analysis (10d/25d/40d delta, butterfly)
2. IV term structure (contango/backwardation detection)
3. IV percentile, rank, and realized vol calculation
4. VIX context (level, percentile, regime, term structure)
5. Expected move calculation (ATM straddle + IV-based 1SD)
6. Five new tools

## Files to Create

```
src/
├── tools/
│   └── volatility.py            # Vol tool handlers
│
├── core/
│   ├── volatility.py            # IV skew, butterfly, term structure
│   ├── iv_context.py            # IV percentile, rank, realized vol
│   └── vix_context.py           # VIX regime, percentile, term structure
│
```

## Port Mapping

| Source (gex-tool) | Target (MCP) | Notes |
|---|---|---|
| `src/gex/volatility.py` | `core/volatility.py` | IV skew, butterfly, term structure |
| `src/gex/iv_context.py` | `core/iv_context.py` | Percentile, rank, RV, IV-RV premium |
| `src/data/vix_context.py` | `core/vix_context.py` | VIX regime, VIX/VIX3M ratio |

## Core Calculations

### IV Skew (per expiration)
Find contracts nearest to target delta, compute skew:
```
25d_skew = put_25d_IV - call_25d_IV
10d_skew = put_10d_IV - call_10d_IV
40d_skew = put_40d_IV - call_40d_IV
butterfly_25d = (put_25d_IV + call_25d_IV) / 2 - ATM_IV
```

**Skew regimes:**
- Steep: ratio > 0.35
- Normal: 0.15 - 0.35
- Flat: < 0.15
- Inverted: < 0 (calls more expensive than puts)

### IV Term Structure
ATM IV by expiration date:
```
term_slope = back_month_IV - front_month_IV
```
- Contango: slope > 0 (normal — near-term cheaper)
- Backwardation: slope < 0 (fear — near-term elevated)
- Flat: near zero

### IV Percentile & Rank
```
IV_percentile = percentile_rank(current_IV, 60_day_IV_history)  → 0-100
IV_rank = (current_IV - min_60d) / (max_60d - min_60d)         → 0.0-1.0
```

### Realized Volatility
```
daily_returns = ln(close_t / close_t-1)
RV_20d = std(daily_returns, 20) × √252 × 100
```

### IV-RV Premium
```
premium = ATM_IV - RV_20d
```
- Rich: premium > 5% (favorable for selling)
- Fair: -5% to 5%
- Cheap: premium < -5% (unfavorable for selling)

### VIX Context
```
VIX_percentile = percentile_rank(current_VIX, 1_year_VIX_history)
VIX_VIX3M_ratio = VIX / VIX3M
```

**VIX regimes:**
- Spike: VIX ≥ 30 or percentile ≥ 90
- Elevated: VIX ≥ 20 or percentile ≥ 70
- Moderate: VIX ≥ 15 or percentile ≥ 40
- Low: everything else

**Term structure:**
- Contango: ratio < 0.95 (normal)
- Backwardation: ratio > 1.05 (fear)
- Flat: 0.95 - 1.05

### Expected Move
```
straddle_method = ATM_call_bid + ATM_put_bid
iv_method = spot × ATM_IV/100 × √(DTE/365)
```

## Tool Specifications

### `analyze_volatility`
- Input: `symbol`
- Returns: ATM IV, IV context (percentile, rank, RV, premium), skew (25d/10d/40d, butterfly, regime), term structure (shape, slope, per-expiry)

### `get_vix_context`
- Input: none
- Fetches $VIX, $VIX3M quotes + 1-year VIX history
- Returns: VIX level, change, percentile, regime, VIX3M, ratio, term structure shape

### `get_iv_surface`
- Input: `symbol`, `num_strikes`, `max_dte`
- Returns: grid of (strike, dte, iv, delta) tuples

### `analyze_term_structure`
- Input: `symbol`
- Returns: ATM IV per expiration, shape, slope

### `get_expected_move`
- Input: `symbol`, `expiration` (optional), `multiple_expirations` flag
- Returns: straddle-based and IV-based expected move, upper/lower bounds

## Definition of Done

- [ ] `analyze_volatility("SPX")` returns full IV analysis
- [ ] IV skew values match gex-tool output
- [ ] `get_vix_context()` returns VIX regime and percentile
- [ ] `get_iv_surface("SPX")` returns surface data
- [ ] `get_expected_move("SPX")` returns straddle + IV-based move
- [ ] `get_expected_move("SPX", multiple_expirations=True)` returns all near-term
- [ ] VIX history cached (1-day TTL — historical data doesn't change)
