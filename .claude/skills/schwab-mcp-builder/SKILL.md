---
name: schwab-mcp-builder
description: "This skill enforces coding patterns, conventions, and test-driven development for the Schwab Options MCP Server project (thinkorswim_local_mcp). It should be used automatically whenever building new phases, adding tools, modifying existing code, or refactoring in this project. TRIGGER when: working in thinkorswim_local_mcp, building MCP tools, adding core computation modules, writing tests, or modifying any src/ code. DO NOT TRIGGER when: editing documentation only, or working outside this project."
---

# Schwab MCP Builder

## Overview

This skill provides coding standards, architecture enforcement, and test-driven development workflow for the Schwab Options MCP Server — an MCP server that gives Claude access to Schwab market data for options trading analysis.

For detailed architecture and tool specifications, read `references/architecture.md` and `references/tool_specs.md`.

## Core Principle

**MCP = calculator (data + math, no opinions). Claude = analyst (decisions).**

Tool output must never contain opinions, recommendations, or interpretations. Return numbers, labels, and structured data only.

## Development Workflow (Test-Driven)

Follow this order strictly when building any new module:

1. **Read existing code** — understand what exists, how it's wired, what patterns are established
2. **Run existing tests** — `pytest tests/` must pass before any changes
3. **Write tests first** — create test file with all test cases before writing implementation
4. **Write implementation** — build the module to make tests pass
5. **Run all tests** — verify new tests pass AND existing tests still pass
6. **Wire into server** — register new tools/modules in `src/server.py`

### Critical Rule: Never Update Tests Without Verification

When modifying existing code:
- Run existing tests FIRST
- If tests pass after code changes → update tests to mirror changes
- If tests FAIL after code changes → STOP and notify user why
- Never silently update tests to make them pass — the tests are the safety net

## Architecture Rules

Read `references/architecture.md` for full details. Key rules:

### 4-Layer Architecture
```
src/tools/   → Layer 1: MCP tool handlers (orchestrate core modules directly)
src/core/    → Layer 2: Pure computation (no I/O, no side effects)
src/data/    → Layer 3: Data access (Schwab client, cache, tokens, models)
src/shared/  → Cross-cutting: logging, retry, timing (DRY — no duplication)
```

### DRY (Do Not Repeat Yourself)
- Extract shared logic into `src/shared/` modules
- If the same pattern appears in two places, refactor into a shared utility
- Common candidates: logging setup, HTTP retry logic, timing/profiling, error formatting

### Tool Wiring Pattern
Tool handlers orchestrate core modules directly — no service layer:
```python
# src/tools/gex.py
def get_gex_levels(symbol: str, max_dte: int = 45) -> dict:
    chain = schwab_client.get_options_chain(symbol, to_dte=max_dte)
    per_strike = gex_calculator.calculate(chain)
    levels = gex_levels.extract(per_strike, chain.underlying_price)
    return levels.model_dump(mode="json")
```

### Tool Registration Pattern
Each tool module exposes `register_tools(mcp, dependencies...)`:
```python
# src/tools/market_data.py
def register_tools(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    @mcp.tool(name="get_quote", description="...")
    def get_quote(symbol: str) -> dict:
        ...
```

Wired in `src/server.py`:
```python
from src.tools.market_data import register_tools
register_tools(mcp, schwab_client)
```

### Data Models
- All models in `src/data/models.py` using Pydantic v2
- Tools return `.model_dump(mode="json")`
- Add new models to this file as needed — one models file, not scattered

## Coding Patterns

### Error Handling — Fail Loudly

**Custom exceptions per module/domain:**
```python
class GexCalculationError(Exception):
    """Raised when GEX calculation encounters invalid data."""

class VolatilityError(Exception):
    """Raised when volatility analysis fails."""
```

**Never use defensive fallbacks:**
```python
# WRONG — silent failure, hides bugs
value = data.get("gamma") or 0.0
result = compute(data) or {}

# CORRECT — fail loudly, surface the problem
value = data["gamma"]
result = compute(data)
```

**Trust internal data.** Pydantic validates at the Schwab API boundary. After that, data is typed and trustworthy. Do not re-validate internally.

**No overly broad try/except:**
```python
# WRONG — swallows real bugs
try:
    result = complex_calculation(data)
except Exception:
    return None

# CORRECT — catch specific errors at boundaries
try:
    resp = client.option_chains(symbol)
    data = resp.json()
except requests.RequestException as e:
    raise SchwabClientError(f"API call failed for {symbol}: {e}") from e
```

### Function Design

**Small, focused functions.** Prefer many modules over giant functions. If a function is getting long, split it.

