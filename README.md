# Schwab Options MCP Server

An MCP (Model Context Protocol) server that gives Claude access to Charles Schwab market data for options trading analysis. Designed for premium selling strategies — weekly SPX iron condors, credit spreads, and GEX-based regime detection.

**MCP = calculator. Claude = analyst.** The server fetches data and does math. Claude interprets and makes trading decisions.

## Quick Start

### 1. Configure

```bash
bash scripts/start.sh
```

On first run this creates a virtual environment, installs dependencies, and copies `.env.example` to `.env`. Edit `.env` with your [Schwab Developer](https://developer.schwab.com/) API credentials:

```env
SCHWAB_APP_KEY=your_app_key
SCHWAB_APP_SECRET=your_app_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
```

### 2. Authenticate

```bash
.venv/bin/python scripts/authenticate.py
```

Opens your browser to Schwab's login page. After you log in, the script auto-captures the OAuth callback — no copy-paste needed. Tokens are saved locally and auto-refresh for 7 days.

### 3. Start the Server

```bash
bash scripts/start.sh
```

Subsequent runs skip setup and start the server directly.

### 4. Connect Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "schwab-options": {
      "command": "/absolute/path/to/thinkorswim_local_mcp/.venv/bin/python",
      "args": ["-m", "src"],
      "cwd": "/absolute/path/to/thinkorswim_local_mcp"
    }
  }
}
```

Replace `/absolute/path/to/thinkorswim_local_mcp` with the actual path to this project.

## Available Tools

| Tool | Description |
|------|-------------|
| `get_quote` | Real-time quote for any symbol (equity, index, futures, VIX) |
| `get_options_chain` | Full options chain with greeks, OI, volume. Multi-range DTE caching. |

## Re-authentication

The Schwab refresh token expires every 7 days. When it does, Claude will tell you. Just re-run:

```bash
.venv/bin/python scripts/authenticate.py
```

## Project Structure

```
src/
├── server.py                 # MCP server entry point (stdio)
├── tools/
│   └── market_data.py        # get_quote, get_options_chain
└── data/
    ├── models.py              # Pydantic v2 data models
    ├── cache.py               # Disk cache with per-DTE-range TTL
    ├── schwab_client.py       # Schwab API wrapper
    └── token_manager.py       # OAuth 2.0 token lifecycle

scripts/
├── start.sh                   # Setup (if needed) + start the MCP server
└── authenticate.py            # One-time Schwab OAuth login
```

## Requirements

- Python 3.11+
- Schwab Developer API account
