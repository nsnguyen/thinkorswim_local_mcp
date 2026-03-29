"""Tests for alert_engine — condition persistence, evaluation, and state management.

All state operations use tmp_path to avoid polluting the real filesystem.
"""


import pytest

from src.core.alert_engine import AlertEngine

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def engine(tmp_path) -> AlertEngine:
    """Create an AlertEngine with a temp state directory."""
    return AlertEngine(state_dir=str(tmp_path / "state"))


def _condition(
    cond_type: str = "vix_above",
    symbol: str | None = None,
    threshold: float | None = 20.0,
    wall: str | None = None,
) -> dict:
    """Build a condition dict for testing."""
    return {
        "type": cond_type,
        "symbol": symbol,
        "threshold": threshold,
        "wall": wall,
    }


# ── Add / Remove / List ───────────────────────────────────────────


class TestAddCondition:
    """Test adding alert conditions."""

    def test_add_returns_id(self, engine: AlertEngine) -> None:
        """Adding a condition should return a unique ID.

        Without an ID, we can't remove specific conditions later.
        """
        result = engine.add(_condition("vix_above", threshold=20.0))
        assert "id" in result
        assert len(result["id"]) > 0

    def test_add_persists_to_disk(self, engine: AlertEngine) -> None:
        """Conditions must survive engine restart.

        Alert state must persist across MCP server restarts.
        """
        engine.add(_condition("vix_above", threshold=25.0))

        # Create new engine pointing to same directory
        engine2 = AlertEngine(state_dir=engine._state_dir)
        conditions = engine2.list_conditions()
        assert len(conditions) == 1
        assert conditions[0]["type"] == "vix_above"
        assert conditions[0]["threshold"] == 25.0

    def test_add_multiple(self, engine: AlertEngine) -> None:
        """Can add multiple conditions."""
        engine.add(_condition("vix_above", threshold=20.0))
        engine.add(_condition("vix_below", threshold=12.0))
        engine.add(_condition("price_above", symbol="SPX", threshold=6000.0))
        assert len(engine.list_conditions()) == 3


class TestRemoveCondition:
    """Test removing alert conditions."""

    def test_remove_by_id(self, engine: AlertEngine) -> None:
        """Remove a specific condition by ID.

        Users need to clean up stale alerts.
        """
        result = engine.add(_condition("vix_above", threshold=20.0))
        cond_id = result["id"]
        engine.remove(cond_id)
        assert len(engine.list_conditions()) == 0

    def test_remove_nonexistent_returns_false(self, engine: AlertEngine) -> None:
        """Removing a nonexistent ID should return False, not crash."""
        assert engine.remove("nonexistent_id") is False

    def test_remove_persists(self, engine: AlertEngine) -> None:
        """Removal must persist to disk."""
        result = engine.add(_condition("vix_above", threshold=20.0))
        engine.remove(result["id"])

        engine2 = AlertEngine(state_dir=engine._state_dir)
        assert len(engine2.list_conditions()) == 0


class TestListConditions:
    """Test listing alert conditions."""

    def test_empty(self, engine: AlertEngine) -> None:
        """No conditions → empty list."""
        assert engine.list_conditions() == []

    def test_returns_all_fields(self, engine: AlertEngine) -> None:
        """Listed conditions must have all fields."""
        engine.add(_condition("wall_breach", symbol="SPX", wall="call"))
        conditions = engine.list_conditions()
        assert conditions[0]["type"] == "wall_breach"
        assert conditions[0]["symbol"] == "SPX"
        assert conditions[0]["wall"] == "call"
        assert "id" in conditions[0]
        assert "created_at" in conditions[0]


# ── Condition Evaluation ───────────────────────────────────────────


