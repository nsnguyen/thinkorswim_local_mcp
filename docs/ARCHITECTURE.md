# Schwab Options MCP Server — Architecture

## Overview

A **Model Context Protocol (MCP) server** that gives Claude direct access to Charles Schwab market data and GEX (Gamma Exposure) analysis. Designed for **options premium selling** — weekly SPX iron condors, directional credit spreads, and intraday regime detection.

```
┌─────────────────────────────────────────────────────────┐
│                     Claude Desktop                       │
│                                                         │
│  "What are the GEX levels for SPX?"                     │
│  "Find me an iron condor with 80% POP for Friday"       │
│  "Has the gamma regime flipped today?"                   │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Protocol (stdio)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Schwab Options MCP Server                   │
│                     (Python)                             │
│                                                         │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │  Tools  │ │Resources │ │  Prompts  │ │  Alerts   │  │
│  └────┬────┘ └────┬─────┘ └─────┬─────┘ └─────┬─────┘  │
│       │           │             │              │         │
│  ┌────▼───────────▼─────────────▼──────────────▼─────┐  │
│  │              Core Engine                           │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │  │
│  │  │ GEX Calc │ │ Vol Anlz │ │ Strategy Engine    │ │  │
│  │  └──────────┘ └──────────┘ └────────────────────┘ │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                               │
│  ┌───────────────────────▼───────────────────────────┐  │
│  │              Data Layer                            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │  │
│  │  │ Schwab   │ │  Cache   │ │ Token Manager      │ │  │
│  │  │ Client   │ │ (Disk)   │ │ (OAuth 2.0)        │ │  │
│  │  └──────────┘ └──────────┘ └────────────────────┘ │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                               │
└──────────────────────────┼───────────────────────────────┘
                           │ HTTPS
                           ▼
              ┌──────────────────────┐
              │  Schwab Developer    │
              │  API (REST)          │
              │  api.schwabapi.com   │
              └──────────────────────┘
```

---

## System Architecture (Mermaid)

```mermaid
graph TB
    subgraph Claude["Claude Desktop / Claude Code"]
        User[User Conversation]
    end

    subgraph MCP["MCP Server (Python, stdio)"]
        direction TB

        subgraph Tools["MCP Tools (Claude calls these)"]
            T1[get_options_chain]
            T2[get_gex_levels]
            T3[get_quote]
            T4[get_price_history]
            T5[get_futures_quote]
            T6[analyze_volatility]
            T7[find_spreads]
            T8[find_iron_condors]
            T9[get_market_movers]
            T10[get_market_hours]
            T11[search_instruments]
            T12[check_alerts]
            T13[get_gex_summary]
            T14[get_iv_surface]
            T15[analyze_term_structure]
        end

        subgraph Resources["MCP Resources (context for Claude)"]
            R1["schwab://market-status"]
            R2["schwab://vix-dashboard"]
            R3["schwab://gex-regime/{symbol}"]
            R4["schwab://watchlist"]
        end

        subgraph Prompts["MCP Prompts (reusable workflows)"]
            P1[morning_briefing]
            P2[iron_condor_scan]
            P3[regime_check]
            P4[intraday_levels]
        end

        subgraph Engine["Core Engine"]
            GEX[GEX Calculator]
            VOL[Volatility Analyzer]
            STRAT[Strategy Engine]
            ALERT[Alert Evaluator]
        end

        subgraph Data["Data Layer"]
            SC[Schwab Client]
            CACHE[Disk Cache]
            TOKEN[Token Manager]
        end
    end

    subgraph Schwab["Schwab API"]
        API_CHAINS["/chains"]
        API_QUOTES["/quotes"]
        API_HISTORY["/pricehistory"]
        API_MOVERS["/movers"]
        API_HOURS["/markets"]
        API_SEARCH["/instruments"]
    end

    User <-->|MCP Protocol| Tools
    User <-->|MCP Protocol| Resources
    User <-->|MCP Protocol| Prompts

    Tools --> Engine
    Resources --> Engine
    Prompts --> Tools

    Engine --> Data
    GEX --> SC
    VOL --> SC
    STRAT --> GEX
    STRAT --> VOL
    ALERT --> GEX
    ALERT --> VOL

    SC --> CACHE
    SC --> TOKEN
    TOKEN --> API_CHAINS
    SC --> API_CHAINS
    SC --> API_QUOTES
    SC --> API_HISTORY
    SC --> API_MOVERS
    SC --> API_HOURS
    SC --> API_SEARCH

    style Claude fill:#f0f4ff,stroke:#4a6cf7
    style MCP fill:#f8f9fa,stroke:#333
    style Tools fill:#e8f5e9,stroke:#2e7d32
    style Resources fill:#fff3e0,stroke:#ef6c00
    style Prompts fill:#fce4ec,stroke:#c62828
    style Engine fill:#e3f2fd,stroke:#1565c0
    style Data fill:#f3e5f5,stroke:#7b1fa2
    style Schwab fill:#fff8e1,stroke:#f57f17
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant U as User (Claude)
    participant M as MCP Server
    participant C as Cache
    participant S as Schwab API

    U->>M: get_gex_levels("SPX")
    M->>C: Check cache (TTL by DTE range)
    alt Cache Hit
        C-->>M: Cached options chain
    else Cache Miss
        M->>S: GET /chains (0-7 DTE, TTL=60s)
        S-->>M: Near-term contracts
        M->>S: GET /chains (8-45 DTE, TTL=120s)
        S-->>M: Mid-term contracts
        M->>C: Store with per-range TTL
    end
    M->>M: Calculate GEX per strike
    M->>M: Extract levels (walls, zero gamma, HVL)
    M->>M: Classify regime (+GEX/-GEX)
    M-->>U: GEX levels + regime + trading zones

    Note over U,S: Claude interprets results and<br/>advises on iron condor placement
```

