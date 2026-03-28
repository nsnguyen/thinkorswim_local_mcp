"""MCP server entry point — Schwab Options MCP Server."""

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.core.snapshot_store import SnapshotStore
from src.data.cache import CacheManager
from src.data.schwab_client import SchwabClient
from src.data.token_manager import TokenManager
from src.shared.logging import get_logger, setup_logging
from src.tools.gex import register_tools as register_gex_tools
from src.tools.history import register_tools as register_history_tools
from src.tools.market_data import register_tools as register_market_data_tools
from src.tools.volatility import register_tools as register_volatility_tools

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

setup_logging()
logger = get_logger(__name__)

# ── Configuration ───────────────────────────────────────────────────

APP_KEY = os.environ.get("SCHWAB_APP_KEY", "")
APP_SECRET = os.environ.get("SCHWAB_APP_SECRET", "")
CALLBACK_URL = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
TOKEN_PATH = os.environ.get("TOKEN_PATH", "./tokens/schwab_tokens.db")
CACHE_DIR = os.environ.get("CACHE_DIRECTORY", "./cache")
SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIRECTORY", "./data/snapshots")
QUOTE_CACHE_TTL = int(os.environ.get("QUOTE_CACHE_TTL", "5"))

# ── Initialize components ──────────────────────────────────────────

token_manager = TokenManager(
    app_key=APP_KEY,
    app_secret=APP_SECRET,
    callback_url=CALLBACK_URL,
    token_path=TOKEN_PATH,
)

cache = CacheManager(cache_dir=CACHE_DIR, quote_ttl=QUOTE_CACHE_TTL)

schwab_client = SchwabClient(
    token_manager=token_manager,
    cache=cache,
)

snapshot_store = SnapshotStore(base_dir=SNAPSHOT_DIR)

# ── Create MCP server ──────────────────────────────────────────────

mcp = FastMCP(
    "schwab-options",
    instructions=(
        "Schwab Options MCP Server — provides real-time market data, "
        "options chains with greeks, and GEX analysis for options trading. "
        "Use get_quote for price data and get_options_chain for full chain data."
    ),
)

# Register tool modules
register_market_data_tools(mcp, schwab_client)
register_gex_tools(mcp, schwab_client)
register_volatility_tools(mcp, schwab_client)
register_history_tools(mcp, schwab_client, snapshot_store)

# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Schwab Options MCP Server (stdio)")
    mcp.run("stdio")
