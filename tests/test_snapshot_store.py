"""Tests for snapshot_store — Parquet-based daily snapshot storage.

Covers: save, load, query, deduplication, append, and metadata tracking.
All tests use tmp_path to avoid polluting the real filesystem.
"""

from datetime import date

import pytest

from src.core.snapshot_store import (
    SnapshotStore,
    compute_backwardation_events,
    compute_current_vs_history,
    compute_expected_move_accuracy,
    compute_iv_trend,
    compute_regime_streak,
    compute_vix_regime_history,
    compute_wall_movement,
    compute_zero_gamma_trend,
)

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path) -> SnapshotStore:
    """Create a SnapshotStore with a temp directory."""
    return SnapshotStore(base_dir=str(tmp_path / "snapshots"))


def _gex_row(
    d: date = date(2026, 3, 25),
    regime: str = "positive",
    zero_gamma: float = 5200.0,
    call_wall: float = 5300.0,
    put_wall: float = 5100.0,
    max_gamma: float = 5250.0,
    hvl: float = 5250.0,
    total_gex: float = 450_000_000.0,
    gross_gex: float = 600_000_000.0,
) -> dict:
    """Build a GEX snapshot row dict."""
    return {
        "date": d,
        "regime": regime,
        "zero_gamma": zero_gamma,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_gamma": max_gamma,
        "hvl": hvl,
        "total_gex": total_gex,
        "gross_gex": gross_gex,
    }


def _iv_row(
    d: date = date(2026, 3, 25),
    atm_iv: float = 14.5,
    skew_25d: float = 4.2,
    skew_regime: str = "normal_skew",
    term_structure_shape: str = "contango",
) -> dict:
    """Build an IV snapshot row dict."""
    return {
        "date": d,
        "atm_iv": atm_iv,
        "iv_percentile": None,
        "iv_rank": None,
        "realized_vol_20d": None,
        "iv_rv_premium": None,
        "skew_25d": skew_25d,
        "skew_regime": skew_regime,
        "term_structure_shape": term_structure_shape,
    }


def _vix_row(
    d: date = date(2026, 3, 25),
    vix_level: float = 18.5,
    vix_regime: str = "normal",
    vix3m: float = 19.2,
    vix_vix3m_ratio: float = 0.96,
    term_structure: str = "contango",
) -> dict:
    """Build a VIX snapshot row dict."""
    return {
        "date": d,
        "vix_level": vix_level,
        "vix_percentile": None,
        "vix_regime": vix_regime,
        "vix3m": vix3m,
        "vix_vix3m_ratio": vix_vix3m_ratio,
        "term_structure": term_structure,
    }


def _em_row(
    d: date = date(2026, 3, 25),
    expiration: date = date(2026, 3, 28),
    expected_move_straddle: float = 55.0,
    expected_move_1sd: float = 48.0,
    actual_move: float | None = None,
) -> dict:
    """Build an expected move snapshot row dict."""
    return {
        "date": d,
        "expiration": expiration,
        "expected_move_straddle": expected_move_straddle,
        "expected_move_1sd": expected_move_1sd,
        "actual_move": actual_move,
    }


# ── SnapshotStore: save & load ─────────────────────────────────────