---

## MCP Tools (What Claude Can Call)

### Market Data Tools

| Tool | Description | Schwab Endpoint |
|------|-------------|-----------------|
| `get_quote` | Real-time quote for any symbol (equity, ETF, index) | `GET /quotes` |
| `get_options_chain` | Full options chain with greeks, OI, volume | `GET /chains` |
| `get_price_history` | OHLCV candles (1min to monthly, up to 20yr) | `GET /pricehistory` |
| `get_futures_quote` | Quote for futures (/ES, /NQ, /CL, etc.) | `GET /quotes` |
| `get_market_movers` | Top movers by volume, trades, % change | `GET /movers/{index}` |
| `get_market_hours` | Market hours for equity/option/futures/forex | `GET /markets` |
| `search_instruments` | Search symbols by name, description, CUSIP | `GET /instruments` |
| `get_expiration_dates` | Available expiration dates for a symbol | `GET /expirationchain` |

### GEX & Analysis Tools

| Tool | Description | Computation |
|------|-------------|-------------|
| `get_gex_levels` | Key GEX levels: walls, zero gamma, HVL, max gamma, top 10 | GEX = \|Γ\| × OI × 100 × S² × 0.01 |
| `get_gex_summary` | Aggregate GEX metrics: total, gross, DEX, VEX, theta | Sum across all strikes |
| `get_0dte_levels` | Same-day expiration GEX levels only | Filter DTE=0, compute levels |
| `analyze_volatility` | IV skew (10d/25d/40d), butterfly, term structure, IV-RV | Options chain analytics |
| `get_iv_surface` | IV by strike and expiration (surface data) | Grid interpolation |
| `analyze_term_structure` | ATM IV across expirations, contango/backwardation | Per-expiry ATM IV |
| `get_vix_context` | VIX level, percentile, regime, VIX/VIX3M ratio | VIX quote + 1yr history |
| `estimate_charm_shift` | Project GEX shift N hours forward (time decay) | charm ≈ -θ/S |
| `estimate_vanna_shift` | Project GEX shift for IV change | vanna ≈ ν/S |

### Strategy Tools

| Tool | Description | Logic |
|------|-------------|-------|
| `find_iron_condors` | Scan for iron condors matching criteria (POP, width, premium) | Filter by delta, width, credit |
| `find_spreads` | Find credit/debit spreads (vertical, calendar) | Strike selection by delta/width |
| `evaluate_trade` | Analyze a specific trade: max profit, max loss, breakevens, POP | Options math |
| `get_regime_signal` | Current regime: positive/negative GEX, directional bias, vol posture | GEX + IV + VIX composite |
| `check_alerts` | Evaluate watchlist conditions (IV rank threshold, GEX flip, etc.) | Condition engine |

### MCP Resources (Ambient Context)

Resources provide **background context** that Claude can read without explicit tool calls:

