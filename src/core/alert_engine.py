"""Alert condition engine — persistence, evaluation, and state management.

Conditions are persisted as JSON on disk. Evaluation compares current market
data against thresholds or previous state to determine triggered/clear status.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.shared.logging import get_logger

logger = get_logger(__name__)


class AlertEngine:
    """Manages alert conditions with JSON state persistence."""

    def __init__(self, state_dir: str = "./state") -> None:
        self._state_dir = state_dir
        self._state_path = Path(state_dir) / "alerts.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load state from disk or return default."""
        if self._state_path.exists():
            with open(self._state_path) as f:
                return json.load(f)
        return {
            "conditions": [],
            "previous_state": {},
        }

    def _save_state(self) -> None:
        """Persist state to disk."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w") as f:
            json.dump(self._state, f, indent=2, default=str)

    def add(self, condition: dict) -> dict:
        """Add a new alert condition. Returns dict with assigned ID."""
        cond_id = uuid.uuid4().hex[:8]
        entry = {
            "id": cond_id,
            "type": condition["type"],
            "symbol": condition.get("symbol"),
            "threshold": condition.get("threshold"),
            "wall": condition.get("wall"),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._state["conditions"].append(entry)
        self._save_state()
        logger.info("Added alert condition: %s (%s)", cond_id, condition["type"])
        return {"id": cond_id}

    def remove(self, cond_id: str) -> bool:
        """Remove a condition by ID. Returns True if found and removed."""
        before = len(self._state["conditions"])
        self._state["conditions"] = [
            c for c in self._state["conditions"] if c["id"] != cond_id
        ]
        removed = len(self._state["conditions"]) < before
        if removed:
            self._save_state()
            logger.info("Removed alert condition: %s", cond_id)
        return removed

    def list_conditions(self) -> list[dict]:
        """Return all active conditions."""
        return self._state["conditions"]

    def update_previous_state(self, key: str, value: object) -> None:
        """Update a previous state value for stateful comparisons."""
        self._state["previous_state"][key] = value
        self._save_state()

    def get_previous_state(self, key: str) -> object:
        """Get a previous state value."""
        return self._state["previous_state"].get(key)

    def evaluate(self, market_data: dict) -> list[dict]:
        """Evaluate all conditions against current market data.

        Returns list of results with status ('triggered' or 'clear').
        """
        results = []
        for cond in self._state["conditions"]:
            result = self._evaluate_one(cond, market_data)
            results.append(result)
        return results

    def _evaluate_one(self, cond: dict, market_data: dict) -> dict:
        """Evaluate a single condition against market data."""
        cond_type = cond["type"]
        symbol = cond.get("symbol")
        threshold = cond.get("threshold")

        if cond_type == "vix_above":
            current = market_data.get("vix_level")
            triggered = current is not None and current > threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "vix_below":
            current = market_data.get("vix_level")
            triggered = current is not None and current < threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "price_above":
            current = market_data.get(f"{symbol}_price")
            triggered = current is not None and current > threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "price_below":
            current = market_data.get(f"{symbol}_price")
            triggered = current is not None and current < threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "gex_flip":
            current = market_data.get(f"{symbol}_gex_regime")
            previous = self.get_previous_state(f"{symbol}_gex_regime")
            triggered = previous is not None and current != previous
            return _result(cond, triggered, current_value=current, previous_value=previous)

        if cond_type == "wall_breach":
            wall_type = cond.get("wall", "call")
            price = market_data.get(f"{symbol}_price")
            wall = market_data.get(f"{symbol}_{wall_type}_wall")
            if wall_type == "call":
                triggered = price is not None and wall is not None and price > wall
            else:
                triggered = price is not None and wall is not None and price < wall
            return _result(cond, triggered, current_value=price)

        if cond_type == "iv_rank_above":
            current = market_data.get(f"{symbol}_iv_rank")
            triggered = current is not None and current > threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "iv_rank_below":
            current = market_data.get(f"{symbol}_iv_rank")
            triggered = current is not None and current < threshold
            return _result(cond, triggered, current_value=current)

        if cond_type == "expected_move_breach":
            price = market_data.get(f"{symbol}_price")
            upper = market_data.get(f"{symbol}_expected_move_upper")
            lower = market_data.get(f"{symbol}_expected_move_lower")
            triggered = (
                price is not None
                and upper is not None
                and lower is not None
                and (price > upper or price < lower)
            )
            return _result(cond, triggered, current_value=price)

        return _result(cond, False, details=f"Unknown condition type: {cond_type}")


def _result(
    cond: dict,
    triggered: bool,
    current_value: object = None,
    previous_value: object = None,
    details: str | None = None,
) -> dict:
    """Build a standardized evaluation result."""
    return {
        "condition": cond,
        "status": "triggered" if triggered else "clear",
        "current_value": current_value,
        "previous_value": previous_value,
        "details": details,
    }