class TestSaveAndLoad:
    """Test saving and loading snapshot rows."""

    def test_save_gex_creates_parquet(self, store: SnapshotStore) -> None:
        """Saving a GEX row should create the Parquet file on disk.

        Without this, no history would persist between sessions.
        """
        store.save("SPX", "gex", _gex_row())
        rows = store.load("SPX", "gex")
        assert len(rows) == 1
        assert rows[0]["regime"] == "positive"

    def test_save_iv_creates_parquet(self, store: SnapshotStore) -> None:
        """Saving an IV row should create the Parquet file on disk."""
        store.save("SPX", "iv", _iv_row())
        rows = store.load("SPX", "iv")
        assert len(rows) == 1
        assert rows[0]["atm_iv"] == 14.5

    def test_save_vix_creates_parquet(self, store: SnapshotStore) -> None:
        """Saving a VIX row should create the Parquet file on disk."""
        store.save("SPX", "vix", _vix_row())
        rows = store.load("SPX", "vix")
        assert len(rows) == 1
        assert rows[0]["vix_level"] == 18.5

    def test_save_expected_move_creates_parquet(self, store: SnapshotStore) -> None:
        """Saving an expected move row should create the Parquet file on disk."""
        store.save("SPX", "expected_move", _em_row())
        rows = store.load("SPX", "expected_move")
        assert len(rows) == 1
        assert rows[0]["expected_move_straddle"] == 55.0

    def test_append_multiple_days(self, store: SnapshotStore) -> None:
        """Multiple saves should append, not overwrite.

        History depends on accumulating daily snapshots over time.
        """
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 25)))
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 26)))
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 27)))
        rows = store.load("SPX", "gex")
        assert len(rows) == 3

    def test_deduplicates_same_date(self, store: SnapshotStore) -> None:
        """Saving the same date twice should keep only the latest.

        Prevents duplicate rows if snapshot is retaken on the same day.
        """
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 25), regime="positive"))
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 25), regime="negative"))
        rows = store.load("SPX", "gex")
        assert len(rows) == 1
        assert rows[0]["regime"] == "negative"

    def test_load_empty_returns_empty(self, store: SnapshotStore) -> None:
        """Loading from a non-existent file should return empty list, not error.

        History tools must gracefully handle no-data scenarios.
        """
        rows = store.load("SPX", "gex")
        assert rows == []

    def test_load_with_days_filter(self, store: SnapshotStore) -> None:
        """Loading with days filter should return only recent rows.

        History tools default to 30 days — must not return all time.
        """
        for i in range(10):
            store.save("SPX", "gex", _gex_row(d=date(2026, 3, 16 + i)))
        rows = store.load("SPX", "gex", days=5)
        assert len(rows) == 5
        # Should be the last 5 dates
        dates = [r["date"] for r in rows]
        assert dates[0] == date(2026, 3, 21)
        assert dates[-1] == date(2026, 3, 25)

    def test_separate_symbols(self, store: SnapshotStore) -> None:
        """Different symbols should have independent storage.

        SPX snapshots must not appear in QQQ history.
        """
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 25), zero_gamma=5200.0))
        store.save("QQQ", "gex", _gex_row(d=date(2026, 3, 25), zero_gamma=440.0))
        spx = store.load("SPX", "gex")
        qqq = store.load("QQQ", "gex")
        assert len(spx) == 1
        assert len(qqq) == 1
        assert spx[0]["zero_gamma"] == 5200.0
        assert qqq[0]["zero_gamma"] == 440.0


class TestHasSnapshotToday:
    """Test checking if today's snapshot exists."""

    def test_no_snapshot_returns_false(self, store: SnapshotStore) -> None:
        """No file means no snapshot today."""
        assert store.has_snapshot_today("SPX", "gex") is False

    def test_old_snapshot_returns_false(self, store: SnapshotStore) -> None:
        """A snapshot from yesterday is not today's snapshot."""
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 24)))
        assert store.has_snapshot_today("SPX", "gex", today=date(2026, 3, 25)) is False

    def test_today_snapshot_returns_true(self, store: SnapshotStore) -> None:
        """A snapshot from today should return True."""
        store.save("SPX", "gex", _gex_row(d=date(2026, 3, 25)))
        assert store.has_snapshot_today("SPX", "gex", today=date(2026, 3, 25)) is True