| Resource URI | Description | Auto-refresh |
|---|---|---|
| `schwab://market-status` | Market open/closed, hours today, next open | On access |
| `schwab://vix-dashboard` | VIX level, regime, percentile, term structure | 60s cache |
| `schwab://gex-regime/{symbol}` | Current GEX regime, zero gamma level, flip status | 60s cache |
| `schwab://watchlist` | User-configured symbols with current quotes | 120s cache |

### MCP Prompts (Reusable Workflows)

| Prompt | Description | Tools Used |
|---|---|---|
| `morning_briefing` | Pre-market analysis: VIX, GEX levels, overnight moves, regime | vix_context + gex_levels + quotes |
| `iron_condor_scan` | Find optimal weekly SPX iron condors for current regime | gex_levels + find_iron_condors + volatility |
| `regime_check` | Quick regime assessment: are we in +GEX or -GEX? Trending or mean-reverting? | gex_levels + vix_context |
| `intraday_levels` | 0DTE levels + charm-adjusted projections for rest of day | 0dte_levels + charm_shift |

---

## GEX Calculation Pipeline

```mermaid
flowchart LR
    subgraph Input["Data Input"]
        OC[Options Chain<br/>from Schwab]
        SP[Spot Price]
    end

    subgraph Calc["Per-Strike Calculation"]
        direction TB
        F1["Call GEX = |Γ| × OI × 100 × S² × 0.01 × (+1)"]
        F2["Put GEX = |Γ| × OI × 100 × S² × 0.01 × (-1)"]
        F3["Net GEX = Call GEX + Put GEX"]
    end

    subgraph Levels["Level Extraction (0-45 DTE)"]
        direction TB
        L1[Call Wall — max call OI strike]
        L2[Put Wall — max put OI strike]
        L3[Zero Gamma — GEX sign flip<br/>linear interpolation]
        L4[Max Gamma — highest |GEX| strike]
        L5[HVL — highest total OI strike]
        L6[GEX 1-10 — top 10 by |GEX|]
    end

    subgraph Regime["Regime Classification"]
        direction TB
        R1{Spot vs Zero Gamma?}
        R2["+GEX Regime<br/>Mean-reverting<br/>Dealers dampen moves"]
        R3["-GEX Regime<br/>Trending<br/>Dealers amplify moves"]
    end

    OC --> Calc
    SP --> Calc
    F1 --> F3
    F2 --> F3
    Calc --> Levels
    Levels --> Regime
    R1 -->|Above| R2
    R1 -->|Below| R3

    style Input fill:#fff3e0
    style Calc fill:#e3f2fd
    style Levels fill:#e8f5e9
    style Regime fill:#fce4ec
```

---

## Project Structure

```
thinkorswim_local_mcp/
├── docs/
│   ├── ARCHITECTURE.md          # This file
│   ├── SCHWAB_API_REFERENCE.md  # API endpoints, limits, data fields
│   └── TOOLS_REFERENCE.md       # Detailed MCP tool specifications
│
├── src/
│   ├── server.py                # MCP server entry point (stdio transport)
│   │
│   ├── tools/                   # MCP tool handlers
│   │   ├── __init__.py
│   │   ├── market_data.py       # Quotes, chains, history, movers, hours
│   │   ├── gex.py               # GEX levels, summary, 0DTE, projections
│   │   ├── volatility.py        # IV analysis, skew, term structure, surface
│   │   └── strategy.py          # Spreads, iron condors, regime, alerts
│   │
│   ├── core/                    # Business logic (ported from gex-tool)
│   │   ├── __init__.py
│   │   ├── gex_calculator.py    # GEX formula, per-strike calc, aggregates
│   │   ├── gex_levels.py        # Level extraction, zero gamma, walls
│   │   ├── volatility.py        # IV skew, butterfly, term structure
│   │   ├── iv_context.py        # IV percentile, rank, realized vol
│   │   ├── vix_context.py       # VIX regime, percentile, term structure
│   │   └── strategy_engine.py   # Regime signals, trade evaluation, POP
│   │
│   ├── data/                    # Data access layer
│   │   ├── __init__.py
│   │   ├── schwab_client.py     # Schwab API wrapper (schwab-py)
│   │   ├── cache.py             # Disk cache with per-range TTL
│   │   ├── models.py            # Data models (OptionContract, Chain, etc.)
│   │   └── token_manager.py     # OAuth 2.0 token lifecycle
│   │
│   ├── resources/               # MCP resource handlers
│   │   ├── __init__.py
│   │   └── market_resources.py  # Market status, VIX dashboard, watchlist
│   │
│   └── prompts/                 # MCP prompt templates
│       ├── __init__.py
│       └── workflows.py         # morning_briefing, iron_condor_scan, etc.
│
├── tests/
│   ├── test_gex_calculator.py
│   ├── test_gex_levels.py
│   ├── test_schwab_client.py
│   └── test_tools.py
│
├── .env.example                 # Configuration template
├── pyproject.toml               # Python package config
├── requirements.txt             # Dependencies
└── README.md
```