**Action-verb names** that tell the reader what the function does without reading the body:
```python
# Good — clear action
def calculate_per_strike_gex(contracts: list[OptionContract], spot: float) -> list[StrikeGex]: ...
def extract_zero_gamma_level(strike_gex: list[StrikeGex]) -> float: ...
def classify_gex_regime(spot: float, zero_gamma: float) -> str: ...

# Bad — vague, requires reading the body
def process(data): ...
def handle(contracts): ...
def do_gex(chain): ...
```

**Every function gets a docstring** describing what it does:
```python
def extract_call_wall(strike_gex: list[StrikeGex]) -> KeyLevel:
    """Find the strike with highest call open interest (call wall)."""
    ...
```

### Type Hints

Strict everywhere — all function params, return types, and variable annotations where non-obvious:
```python
def calculate_per_strike_gex(
    contracts: list[OptionContract],
    spot_price: float,
    max_dte: int = 45,
) -> list[StrikeGex]:
```

### Imports

Absolute imports only:
```python
from src.data.models import OptionContract, OptionsChainData
from src.core.gex_calculator import calculate_per_strike_gex
```

### Formatting

Use `ruff` for linting and formatting. Add to `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

## Testing Standards

### Structure
- Flat test files in `tests/` (e.g., `tests/test_gex_calculator.py`)
- Shared fixtures in `tests/fixtures/` and `tests/conftest.py`
- JSON files for Schwab API response shapes (`tests/fixtures/*.json`)
- Python factory functions for internal models (`tests/fixtures/factories.py`)

### Mock Level
Mock at `schwabdev.Client` level — fake the HTTP responses from Schwab, not our wrapper:
```python
@pytest.fixture
def mock_schwab_client(mocker):
    """Mock schwabdev.Client to return fake API responses."""
    client = mocker.patch("schwabdev.Client")
    # Configure fake responses...
    return client
```

### Every Public Function Gets a Test

Every public function must have at least one test verifying:
- It is called with correct parameters
- It returns the expected value
- It handles edge cases

This ensures another Claude session cannot accidentally break existing functionality.

### Parameterized Tests for Edge Cases

Use `pytest.mark.parametrize` to cover multiple scenarios:
```python
@pytest.mark.parametrize("spot,zero_gamma,expected_regime", [
    (5300.0, 5200.0, "positive"),   # spot above zero gamma
    (5100.0, 5200.0, "negative"),   # spot below zero gamma
    (5200.0, 5200.0, "positive"),   # spot exactly at zero gamma
])
def test_classify_gex_regime(spot: float, zero_gamma: float, expected_regime: str) -> None:
    """Test GEX regime classification based on spot vs zero gamma level."""
    result = classify_gex_regime(spot, zero_gamma)
    assert result == expected_regime
```

### Chain Tests (Dependency Chain Verification)

Tests must verify the full call chain, not just isolated units. Start from the function calling Schwab API and test every function propagating upward:

```python
def test_get_gex_levels_full_chain(mock_schwab_response, cache_manager) -> None:
    """Test full chain: tool → gex_calculator → schwab_client → mock API.

    Verifies that get_gex_levels correctly:
    1. Calls schwab_client.get_options_chain with correct params
    2. Passes chain data to gex_calculator.calculate
    3. Passes results to gex_levels.extract
    4. Returns properly structured response
    """
    ...
```

### Cache Chain Tests

Verify caching behavior within the chain:
```python
def test_options_chain_cache_hit(mock_schwab_client) -> None:
    """Test that second call returns cached data without hitting API.

    First call should hit schwabdev.Client.option_chains().
    Second call within TTL should return cached data.
    schwabdev.Client.option_chains() should be called exactly once.
    """
    ...
```

### Error Propagation Tests

Test that errors propagate correctly with proper exception types:
```python
def test_schwab_api_error_propagates_as_schwab_client_error(mock_schwab_client) -> None:
    """Test that schwabdev.Client errors are wrapped in SchwabClientError.

    When schwabdev.Client.option_chains() raises an exception,
    SchwabClient should catch it and raise SchwabClientError with
    a clear message including the symbol and original error.
    """
    mock_schwab_client.option_chains.side_effect = Exception("API timeout")
    with pytest.raises(SchwabClientError, match="SPX"):
        schwab_client.get_options_chain("SPX")
```

### Test Comments

Every test function must have a docstring explaining:
- What behavior is being tested
- Why it matters (what breaks if this test is removed)
- Expected outcome

## Resources

### references/
- `architecture.md` — Full architecture, directory structure, layer rules, caching strategy, Schwab API constraints
- `tool_specs.md` — Complete specifications for all planned MCP tools across all phases, including parameters and return shapes