class TestNullableFields:
    """Test that nullable fields (Phase 3A stubs) round-trip through Parquet."""

    def test_iv_nulls_round_trip(self, store: SnapshotStore) -> None:
        """IV percentile/rank/rv/premium are None in Phase 3A — must survive Parquet.

        If Parquet drops nulls or converts them, history queries would break.
        """
        store.save("SPX", "iv", _iv_row())
        rows = store.load("SPX", "iv")
        assert rows[0]["iv_percentile"] is None
        assert rows[0]["iv_rank"] is None
        assert rows[0]["realized_vol_20d"] is None
        assert rows[0]["iv_rv_premium"] is None

    def test_vix_percentile_null_round_trip(self, store: SnapshotStore) -> None:
        """VIX percentile is None in Phase 3A — must survive Parquet."""
        store.save("SPX", "vix", _vix_row())
        rows = store.load("SPX", "vix")
        assert rows[0]["vix_percentile"] is None

    def test_expected_move_actual_null_round_trip(self, store: SnapshotStore) -> None:
        """actual_move is None until backfilled — must survive Parquet."""
        store.save("SPX", "expected_move", _em_row())
        rows = store.load("SPX", "expected_move")
        assert rows[0]["actual_move"] is None


# ── Pre-aggregated computation functions ──────────────────────────


class TestComputeRegimeStreak:
    """Test regime streak calculation."""

    def test_all_same_regime(self) -> None:
        """All positive days → streak = total days.

        Verifies basic streak counting works.
        """
        rows = [_gex_row(d=date(2026, 3, i + 20), regime="positive") for i in range(5)]
        result = compute_regime_streak(rows)
        assert result == {"type": "positive", "days": 5}

    def test_regime_change(self) -> None:
        """Streak resets on regime change — only count from latest.

        If regime flipped 2 days ago, streak should be 2, not 5.
        """
        rows = [
            _gex_row(d=date(2026, 3, 20), regime="positive"),
            _gex_row(d=date(2026, 3, 21), regime="positive"),
            _gex_row(d=date(2026, 3, 22), regime="positive"),
            _gex_row(d=date(2026, 3, 23), regime="negative"),
            _gex_row(d=date(2026, 3, 24), regime="negative"),
        ]
        result = compute_regime_streak(rows)
        assert result == {"type": "negative", "days": 2}

    def test_empty_rows(self) -> None:
        """No data → streak of 0."""
        result = compute_regime_streak([])
        assert result == {"type": "unknown", "days": 0}

    def test_single_day(self) -> None:
        """Single day → streak of 1."""
        result = compute_regime_streak([_gex_row(regime="negative")])
        assert result == {"type": "negative", "days": 1}


class TestComputeZeroGammaTrend:
    """Test zero gamma trend calculation."""

    def test_rising_trend(self) -> None:
        """Zero gamma increasing over 5 days → 'rising'.

        Helps Claude identify upward drift in the gamma flip level.
        """
        rows = [_gex_row(d=date(2026, 3, i + 20), zero_gamma=5200.0 + i * 10) for i in range(6)]
        result = compute_zero_gamma_trend(rows)
        assert result["direction"] == "rising"
        assert result["change_5d"] == pytest.approx(50.0)

    def test_falling_trend(self) -> None:
        """Zero gamma decreasing → 'falling'."""
        rows = [_gex_row(d=date(2026, 3, i + 20), zero_gamma=5200.0 - i * 10) for i in range(6)]
        result = compute_zero_gamma_trend(rows)
        assert result["direction"] == "falling"
        assert result["change_5d"] == pytest.approx(-50.0)

    def test_flat_trend(self) -> None:
        """Zero gamma unchanged → 'flat'."""
        rows = [_gex_row(d=date(2026, 3, i + 20), zero_gamma=5200.0) for i in range(6)]
        result = compute_zero_gamma_trend(rows)
        assert result["direction"] == "flat"

    def test_min_max_30d(self) -> None:
        """Min/max should span all rows provided."""
        rows = [_gex_row(d=date(2026, 3, i + 1), zero_gamma=5100.0 + i * 20) for i in range(10)]
        result = compute_zero_gamma_trend(rows)
        assert result["min_30d"] == 5100.0
        assert result["max_30d"] == 5100.0 + 9 * 20

    def test_empty_rows(self) -> None:
        """No data → all None."""
        result = compute_zero_gamma_trend([])
        assert result["direction"] == "flat"
        assert result["change_5d"] is None

    def test_fewer_than_5_days(self) -> None:
        """With fewer than 5 days, change_5d uses available data."""
        rows = [_gex_row(d=date(2026, 3, i + 20), zero_gamma=5200.0 + i * 10) for i in range(3)]
        result = compute_zero_gamma_trend(rows)
        assert result["change_5d"] == pytest.approx(20.0)


