"""MCP Resources for Phase 5 — live market snapshots accessible by URI.

Resources are read-only data endpoints Claude can poll without a tool call.
They return JSON strings.
"""

import json
import os

from mcp.server.fastmcp import FastMCP

from src.data.schwab_client import SchwabClient
from src.shared.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_WATCHLIST = ["SPX", "SPY", "QQQ", "IWM", "/ES", "/NQ", "$VIX"]


def register_resources(mcp: FastMCP, schwab_client: SchwabClient) -> None:
    """Register MCP resources with the server."""

    @mcp.resource(
        "schwab://market-status",
        name="market-status",
        description="Current market open/closed status with session times and VIX level.",
        mime_type="application/json",
    )
    def market_status() -> str:
        """Return market hours + VIX as a compact JSON snapshot."""
        try:
            hours = schwab_client.get_market_hours("option")
        except Exception as e:
            logger.warning("market-status: market_hours failed: %s", e)
            hours = None

        try:
            vix_quote = schwab_client.get_quote("$VIX")
            vix_level = vix_quote.last
        except Exception as e:
            logger.warning("market-status: VIX quote failed: %s", e)
            vix_level = None

        return json.dumps({
            "is_open": hours.is_open if hours else None,
            "market": "option",
            "regular_start": hours.regular_start if hours else None,
            "regular_end": hours.regular_end if hours else None,
            "vix_level": vix_level,
        })

    @mcp.resource(
        "schwab://vix-dashboard",
        name="vix-dashboard",
        description="VIX and VIX3M levels with term structure ratio for volatility regime.",
        mime_type="application/json",
    )
    def vix_dashboard() -> str:
        """Return VIX + VIX3M snapshot as JSON."""
        try:
            vix = schwab_client.get_quote("$VIX")
            vix_level = vix.last
            vix_change = vix.net_change
        except Exception as e:
            logger.warning("vix-dashboard: VIX quote failed: %s", e)
            vix_level = None
            vix_change = None

        try:
            vix3m = schwab_client.get_quote("$VIX3M")
            vix3m_level = vix3m.last
        except Exception as e:
            logger.warning("vix-dashboard: VIX3M quote failed: %s", e)
            vix3m_level = None

        ratio = None
        shape = None
        if vix_level and vix3m_level and vix3m_level > 0:
            ratio = round(vix_level / vix3m_level, 4)
            if ratio < 0.9:
                shape = "contango"
            elif ratio > 1.05:
                shape = "backwardation"
            else:
                shape = "flat"

        return json.dumps({
            "vix_level": vix_level,
            "vix_change": vix_change,
            "vix3m_level": vix3m_level,
            "term_structure_ratio": ratio,
            "term_structure_shape": shape,
        })

    @mcp.resource(
        "schwab://gex-regime/{symbol}",
        name="gex-regime",
        description="Current GEX regime, zero gamma, call wall, and put wall for a symbol.",
        mime_type="application/json",
    )
    def gex_regime(symbol: str) -> str:
        """Return GEX regime snapshot for the given symbol as JSON."""
        from src.core.gex_calculator import calculate_per_strike_gex
        from src.core.gex_levels import extract_levels

        try:
            chain = schwab_client.get_options_chain(symbol, to_dte=45)
            strike_gex = calculate_per_strike_gex(
                chain.call_contracts, chain.put_contracts, chain.underlying_price
            )
            levels = extract_levels(strike_gex, chain.underlying_price)

            def _level_price(key: str) -> float | None:
                kl = levels.key_levels
                return kl.get(key, {}).get("price") if kl else None

            return json.dumps({
                "symbol": symbol,
                "spot_price": chain.underlying_price,
                "regime": levels.regime.type,
                "zero_gamma": _level_price("zero_gamma"),
                "call_wall": _level_price("call_wall"),
                "put_wall": _level_price("put_wall"),
            })
        except Exception as e:
            logger.warning("gex-regime: failed for %s: %s", symbol, e)
            return json.dumps({"symbol": symbol, "error": str(e)})

    @mcp.resource(
        "schwab://watchlist",
        name="watchlist",
        description=(
            "Configured list of tracked symbols. "
            "Set WATCHLIST env var (comma-separated) to customize."
        ),
        mime_type="application/json",
    )
    def watchlist() -> str:
        """Return the configured watchlist as JSON."""
        env_val = os.environ.get("WATCHLIST", "")
        if env_val:
            symbols = [s.strip() for s in env_val.split(",") if s.strip()]
        else:
            symbols = _DEFAULT_WATCHLIST
        return json.dumps({"symbols": symbols, "count": len(symbols)})
