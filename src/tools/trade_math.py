"""MCP tools for trade evaluation and alert management."""

from datetime import date

from mcp.server.fastmcp import FastMCP

from src.core.alert_engine import AlertEngine
from src.core.trade_math import (
    calculate_breakevens,
    calculate_max_profit_loss,
    calculate_net_credit,
    calculate_net_greeks,
    calculate_pop,
    detect_strategy,
)
from src.data.models import (
    AlertCheckResult,
    AlertCondition,
    AlertResult,
    TradeEvaluation,
    TradeLeg,
)
from src.data.schwab_client import SchwabClient


def _match_legs_to_chain(
    legs: list[dict],
    calls: list,
    puts: list,
    spot: float,
) -> list[dict]:
    """Match user-specified legs to actual chain contracts for pricing/greeks."""
    enriched = []
    for leg in legs:
        strike = leg["strike"]
        opt_type = leg["option_type"].upper()
        exp_str = leg["expiration"]
        exp = date.fromisoformat(exp_str) if isinstance(exp_str, str) else exp_str
        action = leg["action"].upper()
        quantity = leg.get("quantity", 1)

        contracts = calls if opt_type == "CALL" else puts
        matched = None
        for c in contracts:
            if abs(c.strike_price - strike) < 0.01 and c.expiration_date == exp:
                matched = c
                break

        if matched is None:
            # Use leg values as-is with defaults
            enriched.append({
                "strike": strike,
                "option_type": opt_type,
                "action": action,
                "expiration": exp,
                "quantity": quantity,
                "bid": leg.get("bid", 0.0),
                "ask": leg.get("ask", 0.0),
                "mark": leg.get("mark", 0.0),
                "delta": leg.get("delta", 0.0),
                "gamma": leg.get("gamma", 0.0),
                "theta": leg.get("theta", 0.0),
                "vega": leg.get("vega", 0.0),
                "iv": leg.get("iv", 0.20),
            })
        else:
            iv = matched.implied_volatility
            enriched.append({
                "strike": matched.strike_price,
                "option_type": opt_type,
                "action": action,
                "expiration": exp,
                "quantity": quantity,
                "bid": matched.bid,
                "ask": matched.ask,
                "mark": matched.mark,
                "delta": matched.delta,
                "gamma": matched.gamma,
                "theta": matched.theta,
                "vega": matched.vega,
                "iv": iv / 100 if iv > 1 else iv,
            })

    return enriched