class TestComputeWallMovement:
    """Test call/put wall movement calculation."""

    def test_wall_shift(self) -> None:
        """Walls moving up over 5 days.

        Important for Claude to see directional wall drift.
        """
        rows = [
            _gex_row(d=date(2026, 3, i + 20), call_wall=5300.0 + i * 5, put_wall=5100.0 + i * 3)
            for i in range(6)
        ]
        result = compute_wall_movement(rows)
        assert result["call_wall_5d_change"] == pytest.approx(25.0)
        assert result["put_wall_5d_change"] == pytest.approx(15.0)

    def test_empty_rows(self) -> None:
        """No data → None."""
        result = compute_wall_movement([])
        assert result["call_wall_5d_change"] is None
        assert result["put_wall_5d_change"] is None


class TestComputeIvTrend:
    """Test IV trend calculation."""

    def test_rising_iv(self) -> None:
        """ATM IV increasing → 'rising'."""
        rows = [_iv_row(d=date(2026, 3, i + 20), atm_iv=14.0 + i * 0.5) for i in range(6)]
        result = compute_iv_trend(rows)
        assert result["direction"] == "rising"
        assert result["change_5d"] == pytest.approx(2.5)

    def test_falling_iv(self) -> None:
        """ATM IV decreasing → 'falling'."""
        rows = [_iv_row(d=date(2026, 3, i + 20), atm_iv=20.0 - i * 0.5) for i in range(6)]
        result = compute_iv_trend(rows)
        assert result["direction"] == "falling"

    def test_min_max(self) -> None:
        """Min/max should span all rows."""
        rows = [_iv_row(d=date(2026, 3, i + 1), atm_iv=12.0 + i) for i in range(10)]
        result = compute_iv_trend(rows)
        assert result["min_30d"] == 12.0
        assert result["max_30d"] == 21.0

    def test_empty(self) -> None:
        """No data → flat, all None."""
        result = compute_iv_trend([])
        assert result["direction"] == "flat"
        assert result["change_5d"] is None


class TestComputeCurrentVsHistory:
    """Test current-vs-history IV comparison."""

    def test_counts(self) -> None:
        """Count days above and below current IV.

        Claude uses this to contextualize current IV relative to recent history.
        """
        rows = [_iv_row(d=date(2026, 3, i + 1), atm_iv=10.0 + i) for i in range(10)]
        # current = 15.0 → values 10,11,12,13,14 below; 15,16,17,18,19 at-or-above
        result = compute_current_vs_history(rows, current_iv=15.0)
        assert result["days_below_current"] == 5
        assert result["days_above_current"] == 4  # strictly above: 16,17,18,19

    def test_empty(self) -> None:
        """No data → zeros."""
        result = compute_current_vs_history([], current_iv=15.0)
        assert result["days_below_current"] == 0
        assert result["days_above_current"] == 0


class TestComputeVixRegimeHistory:
    """Test VIX regime day counting."""

    def test_regime_counts(self) -> None:
        """Count days in each VIX regime.

        Gives Claude a quick read on how much time was spent in each regime.
        """
        rows = [
            _vix_row(d=date(2026, 3, 1), vix_regime="low"),
            _vix_row(d=date(2026, 3, 2), vix_regime="low"),
            _vix_row(d=date(2026, 3, 3), vix_regime="normal"),
            _vix_row(d=date(2026, 3, 4), vix_regime="elevated"),
            _vix_row(d=date(2026, 3, 5), vix_regime="high"),
        ]
        result = compute_vix_regime_history(rows)
        assert result == {"days_low": 2, "days_normal": 1, "days_elevated": 1, "days_high": 1}

    def test_empty(self) -> None:
        """No data → all zeros."""
        result = compute_vix_regime_history([])
        assert result == {"days_low": 0, "days_normal": 0, "days_elevated": 0, "days_high": 0}


