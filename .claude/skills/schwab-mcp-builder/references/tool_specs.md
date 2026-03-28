# MCP Tool Specifications

## Tool Design Rules

1. Return structured JSON that Claude can reason about
2. Sensible defaults — every tool works with minimal parameters
3. Data + math only — never output opinions, rankings, or recommendations
4. Leverage the cache layer — repeated calls must be fast
5. Composable — tools chain: get_gex_levels → get_options_chain → evaluate_trade

## Phase 1 — Foundation (COMPLETE)

### get_quote
- Input: `symbol: str`
- Returns: Quote model (last, bid, ask, OHLC, volume, net_change, is_delayed)

### get_options_chain
- Input: `symbol: str`, `contract_type: str = "ALL"`, `from_dte: int | None`, `to_dte: int | None`, `min_open_interest: int = 0`, `min_volume: int = 0`
- Returns: OptionsChainData model (underlying_price, call_contracts, put_contracts, expirations, strikes)
- Multi-range DTE fetching with per-range caching

## Phase 2 — GEX Engine

### get_gex_levels
- Input: `symbol: str = "SPX"`, `max_dte: int = 45`, `include_0dte: bool = True`
- Returns: regime (positive/negative, zero_gamma), key_levels (call_wall, put_wall, zero_gamma, max_gamma, hvl), top_10_gex_strikes, 0dte_levels
- GEX formula: GEX = |Γ| × OI × 100 × S² × 0.01
- Calls sign: +1, Puts sign: -1

### get_gex_summary
- Input: `symbol: str = "SPX"`
- Returns: total_gex, gross_gex, total_dex, total_vex, aggregate_theta, call_gex, put_gex, gex_ratio

### get_0dte_levels
- Input: `symbol: str = "SPX"`
- Returns: same structure as get_gex_levels but filtered to DTE=0

### estimate_charm_shift
- Input: `symbol: str = "SPX"`, `hours_forward: float = 3.0`
- Returns: current vs projected zero_gamma, shift_direction, current vs projected total_gex
- Formula: charm ≈ -θ/S

### estimate_vanna_shift
- Input: `symbol: str = "SPX"`, `iv_change_pct: float = 2.0`
- Returns: current vs projected zero_gamma, iv_change_applied, current vs projected total_gex
- Formula: vanna ≈ ν/S

## Phase 3 — Volatility & Context

### analyze_volatility
- Input: `symbol: str = "SPX"`
- Returns: atm_iv, iv_context (percentile, rank, rv_20d, iv_rv_premium, regime), skew (25d, 10d, 40d, butterfly, regime), term_structure (shape, slope, by_expiration)

### get_iv_surface
- Input: `symbol: str = "SPX"`, `num_strikes: int = 20`, `max_dte: int = 90`
- Returns: surface grid (strike, dte, iv, delta)

### analyze_term_structure
- Input: `symbol: str = "SPX"`
- Returns: ATM IV across expirations, contango/backwardation classification

### get_vix_context
- Input: none
- Returns: vix (level, change, percentile, regime), vix3m (level), term_structure (ratio, shape)

### get_expected_move
- Input: `symbol: str = "SPX"`, `expiration: str | None`, `multiple_expirations: bool = False`
- Returns: expected_move_straddle, expected_move_1sd, upper/lower bounds, atm_strike, atm_iv

## Phase 3B — Historical Snapshots

### get_gex_history / get_iv_history / get_vix_history / get_expected_move_history
- Daily Parquet snapshots with trend analysis
- Regime streaks, accuracy stats

### take_snapshot
- Manually trigger daily snapshot save to Parquet

## Phase 4 — Trade Math

### evaluate_trade
- Input: `symbol: str`, `legs: list[dict]` (strike, type, action, expiration)
- Returns: strategy_type, max_profit, max_loss, breakevens, POP (Black-Scholes), expected_value, risk_reward, net greeks

### check_alerts
- Input: `action: str`, `condition: dict | None`
- Condition types: gex_flip, iv_rank_above, vix_above, wall_breach, price_level
- Returns: triggered/clear alerts with context

## Phase 5 — Remaining Tools

### get_price_history, get_futures_quote, get_market_movers, get_market_hours, search_instruments, get_expiration_dates

### MCP Resources
- schwab://market-status
- schwab://vix-dashboard
- schwab://gex-regime/{symbol}
- schwab://watchlist

### MCP Prompts
- morning_briefing, iron_condor_scan, regime_check, intraday_levels