---

## Module Dependency Graph

```mermaid
graph TD
    SERVER[server.py<br/>MCP Entry Point] --> TOOLS_MD[tools/market_data.py]
    SERVER --> TOOLS_GEX[tools/gex.py]
    SERVER --> TOOLS_VOL[tools/volatility.py]
    SERVER --> TOOLS_STRAT[tools/strategy.py]
    SERVER --> RES[resources/market_resources.py]
    SERVER --> PROMPTS[prompts/workflows.py]

    TOOLS_MD --> CLIENT[data/schwab_client.py]
    TOOLS_GEX --> GCALC[core/gex_calculator.py]
    TOOLS_GEX --> GLEV[core/gex_levels.py]
    TOOLS_VOL --> CVOL[core/volatility.py]
    TOOLS_VOL --> IVC[core/iv_context.py]
    TOOLS_STRAT --> STRAT[core/strategy_engine.py]
    TOOLS_STRAT --> GCALC

    RES --> CLIENT
    RES --> VIX[core/vix_context.py]
    PROMPTS --> TOOLS_MD
    PROMPTS --> TOOLS_GEX

    GCALC --> CLIENT
    GCALC --> MODELS[data/models.py]
    GLEV --> GCALC
    CVOL --> CLIENT
    IVC --> CLIENT
    VIX --> CLIENT
    STRAT --> GCALC
    STRAT --> GLEV
    STRAT --> CVOL

    CLIENT --> CACHE[data/cache.py]
    CLIENT --> TOKEN[data/token_manager.py]

    style SERVER fill:#4a6cf7,color:#fff
    style TOOLS_MD fill:#66bb6a,color:#fff
    style TOOLS_GEX fill:#66bb6a,color:#fff
    style TOOLS_VOL fill:#66bb6a,color:#fff
    style TOOLS_STRAT fill:#66bb6a,color:#fff
    style RES fill:#ffa726,color:#fff
    style PROMPTS fill:#ef5350,color:#fff
    style GCALC fill:#42a5f5,color:#fff
    style GLEV fill:#42a5f5,color:#fff
    style CVOL fill:#42a5f5,color:#fff
    style IVC fill:#42a5f5,color:#fff
    style VIX fill:#42a5f5,color:#fff
    style STRAT fill:#42a5f5,color:#fff
    style CLIENT fill:#ab47bc,color:#fff
    style CACHE fill:#ab47bc,color:#fff
    style TOKEN fill:#ab47bc,color:#fff
    style MODELS fill:#ab47bc,color:#fff
```

---

## Schwab API Rate Limits & Caching Strategy

```mermaid
graph LR
    subgraph Limits["Schwab API Limits"]
        L1["120 requests/minute"]
        L2["Access token: 30 min"]
        L3["Refresh token: 7 days"]
        L4["Then full re-auth required"]
    end

    subgraph Cache["Smart Cache (per DTE range)"]
        C1["0-7 DTE → 60s TTL<br/>(near-term gamma changes fast)"]
        C2["8-45 DTE → 120s TTL<br/>(moderate refresh)"]
        C3["46-180 DTE → 300s TTL<br/>(slow-changing)"]
        C4["181-730 DTE → 300s TTL<br/>(LEAPs, very slow)"]
    end

    subgraph Quotes["Quote Cache"]
        Q1["Equity quotes → 15s TTL"]
        Q2["VIX quote → 30s TTL"]
        Q3["Futures quotes → 15s TTL"]
    end

    Limits --> Cache
    Limits --> Quotes

    style Limits fill:#ffcdd2
    style Cache fill:#c8e6c9
    style Quotes fill:#bbdefb
```

