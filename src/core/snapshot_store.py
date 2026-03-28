"""Parquet-based daily snapshot storage for GEX, IV, VIX, and expected move history.

Stores one row per day per symbol in append-only Parquet files.
Deduplicates by date on save (latest wins).
"""

from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.shared.logging import get_logger

logger = get_logger(__name__)

# ── Parquet schemas ────────────────────────────────────────────────

GEX_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("regime", pa.string()),
    ("zero_gamma", pa.float64()),
    ("call_wall", pa.float64()),
    ("put_wall", pa.float64()),
    ("max_gamma", pa.float64()),
    ("hvl", pa.float64()),
    ("total_gex", pa.float64()),
    ("gross_gex", pa.float64()),
])

IV_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("atm_iv", pa.float64()),
    ("iv_percentile", pa.float64()),  # nullable
    ("iv_rank", pa.float64()),  # nullable
    ("realized_vol_20d", pa.float64()),  # nullable
    ("iv_rv_premium", pa.float64()),  # nullable
    ("skew_25d", pa.float64()),
    ("skew_regime", pa.string()),
    ("term_structure_shape", pa.string()),
])

VIX_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("vix_level", pa.float64()),
    ("vix_percentile", pa.float64()),  # nullable
    ("vix_regime", pa.string()),
    ("vix3m", pa.float64()),
    ("vix_vix3m_ratio", pa.float64()),
    ("term_structure", pa.string()),
])

EXPECTED_MOVE_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("expiration", pa.date32()),
    ("expected_move_straddle", pa.float64()),
    ("expected_move_1sd", pa.float64()),
    ("actual_move", pa.float64()),  # nullable
])

SCHEMAS: dict[str, pa.Schema] = {
    "gex": GEX_SCHEMA,
    "iv": IV_SCHEMA,
    "vix": VIX_SCHEMA,
    "expected_move": EXPECTED_MOVE_SCHEMA,
}

FILE_NAMES: dict[str, str] = {
    "gex": "gex_history.parquet",
    "iv": "iv_history.parquet",
    "vix": "vix_history.parquet",
    "expected_move": "expected_move_history.parquet",
}


