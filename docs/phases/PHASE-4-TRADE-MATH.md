# Phase 4 — Trade Math & Alerts

**Goal:** Claude can ask the MCP to crunch the numbers on any trade setup and monitor conditions.

**Depends on:** Phase 1 (Schwab client), Phase 2 (GEX for alert conditions), Phase 3 (IV for alert conditions)

## Deliverables

1. Trade evaluator (P&L, POP, breakevens, net greeks)
2. POP calculation via Black-Scholes integration
3. Multi-leg strategy detection (iron condor, vertical, straddle, etc.)
4. Alert condition engine with disk-persisted state
5. Two new tools: `evaluate_trade`, `check_alerts`

## Files to Create

```
src/
├── tools/
│   └── trade_math.py            # evaluate_trade, check_alerts handlers
│
├── core/
│   └── trade_math.py            # POP, P&L, breakevens, strategy detection
│
├── state/                       # Alert state persistence
│   └── (created at runtime)
```

## Implementation Details

### core/trade_math.py

#### Strategy Auto-Detection
Detect strategy type from legs:

| Legs | Detection Rule | Strategy |
|---|---|---|
| 1 long call/put | Single leg | Long call/put |
| 1 short call/put | Single leg | Short call/put |
| 1 short + 1 long, same type, same exp | Same type, diff strikes | Vertical spread |
| 2 short + 2 long, calls+puts | Short call + long call + short put + long put | Iron condor |
| 1 short call + 1 short put, same strike | Same strike, diff type | Short straddle |
| 1 short call + 1 short put, diff strike | Diff strike, diff type | Short strangle |
| Same strike, diff expiration | Same strike, diff exp | Calendar spread |

#### P&L Calculation
For each leg:
```
credit/debit = bid (if selling) or ask (if buying)
net_credit = Σ credits - Σ debits
```

For verticals and iron condors:
```
max_profit = net_credit × multiplier
max_loss = (width - net_credit) × multiplier
breakeven = short_strike ± net_credit (depends on direction)
risk_reward_ratio = max_loss / max_profit
```

#### POP via Black-Scholes
Probability of profit = probability that price stays between breakevens at expiration.

For a single short put at strike K with credit C:
```
breakeven = K - C
POP = P(S_T > breakeven) = N(d2)

where:
d2 = (ln(S/breakeven) + (r - σ²/2) × T) / (σ × √T)
S = current spot
σ = ATM implied volatility (annualized, decimal)
T = time to expiration (years)
r = risk-free rate
N() = standard normal CDF
```

For iron condors (both breakevens):
```
POP = P(lower_BE < S_T < upper_BE)
    = N(d2_upper) - N(d2_lower)
```

#### Net Greeks
```
net_delta = Σ(leg.delta × leg.quantity × leg.sign)
net_gamma = Σ(leg.gamma × leg.quantity × leg.sign)
net_theta = Σ(leg.theta × leg.quantity × leg.sign)
net_vega  = Σ(leg.vega  × leg.quantity × leg.sign)
```
where sign = +1 for long, -1 for short

### Alert Condition Engine

#### Supported Conditions

| Condition | Parameters | Trigger |
|---|---|---|
| `gex_flip` | symbol | GEX regime changed since last check |
| `iv_rank_above` | symbol, threshold | IV rank exceeds threshold |
| `iv_rank_below` | symbol, threshold | IV rank drops below threshold |
| `vix_above` | threshold | VIX level exceeds threshold |
| `vix_below` | threshold | VIX drops below threshold |
| `wall_breach` | symbol, wall (call/put) | Spot price crosses call or put wall |
| `price_above` | symbol, level | Price exceeds level |
| `price_below` | symbol, level | Price drops below level |
| `expected_move_breach` | symbol | Spot outside expected move range |

#### State Persistence
```json
// state/alerts.json
{
    "conditions": [
        {"id": "abc123", "type": "gex_flip", "symbol": "SPX", "created_at": "..."}
    ],
    "last_check": "2025-03-26T14:30:00Z",
    "previous_state": {
        "SPX_gex_regime": "positive",
        "VIX_level": 18.5
    },
    "history": [
        {"condition_id": "abc123", "triggered_at": "...", "details": {...}}
    ]
}
```

#### Evaluation Flow
1. Load conditions from disk
2. For each condition, fetch current market data
3. Compare against threshold or previous state
4. Return triggered/clear status with raw values
5. Update previous state on disk

## Tool Specifications

### `evaluate_trade`
- Input: `symbol`, `legs` (list of {strike, type, action, expiration})
- Fetches current pricing for each leg from options chain
- Auto-detects strategy type
- Calculates P&L, POP, breakevens, net greeks
- Returns pure numbers — no opinions

### `check_alerts`
- Input: `action` ("check", "add", "remove", "list"), `condition` (for add)
- "add": saves condition to disk
- "check": evaluates all conditions, returns triggered/clear with raw values
- "remove": removes condition by id
- "list": returns all active conditions
- Returns raw values only — Claude interprets what to do

## Definition of Done

- [ ] `evaluate_trade` correctly calculates iron condor P&L
- [ ] `evaluate_trade` correctly calculates vertical spread P&L
- [ ] POP calculation matches thinkorswim within ±2%
- [ ] Strategy auto-detection works for all supported types
- [ ] `check_alerts(action="add", condition={...})` persists to disk
- [ ] `check_alerts(action="check")` evaluates conditions and returns results
- [ ] Alert state survives MCP server restart
- [ ] Unit tests for POP calculation (compare against known values)