**Budget at 120 req/min:**
- Full SPX chain fetch (4 DTE ranges) = 4 requests
- VIX + VIX3M quotes = 2 requests
- SPX underlying quote = 1 request
- Total per full refresh = ~7 requests
- Comfortable headroom for additional symbols and ad-hoc queries

---

## Authentication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as MCP Server
    participant T as Token Manager
    participant S as Schwab OAuth

    Note over M,T: First-time setup
    M->>T: Check for saved tokens
    alt No tokens found
        T->>U: Open browser for Schwab login
        U->>S: Login + authorize app
        S->>T: Redirect with auth code
        T->>S: Exchange code for tokens
        S-->>T: access_token (30min) + refresh_token (7d)
        T->>T: Save tokens to disk
    end

    Note over M,T: Normal operation
    M->>T: Get access token
    alt Token valid
        T-->>M: Return access_token
    else Token expired (< 30min)
        T->>S: POST /token (refresh_token)
        S-->>T: New access_token + refresh_token
        T->>T: Save updated tokens
        T-->>M: Return new access_token
    else Refresh token expired (> 7d)
        T->>U: ⚠️ Re-authentication required
        Note over U,S: User must login again
    end
```

---

## Alert System Design

Since MCP servers are **request-driven** (not persistent daemons), alerts work as a **condition evaluation engine**:

```mermaid
flowchart TB
    subgraph Config["Alert Configuration (user-defined)"]
        A1["GEX flip: notify when regime changes +/−"]
        A2["IV rank threshold: IV_rank > 50"]
        A3["VIX spike: VIX > 25 or +3 in session"]
        A4["Wall breach: spot crosses call/put wall"]
        A5["0DTE gamma surge: 0DTE GEX > 50% of total"]
    end

    subgraph Check["check_alerts tool"]
        E1[Load alert conditions]
        E2[Fetch current market data]
        E3[Evaluate each condition]
        E4[Return triggered alerts with context]
    end

    subgraph Storage["Alert State (disk)"]
        S1[Previous GEX regime]
        S2[Previous VIX level]
        S3[Last check timestamp]
        S4[Alert history log]
    end

    Config --> Check
    Check --> Storage
    E1 --> E2 --> E3 --> E4

    style Config fill:#fff3e0
    style Check fill:#e8f5e9
    style Storage fill:#e3f2fd
```

**How it works in practice:**
1. User tells Claude: *"Watch SPX for a GEX flip or if VIX spikes above 25"*
2. Claude calls `check_alerts` — conditions are saved to disk
3. Each time user chats with Claude, the `morning_briefing` prompt or manual `check_alerts` evaluates conditions
4. Claude reports: *"Alert: SPX GEX flipped negative at 11:42 AM. Zero gamma now at 5,180. Consider tightening your short strikes."*

---

## Strategy Engine — Iron Condor Workflow

```mermaid
flowchart TB
    Start[User: Find me a weekly SPX iron condor] --> GEX[Get GEX levels]
    GEX --> Regime{GEX Regime?}

    Regime -->|+GEX Mean-reverting| Wide["Wider wings OK<br/>Sell closer to ATM<br/>Higher premium"]
    Regime -->|-GEX Trending| Narrow["Narrower wings<br/>Sell further OTM<br/>Lower premium, safer"]

    Wide --> IV[Check IV context]
    Narrow --> IV

    IV --> IVH{IV Rank?}
    IVH -->|High > 50| Sell["Favorable for selling premium<br/>Target higher credit"]
    IVH -->|Low < 30| Caution["Low IV = low premium<br/>Consider skipping or going wider"]

    Sell --> Scan[Scan options chain]
    Caution --> Scan

    Scan --> Filter["Filter by:<br/>• Delta (short strikes 10-16Δ)<br/>• Width (25-50 pts for SPX)<br/>• Min credit target<br/>• DTE (4-7 days)"]

    Filter --> Walls["Check against GEX levels:<br/>• Short call below call wall<br/>• Short put above put wall<br/>• Both outside zero gamma"]

    Walls --> Rank["Rank candidates by:<br/>• Credit/width ratio<br/>• POP (probability of profit)<br/>• Distance from GEX walls<br/>• Risk/reward"]

    Rank --> Output["Return top 3 candidates<br/>with full analysis"]

    style Start fill:#f0f4ff,stroke:#4a6cf7
    style Wide fill:#c8e6c9
    style Narrow fill:#ffcdd2
    style Sell fill:#c8e6c9
    style Caution fill:#fff3e0
    style Output fill:#e3f2fd