class TestComputeBackwardationEvents:
    """Test backwardation event detection."""

    def test_detects_backwardation(self) -> None:
        """Identifies periods when VIX/VIX3M ratio > 1.05.

        Backwardation signals fear — Claude needs to see these events.
        """
        rows = [
            _vix_row(d=date(2026, 3, 1), vix_vix3m_ratio=0.95, term_structure="contango"),
            _vix_row(d=date(2026, 3, 2), vix_vix3m_ratio=1.08, term_structure="backwardation"),
            _vix_row(d=date(2026, 3, 3), vix_vix3m_ratio=1.10, term_structure="backwardation"),
            _vix_row(d=date(2026, 3, 4), vix_vix3m_ratio=0.98, term_structure="flat"),
        ]
        events = compute_backwardation_events(rows)
        assert len(events) == 1
        assert events[0]["date"] == date(2026, 3, 2)
        assert events[0]["ratio"] == pytest.approx(1.08)
        assert events[0]["duration_days"] == 2

    def test_no_backwardation(self) -> None:
        """All contango → no events."""
        rows = [_vix_row(d=date(2026, 3, i + 1), term_structure="contango") for i in range(5)]
        events = compute_backwardation_events(rows)
        assert events == []

    def test_multiple_events(self) -> None:
        """Two separate backwardation periods detected independently."""
        rows = [
            _vix_row(d=date(2026, 3, 1), term_structure="backwardation", vix_vix3m_ratio=1.06),
            _vix_row(d=date(2026, 3, 2), term_structure="contango", vix_vix3m_ratio=0.95),
            _vix_row(d=date(2026, 3, 3), term_structure="backwardation", vix_vix3m_ratio=1.12),
            _vix_row(d=date(2026, 3, 4), term_structure="backwardation", vix_vix3m_ratio=1.09),
        ]
        events = compute_backwardation_events(rows)
        assert len(events) == 2


class TestComputeExpectedMoveAccuracy:
    """Test expected move accuracy statistics."""

    def test_accuracy_stats(self) -> None:
        """Calculate accuracy from snapshots with actual moves filled in.

        This is the core value prop of Phase 3B — did the expected move hold?
        """
        rows = [
            _em_row(d=date(2026, 3, 1), expected_move_straddle=50.0, actual_move=40.0),  # within
            _em_row(d=date(2026, 3, 2), expected_move_straddle=50.0, actual_move=60.0),  # exceeded
            _em_row(d=date(2026, 3, 3), expected_move_straddle=50.0, actual_move=50.0),  # within
            _em_row(d=date(2026, 3, 4), expected_move_straddle=50.0, actual_move=90.0),  # exceeded
        ]
        result = compute_expected_move_accuracy(rows)
        assert result["times_exceeded"] == 2
        assert result["times_within"] == 2
        assert result["exceed_rate"] == pytest.approx(0.5)
        assert result["avg_ratio"] == pytest.approx((0.8 + 1.2 + 1.0 + 1.8) / 4)
        assert result["max_ratio"] == pytest.approx(1.8)

    def test_no_actual_moves(self) -> None:
        """Rows without actual_move should be excluded from accuracy.

        Recent snapshots won't have actuals yet — must not crash.
        """
        rows = [_em_row(d=date(2026, 3, 1), actual_move=None)]
        result = compute_expected_move_accuracy(rows)
        assert result["times_exceeded"] == 0
        assert result["times_within"] == 0
        assert result["avg_ratio"] is None

    def test_empty(self) -> None:
        """No data → zeros."""
        result = compute_expected_move_accuracy([])
        assert result["times_exceeded"] == 0
        assert result["exceed_rate"] == 0.0
