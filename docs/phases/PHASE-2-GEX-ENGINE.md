# Phase 2 — GEX Engine

**Goal:** Port GEX calculation and level extraction from gex-tool. Claude can ask "what are the GEX levels for SPX?" and get a complete answer.

**Depends on:** Phase 1 (Schwab client, cache, models, MCP server)

## Deliverables

1. GEX calculator (per-strike GEX, aggregate metrics)
2. GEX level extractor (walls, zero gamma, HVL, max gamma, top 10)
3. 0DTE level extraction
4. Charm/vanna projection calculations
5. Five new tools: `get_gex_levels`, `get_gex_summary`, `get_0dte_levels`, `estimate_charm_shift`, `estimate_vanna_shift`

## Files to Create

```
src/
├── tools/
│   └── gex.py                   # GEX tool handlers
│
├── core/
│   ├── __init__.py
│   ├── gex_calculator.py        # GEX formula, per-strike, aggregates
│   └── gex_levels.py            # Level extraction, zero gamma, walls
```

## Port Mapping

| Source (gex-tool) | Target (MCP) | Notes |
|---|---|---|
| `src/gex/calculator.py` → `gex_formula()` | `core/gex_calculator.py` | Exact same formula |
| `src/gex/calculator.py` → `calculate_gex()` | `core/gex_calculator.py` | Per-strike + aggregate |
| `src/gex/calculator.py` → `calculate_charm_adjustment()` | `core/gex_calculator.py` | charm ≈ -θ/S |
| `src/gex/calculator.py` → `calculate_vanna_adjustment()` | `core/gex_calculator.py` | vanna ≈ ν/S |
| `src/gex/levels.py` → `find_zero_gamma_level()` | `core/gex_levels.py` | Linear interpolation |
| `src/gex/levels.py` → `classify_levels()` | `core/gex_levels.py` | Major/minor support/resistance |
| `src/gex/levels.py` → `calculate_significance()` | `core/gex_levels.py` | 0-1 normalized score |
| `src/levels/extractor.py` → `extract_levels()` | `core/gex_levels.py` | Walls, HVL, max gamma, top 10 |

## Core Formulas

### GEX per strike
```
GEX = abs(Γ) × OI × 100 × S² × 0.01
```
- Call GEX: positive sign (dealers long calls → stabilizing)
- Put GEX: negative sign (dealers short puts → destabilizing)
- Net GEX at strike = call_gex + put_gex

### Aggregate metrics
| Metric | Formula |
|---|---|
| Total GEX | Σ signed GEX across all strikes |
| Gross GEX | Σ unsigned GEX |
| Total DEX | Σ(δ × OI × 100 × S × sign) |
| Total VEX | Σ(ν × OI × 100) |
| Aggregate Theta | Σ(θ × OI × 100) |

### Level extraction (0-45 DTE only)
| Level | Method |
|---|---|
| Call Wall | Strike with max call open interest |
| Put Wall | Strike with max put open interest |
| Zero Gamma | Linear interpolation where net GEX crosses zero |
| Max Gamma | Strike with highest abs(GEX) |
| HVL | Strike with highest total OI (calls + puts) |
| GEX 1-10 | Top 10 strikes by abs(GEX), ranked |

### Charm projection
```
charm ≈ -θ / S
gamma_change = charm × (hours_forward / 24)
projected_GEX = current_GEX + (gamma_change × OI × 100 × S² × 0.01)
```

### Vanna projection
```
vanna ≈ ν / S
gamma_change = vanna × iv_change_pct
projected_GEX = current_GEX + (gamma_change × OI × 100 × S² × 0.01)
```

## Tool Specifications

### `get_gex_levels`
- Input: `symbol` (default "SPX"), `max_dte` (default 45), `include_0dte` (default true)
- Fetches options chain via Phase 1 client
- Runs GEX calculator on all contracts
- Extracts levels from 0-`max_dte` contracts
- Returns: regime, key levels, top 10 strikes, 0DTE levels

### `get_gex_summary`
- Input: `symbol`
- Returns: total GEX, gross GEX, DEX, VEX, theta, call/put GEX, ratio

### `get_0dte_levels`
- Input: `symbol`
- Filters to DTE=0 only, computes levels
- Returns: same structure as get_gex_levels but 0DTE only

### `estimate_charm_shift`
- Input: `symbol`, `hours_forward`
- Returns: current vs projected zero gamma, total GEX

### `estimate_vanna_shift`
- Input: `symbol`, `iv_change_pct`
- Returns: current vs projected zero gamma, total GEX

## Definition of Done

- [ ] `get_gex_levels("SPX")` returns all key levels
- [ ] Zero gamma calculation matches gex-tool output (within 0.1%)
- [ ] Call wall / put wall match gex-tool output
- [ ] `get_gex_summary("SPX")` returns aggregate metrics
- [ ] `get_0dte_levels("SPX")` works during market hours (when 0DTE exists)
- [ ] `estimate_charm_shift("SPX", 3)` returns projected levels
- [ ] `estimate_vanna_shift("SPX", 2)` returns projected levels
- [ ] GEX levels use only 0-45 DTE contracts (configurable)
- [ ] Unit tests for GEX formula and zero gamma interpolation