class TestEvaluateConditions:
    """Test evaluating alert conditions against current market data."""

    def test_vix_above_triggered(self, engine: AlertEngine) -> None:
        """VIX above threshold → triggered.

        Core alert type — if VIX spikes, Claude needs to know.
        """
        engine.add(_condition("vix_above", threshold=20.0))
        market_data = {"vix_level": 22.5}
        results = engine.evaluate(market_data)
        assert len(results) == 1
        assert results[0]["status"] == "triggered"
        assert results[0]["current_value"] == 22.5

    def test_vix_above_clear(self, engine: AlertEngine) -> None:
        """VIX below threshold → clear."""
        engine.add(_condition("vix_above", threshold=20.0))
        market_data = {"vix_level": 18.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "clear"

    def test_vix_below_triggered(self, engine: AlertEngine) -> None:
        """VIX below threshold → triggered."""
        engine.add(_condition("vix_below", threshold=12.0))
        market_data = {"vix_level": 10.5}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_price_above_triggered(self, engine: AlertEngine) -> None:
        """Price above level → triggered."""
        engine.add(_condition("price_above", symbol="SPX", threshold=6000.0))
        market_data = {"SPX_price": 6050.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_price_below_triggered(self, engine: AlertEngine) -> None:
        """Price below level → triggered."""
        engine.add(_condition("price_below", symbol="SPX", threshold=5800.0))
        market_data = {"SPX_price": 5750.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_gex_flip_triggered(self, engine: AlertEngine) -> None:
        """GEX regime changed since last check → triggered."""
        engine.add(_condition("gex_flip", symbol="SPX"))
        engine.update_previous_state("SPX_gex_regime", "positive")
        market_data = {"SPX_gex_regime": "negative"}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"
        assert results[0]["previous_value"] == "positive"

    def test_gex_flip_clear(self, engine: AlertEngine) -> None:
        """GEX regime unchanged → clear."""
        engine.add(_condition("gex_flip", symbol="SPX"))
        engine.update_previous_state("SPX_gex_regime", "positive")
        market_data = {"SPX_gex_regime": "positive"}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "clear"

    def test_wall_breach_triggered(self, engine: AlertEngine) -> None:
        """Spot crosses call wall → triggered."""
        engine.add(_condition("wall_breach", symbol="SPX", wall="call"))
        market_data = {"SPX_price": 5950.0, "SPX_call_wall": 5900.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_wall_breach_clear(self, engine: AlertEngine) -> None:
        """Spot below call wall → clear."""
        engine.add(_condition("wall_breach", symbol="SPX", wall="call"))
        market_data = {"SPX_price": 5850.0, "SPX_call_wall": 5900.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "clear"

    def test_put_wall_breach(self, engine: AlertEngine) -> None:
        """Spot crosses below put wall → triggered."""
        engine.add(_condition("wall_breach", symbol="SPX", wall="put"))
        market_data = {"SPX_price": 5050.0, "SPX_put_wall": 5100.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_iv_rank_above_triggered(self, engine: AlertEngine) -> None:
        """IV rank above threshold → triggered."""
        engine.add(_condition("iv_rank_above", symbol="SPX", threshold=80.0))
        market_data = {"SPX_iv_rank": 85.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_iv_rank_below_triggered(self, engine: AlertEngine) -> None:
        """IV rank below threshold → triggered."""
        engine.add(_condition("iv_rank_below", symbol="SPX", threshold=20.0))
        market_data = {"SPX_iv_rank": 15.0}
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_expected_move_breach_triggered(self, engine: AlertEngine) -> None:
        """Spot outside expected move range → triggered."""
        engine.add(_condition("expected_move_breach", symbol="SPX"))
        market_data = {
            "SPX_price": 6050.0,
            "SPX_expected_move_upper": 6000.0,
            "SPX_expected_move_lower": 5800.0,
        }
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "triggered"

    def test_expected_move_within(self, engine: AlertEngine) -> None:
        """Spot within expected move range → clear."""
        engine.add(_condition("expected_move_breach", symbol="SPX"))
        market_data = {
            "SPX_price": 5900.0,
            "SPX_expected_move_upper": 6000.0,
            "SPX_expected_move_lower": 5800.0,
        }
        results = engine.evaluate(market_data)
        assert results[0]["status"] == "clear"

    def test_multiple_conditions(self, engine: AlertEngine) -> None:
        """Multiple conditions evaluated at once."""
        engine.add(_condition("vix_above", threshold=20.0))
        engine.add(_condition("vix_below", threshold=12.0))
        market_data = {"vix_level": 22.0}
        results = engine.evaluate(market_data)
        assert len(results) == 2
        statuses = {r["condition"]["type"]: r["status"] for r in results}
        assert statuses["vix_above"] == "triggered"
        assert statuses["vix_below"] == "clear"


class TestPreviousState:
    """Test previous state persistence for stateful alerts."""

    def test_state_persists(self, engine: AlertEngine) -> None:
        """Previous state must survive restart for gex_flip to work."""
        engine.update_previous_state("SPX_gex_regime", "positive")

        engine2 = AlertEngine(state_dir=engine._state_dir)
        assert engine2.get_previous_state("SPX_gex_regime") == "positive"

    def test_state_updates(self, engine: AlertEngine) -> None:
        """State should update after evaluation."""
        engine.update_previous_state("key", "old_value")
        engine.update_previous_state("key", "new_value")
        assert engine.get_previous_state("key") == "new_value"