def register_tools(
    mcp: FastMCP,
    schwab_client: SchwabClient,
    alert_engine: AlertEngine,
) -> None:
    """Register trade math tools with the MCP server."""

    @mcp.tool(
        name="evaluate_trade",
        description=(
            "Evaluate a multi-leg options trade: auto-detect strategy, compute P&L, "
            "probability of profit, breakevens, and net greeks. "
            "Legs format: [{strike, option_type (CALL/PUT), action (BUY/SELL), expiration}]"
        ),
    )
    def evaluate_trade(symbol: str = "SPX", legs: list[dict] | None = None) -> dict:
        """Evaluate a trade by matching legs to live chain data."""
        if not legs:
            return {"error": "No legs provided"}

        chain = schwab_client.get_options_chain(symbol, to_dte=90)
        spot = chain.underlying_price

        enriched = _match_legs_to_chain(legs, chain.call_contracts, chain.put_contracts, spot)

        strategy = detect_strategy(enriched)
        net_credit = calculate_net_credit(enriched)
        pnl = calculate_max_profit_loss(strategy, net_credit, enriched)
        breakevens = calculate_breakevens(strategy, net_credit, enriched)
        greeks = calculate_net_greeks(enriched)

        # Average IV and DTE for POP calculation
        avg_iv = sum(lg["iv"] for lg in enriched) / len(enriched)
        first_exp = enriched[0]["expiration"]
        dte_days = (first_exp - date.today()).days if isinstance(first_exp, date) else 30
        dte_years = max(dte_days, 1) / 365

        pop = calculate_pop(spot, breakevens, avg_iv, dte_years, strategy)

        # Expected value = POP * max_profit - (1-POP) * max_loss
        max_profit = pnl["max_profit"]
        max_loss = pnl["max_loss"]
        if max_profit == float("inf") or max_loss == float("inf"):
            ev = 0.0  # can't compute EV for unlimited risk/reward
        else:
            ev = pop * max_profit - (1 - pop) * max_loss

        # Risk/reward
        if max_loss > 0 and max_loss != float("inf") and max_profit != float("inf"):
            risk_reward = max_profit / max_loss
        else:
            risk_reward = 0.0

        result = TradeEvaluation(
            symbol=symbol,
            spot_price=spot,
            strategy_type=strategy,
            legs=[TradeLeg(
                strike=lg["strike"],
                option_type=lg["option_type"],
                action=lg["action"],
                expiration=lg["expiration"],
                quantity=lg.get("quantity", 1),
            ) for lg in enriched],
            net_credit=round(net_credit, 4),
            max_profit=round(max_profit, 2) if max_profit != float("inf") else float("inf"),
            max_loss=round(max_loss, 2) if max_loss != float("inf") else float("inf"),
            breakevens=[round(b, 2) for b in breakevens],
            pop=round(pop, 4),
            expected_value=round(ev, 2),
            risk_reward=round(risk_reward, 4),
            net_delta=greeks["net_delta"],
            net_gamma=greeks["net_gamma"],
            net_theta=greeks["net_theta"],
            net_vega=greeks["net_vega"],
        )
        return result.model_dump(mode="json")

    @mcp.tool(
        name="check_alerts",
        description=(
            "Manage and check alert conditions. Actions: "
            "'add' (add a new condition), 'remove' (remove by id), "
            "'list' (list all conditions), 'check' (evaluate all against current market data). "
            "Condition types: vix_above, vix_below, price_above, price_below, gex_flip, "
            "wall_breach, iv_rank_above, iv_rank_below, expected_move_breach."
        ),
    )
    def check_alerts(
        action: str = "check",
        condition: dict | None = None,
    ) -> dict:
        """Manage alert conditions and check them against market data."""
        if action == "add":
            if not condition:
                return {"action": "add", "message": "No condition provided"}
            result = alert_engine.add(condition)
            return AlertCheckResult(
                action="add",
                message=f"Added condition {result['id']} ({condition['type']})",
            ).model_dump(mode="json")

        if action == "remove":
            if not condition or "id" not in condition:
                return {"action": "remove", "message": "No condition ID provided"}
            removed = alert_engine.remove(condition["id"])
            return AlertCheckResult(
                action="remove",
                message=f"Removed: {removed}",
            ).model_dump(mode="json")

        if action == "list":
            conditions = alert_engine.list_conditions()
            return AlertCheckResult(
                action="list",
                conditions=[AlertCondition(**c) for c in conditions],
            ).model_dump(mode="json")

        if action == "check":
            # Gather market data from Schwab for all conditions
            market_data = _gather_market_data(schwab_client, alert_engine.list_conditions())
            results = alert_engine.evaluate(market_data)
            return AlertCheckResult(
                action="check",
                results=[AlertResult(**r) for r in results],
            ).model_dump(mode="json")

        return {"action": action, "message": f"Unknown action: {action}"}


def _gather_market_data(schwab_client: SchwabClient, conditions: list[dict]) -> dict:
    """Fetch current market data needed to evaluate alert conditions."""
    data: dict = {}
    symbols_needing_price: set[str] = set()

    for cond in conditions:
        cond_type = cond["type"]
        symbol = cond.get("symbol")

        if cond_type in ("vix_above", "vix_below") and "vix_level" not in data:
            quote = schwab_client.get_quote("$VIX")
            data["vix_level"] = quote.last_price

        if symbol and cond_type in (
            "price_above", "price_below", "wall_breach", "expected_move_breach",
        ):
            symbols_needing_price.add(symbol)

    for symbol in symbols_needing_price:
        chain = schwab_client.get_options_chain(symbol, to_dte=45)
        data[f"{symbol}_price"] = chain.underlying_price

    return data