```

---

## Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.11+ | MCP SDK support, your existing GEX tool is Python |
| **MCP SDK** | `mcp` (official Python SDK) | First-party, stable, stdio transport |
| **Schwab Client** | `schwab-py` | Most mature Python wrapper, auto token refresh |
| **Cache** | `diskcache` | Same as gex-tool, fast, reliable |
| **Data Models** | `pydantic` | Validation, serialization, type safety |
| **Math** | `numpy` | GEX calculations, interpolation |
| **Testing** | `pytest` | Standard, mock-friendly |
| **Config** | `.env` + `python-dotenv` | Simple, proven pattern from gex-tool |

### Dependencies

```
mcp>=1.0.0
schwab-py>=1.0.0
pydantic>=2.0
numpy>=1.24
diskcache>=5.6
python-dotenv>=1.0
httpx>=0.24
```

---

## Configuration

```env
# Schwab API Credentials
SCHWAB_APP_KEY=your_app_key
SCHWAB_APP_SECRET=your_app_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182

# Token Storage
TOKEN_PATH=./tokens/schwab_tokens.json

# Default Settings
DEFAULT_SYMBOL=SPX
MAX_DTE=730
GEX_LEVEL_MAX_DTE=45

# Cache Settings
CACHE_DIRECTORY=./cache
DTE_RANGES=0-7,8-45,46-180,181-730
DTE_RANGE_CACHE_TTLS=60,120,300,300
QUOTE_CACHE_TTL=15

# Alert State
ALERT_STATE_PATH=./state/alerts.json
```

---

## Claude Desktop Integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "schwab-options": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/thinkorswim_local_mcp",
      "env": {
        "SCHWAB_APP_KEY": "your_key",
        "SCHWAB_APP_SECRET": "your_secret"
      }
    }
  }
}
```

---

## What Gets Ported from gex-tool-thinkorswim

| gex-tool Module | MCP Module | What Changes |
|---|---|---|
| `src/gex/calculator.py` | `src/core/gex_calculator.py` | Minimal — core math stays the same |
| `src/gex/levels.py` | `src/core/gex_levels.py` | Minimal — level extraction logic stays |
| `src/levels/extractor.py` | `src/core/gex_levels.py` | Merged into single module |
| `src/gex/volatility.py` | `src/core/volatility.py` | Minimal |
| `src/gex/iv_context.py` | `src/core/iv_context.py` | Minimal |
| `src/data/vix_context.py` | `src/core/vix_context.py` | Minimal |
| `src/data/schwab_fetcher.py` | `src/data/schwab_client.py` | Refactored to use schwab-py |
| `src/data/cache_manager.py` | `src/data/cache.py` | Same pattern, simplified |
| `src/data/data_models.py` | `src/data/models.py` | Pydantic v2 models |
| `src/web/strategy.py` | `src/core/strategy_engine.py` | Decoupled from web, enhanced for MCP |
| `src/web/app.py` | **Removed** | MCP replaces the web dashboard |
| `src/export/` | **Removed** | Claude formats output directly |
| `src/auth/` | `src/data/token_manager.py` | Simplified, schwab-py handles most of it |

---

## Phase Plan

### Phase 1 — Foundation
- Project setup (pyproject.toml, deps, structure)
- Token manager + Schwab client with caching
- Basic MCP server with `get_quote` and `get_options_chain` tools
- Test with Claude Desktop

### Phase 2 — GEX Engine
- Port GEX calculator from gex-tool
- Port level extraction (walls, zero gamma, HVL, max gamma)
- `get_gex_levels`, `get_gex_summary`, `get_0dte_levels` tools
- Charm/vanna projection tools

### Phase 3 — Volatility & Context
- Port IV analysis (skew, term structure, IV-RV)
- Port VIX context
- `analyze_volatility`, `get_vix_context`, `get_iv_surface` tools
- MCP resources (market status, VIX dashboard, GEX regime)

### Phase 4 — Strategy & Trading
- Strategy engine: regime signals, directional bias
- Iron condor scanner with GEX-aware strike selection
- Spread finder (credit spreads, calendars)
- Trade evaluator (POP, max profit/loss, breakevens)
- Alert condition engine

### Phase 5 — Prompts & Polish
- MCP prompts (morning briefing, iron condor scan, regime check)
- Futures and futures options support
- Error handling hardening
- Documentation and tests