class SnapshotStore:
    """Parquet-based daily snapshot storage."""

    def __init__(self, base_dir: str = "./data/snapshots") -> None:
        self._base_dir = Path(base_dir)

    def _path(self, symbol: str, snapshot_type: str) -> Path:
        """Get the Parquet file path for a symbol and snapshot type."""
        return self._base_dir / symbol / FILE_NAMES[snapshot_type]

    def save(self, symbol: str, snapshot_type: str, row: dict) -> None:
        """Save a snapshot row, deduplicating by date (latest wins)."""
        path = self._path(symbol, snapshot_type)
        schema = SCHEMAS[snapshot_type]

        # Load existing rows
        existing = self._read_table(path, schema)

        # Deduplicate: remove rows with same date as new row
        new_date = row["date"]
        filtered = [r for r in existing if r["date"] != new_date]
        filtered.append(row)

        # Sort by date
        filtered.sort(key=lambda r: r["date"])

        # Write back
        self._write_table(path, schema, filtered)
        logger.debug("Saved %s snapshot for %s on %s", snapshot_type, symbol, new_date)

    def load(
        self,
        symbol: str,
        snapshot_type: str,
        days: int | None = None,
    ) -> list[dict]:
        """Load snapshot rows, optionally filtered to last N days."""
        path = self._path(symbol, snapshot_type)
        schema = SCHEMAS[snapshot_type]
        rows = self._read_table(path, schema)

        if days is not None and len(rows) > days:
            rows = rows[-days:]

        return rows

    def has_snapshot_today(
        self,
        symbol: str,
        snapshot_type: str,
        today: date | None = None,
    ) -> bool:
        """Check if a snapshot exists for today."""
        today = today or date.today()
        path = self._path(symbol, snapshot_type)
        schema = SCHEMAS[snapshot_type]
        rows = self._read_table(path, schema)
        return any(r["date"] == today for r in rows)

    def _read_table(self, path: Path, schema: pa.Schema) -> list[dict]:
        """Read a Parquet file into a list of dicts."""
        if not path.exists():
            return []
        table = pq.read_table(path, schema=schema)
        return _table_to_dicts(table)

    def _write_table(self, path: Path, schema: pa.Schema, rows: list[dict]) -> None:
        """Write a list of dicts to a Parquet file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        table = _dicts_to_table(rows, schema)
        pq.write_table(table, path)


def _dicts_to_table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    """Convert list of dicts to a PyArrow table with proper schema."""
    if not rows:
        return schema.empty_table()

    columns = {}
    for field in schema:
        values = [row.get(field.name) for row in rows]
        columns[field.name] = pa.array(values, type=field.type)

    return pa.table(columns, schema=schema)


def _table_to_dicts(table: pa.Table) -> list[dict]:
    """Convert a PyArrow table to a list of dicts with Python types."""
    rows = []
    columns = table.column_names
    for i in range(len(table)):
        row = {}
        for col_name in columns:
            val = table.column(col_name)[i].as_py()
            row[col_name] = val
        rows.append(row)
    return rows


# ── Pre-aggregated computation functions ──────────────────────────


def compute_regime_streak(rows: list[dict]) -> dict:
    """Count consecutive days of the same GEX regime from the end."""
    if not rows:
        return {"type": "unknown", "days": 0}

    latest_regime = rows[-1]["regime"]
    streak = 0
    for row in reversed(rows):
        if row["regime"] == latest_regime:
            streak += 1
        else:
            break
    return {"type": latest_regime, "days": streak}


def compute_zero_gamma_trend(rows: list[dict]) -> dict:
    """Compute zero gamma trend: direction, 5d change, min/max."""
    if not rows:
        return {"direction": "flat", "change_5d": None, "min_30d": None, "max_30d": None}

    values = [r["zero_gamma"] for r in rows]
    min_val = min(values)
    max_val = max(values)

    # 5d change: last value minus value 5 rows back (or first available)
    if len(values) >= 2:
        lookback = min(5, len(values) - 1)
        change = values[-1] - values[-1 - lookback]
    else:
        change = 0.0

    if change > 0.01:
        direction = "rising"
    elif change < -0.01:
        direction = "falling"
    else:
        direction = "flat"

    return {
        "direction": direction,
        "change_5d": round(change, 2),
        "min_30d": min_val,
        "max_30d": max_val,
    }


def compute_wall_movement(rows: list[dict]) -> dict:
    """Compute call/put wall movement over 5 days."""
    if not rows:
        return {"call_wall_5d_change": None, "put_wall_5d_change": None}

    if len(rows) >= 2:
        lookback = min(5, len(rows) - 1)
        call_change = rows[-1]["call_wall"] - rows[-1 - lookback]["call_wall"]
        put_change = rows[-1]["put_wall"] - rows[-1 - lookback]["put_wall"]
    else:
        call_change = 0.0
        put_change = 0.0

    return {
        "call_wall_5d_change": round(call_change, 2),
        "put_wall_5d_change": round(put_change, 2),
    }


def compute_iv_trend(rows: list[dict]) -> dict:
    """Compute IV trend: direction, 5d change, min/max."""
    if not rows:
        return {"direction": "flat", "change_5d": None, "min_30d": None, "max_30d": None}

    values = [r["atm_iv"] for r in rows]
    min_val = min(values)
    max_val = max(values)

    if len(values) >= 2:
        lookback = min(5, len(values) - 1)
        change = values[-1] - values[-1 - lookback]
    else:
        change = 0.0

    if change > 0.01:
        direction = "rising"
    elif change < -0.01:
        direction = "falling"
    else:
        direction = "flat"

    return {
        "direction": direction,
        "change_5d": round(change, 2),
        "min_30d": min_val,
        "max_30d": max_val,
    }


def compute_current_vs_history(rows: list[dict], current_iv: float) -> dict:
    """Compare current IV to historical values."""
    if not rows:
        return {"iv_percentile": None, "days_above_current": 0, "days_below_current": 0}

    values = [r["atm_iv"] for r in rows]
    below = sum(1 for v in values if v < current_iv)
    above = sum(1 for v in values if v > current_iv)
    percentile = round(below / len(values) * 100, 2) if values else None

    return {
        "iv_percentile": percentile,
        "days_above_current": above,
        "days_below_current": below,
    }


def compute_vix_regime_history(rows: list[dict]) -> dict:
    """Count days in each VIX regime."""
    counts = {"days_low": 0, "days_normal": 0, "days_elevated": 0, "days_high": 0}
    for row in rows:
        key = f"days_{row['vix_regime']}"
        if key in counts:
            counts[key] += 1
    return counts


def compute_backwardation_events(rows: list[dict]) -> list[dict]:
    """Detect backwardation periods (term_structure == 'backwardation')."""
    events: list[dict] = []
    in_event = False
    event_start: date | None = None
    event_ratio: float = 0.0
    event_days: int = 0

    for row in rows:
        if row["term_structure"] == "backwardation":
            if not in_event:
                in_event = True
                event_start = row["date"]
                event_ratio = row["vix_vix3m_ratio"]
                event_days = 1
            else:
                event_days += 1
        else:
            if in_event:
                events.append({
                    "date": event_start,
                    "ratio": round(event_ratio, 4),
                    "duration_days": event_days,
                })
                in_event = False

    # Close any open event at end
    if in_event:
        events.append({
            "date": event_start,
            "ratio": round(event_ratio, 4),
            "duration_days": event_days,
        })

    return events


def compute_expected_move_accuracy(rows: list[dict]) -> dict:
    """Compute expected move accuracy statistics."""
    filled = [r for r in rows if r.get("actual_move") is not None]

    if not filled:
        return {
            "times_exceeded": 0,
            "times_within": 0,
            "exceed_rate": 0.0,
            "avg_ratio": None,
            "max_ratio": None,
        }

    ratios = []
    exceeded = 0
    within = 0

    for r in filled:
        ratio = abs(r["actual_move"]) / r["expected_move_straddle"]
        ratios.append(ratio)
        if abs(r["actual_move"]) > r["expected_move_straddle"]:
            exceeded += 1
        else:
            within += 1

    total = len(filled)
    return {
        "times_exceeded": exceeded,
        "times_within": within,
        "exceed_rate": round(exceeded / total, 4) if total else 0.0,
        "avg_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
        "max_ratio": round(max(ratios), 4) if ratios else None,
    }
