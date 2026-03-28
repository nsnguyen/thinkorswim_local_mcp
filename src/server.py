"""MCP server entry point — Schwab Options MCP Server."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.data.cache import CacheManager
from src.data.schwab_client import SchwabClient
from src.data.token_manager import TokenManager
from src.tools.market_data import register_tools

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────

APP_KEY = os.environ.get("SCHWAB_APP_KEY", "")
APP_SECRET = os.environ.get("SCHWAB_APP_SECRET", "")
CALLBACK_URL = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
TOKEN_PATH = os.environ.get("TOKEN_PATH", "./tokens/schwab_tokens.db")
CACHE_DIR = os.environ.get("CACHE_DIRECTORY", "./cache")

# ── Initialize components ──────────────────────────────────────────

token_manager = TokenManager(
    app_key=APP_KEY,
    app_secret=APP_SECRET,
    callback_url=CALLBACK_URL,
    token_path=TOKEN_PATH,
)

cache = CacheManager(cache_dir=CACHE_DIR)

schwab_client = SchwabClient(
    token_manager=token_manager,
    cache=cache,
)

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
register_tools(mcp, schwab_client)

# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Schwab Options MCP Server (stdio)")
    mcp.run("stdio")
