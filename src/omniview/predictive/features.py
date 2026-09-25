"""
omniview.predictive.features — Daily Feature Aggregation & Rolling Slopes
=========================================================================

Preprocessing for the Health Index pipeline:

1. **Resample to daily aggregates** — this is a slow signal; daily is
   enough resolution (Build Spec §4.1).
2. **Handle gaps** — forward-fill short gaps; flag longer ones as reduced
   confidence rather than silently interpolating (Build Spec §4.2).
3. **Derive phase imbalance** — computed from per-phase currents.
4. **Rolling trend features** — fit a line over a trailing 7-day window
   per signal, take the slope. This is the core preprocessing step;
   everything downstream depends on it (Build Spec §4.4).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DailyRow:
    """One day's aggregated feature values for one machine.

    Fields correspond to the tracked signals in ``layer0_priors.yaml``.
    Missing values are represented as ``None`` (not NaN).
    """

    date: date
    machine_id: str
    # Electrical features (daily means)
    current_a_avg: float | None = None
    voltage_thd_percent: float | None = None
    current_thd_percent: float | None = None
    power_factor_avg: float | None = None
    current_a_neutral: float | None = None
    phase_imbalance_percent: float | None = None
    frequency_hz: float | None = None
    # Vibration features
    z_rms_velocity_mm_sec: float | None = None
    # Gas / thermal features (§8 — closes Layer 3 audit Gap 3)
    gas_concentration_ppm: float | None = None
    internal_panel_temp_c: float | None = None
    # Metadata
    reading_count: int = 0
    gap_flagged: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for serialization."""
        return {
            "date": self.date.isoformat(),
            "machine_id": self.machine_id,
            "current_a_avg": self.current_a_avg,
            "voltage_thd_percent": self.voltage_thd_percent,
            "current_thd_percent": self.current_thd_percent,
            "power_factor_avg": self.power_factor_avg,
            "current_a_neutral": self.current_a_neutral,
            "phase_imbalance_percent": self.phase_imbalance_percent,
            "frequency_hz": self.frequency_hz,
            "z_rms_velocity_mm_sec": self.z_rms_velocity_mm_sec,
            "gas_concentration_ppm": self.gas_concentration_ppm,
            "internal_panel_temp_c": self.internal_panel_temp_c,
            "reading_count": self.reading_count,
            "gap_flagged": self.gap_flagged,
        }


# The signals we extract from raw electrical readings
_ELECTRICAL_FIELDS = {
    "current_a_avg",
    "voltage_thd_percent",
    "current_thd_percent",
    "power_factor_avg",
    "current_a_neutral",
    "frequency_hz",
    "current_a_l1",
    "current_a_l2",
    "current_a_l3",
}

_VIBRATION_FIELDS = {
    "z_axis_rms_velocity_mm_sec",
}

_GAS_FIELDS = {
    "gas_concentration_ppm",
    "internal_panel_temp_c",
}


def compute_phase_imbalance(
    i_l1: float, i_l2: float, i_l3: float
) -> float:
    """Compute percentage phase current imbalance.

    Uses the IEEE definition:
    ``imbalance = (max_deviation_from_mean / mean) × 100``

    Parameters
    ----------
    i_l1, i_l2, i_l3 : float
        Per-phase currents in amperes.

    Returns
    -------
    float
        Imbalance percentage. Returns 0.0 if mean is zero.
    """
    mean = (i_l1 + i_l2 + i_l3) / 3.0
    if mean == 0.0:
        return 0.0
    max_dev = max(abs(i_l1 - mean), abs(i_l2 - mean), abs(i_l3 - mean))
    return (max_dev / mean) * 100.0


def aggregate_daily(
    readings: list[dict[str, Any]],
    machine_id: str,
    sensor_type: str = "electrical",
) -> list[DailyRow]:
    """Aggregate raw readings into daily feature rows.

    Groups readings by date, computes daily means for each tracked
    signal, and derives phase imbalance from per-phase currents.

    Parameters
    ----------
    readings : list[dict]
        Raw readings from TSDB. Each must have ``time`` (ISO string or
        datetime) and ``data`` (dict of field values).
    machine_id : str
        The machine these readings belong to.
    sensor_type : str
        ``"electrical"`` or ``"vibration"``.

    Returns
    -------
    list[DailyRow]
        One row per day, sorted chronologically.
    """
    # Group by date
    by_date: dict[date, list[dict]] = {}

    for reading in readings:
        ts = reading.get("time") or reading.get("timestamp", "")
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif isinstance(ts, datetime):
            dt = ts
        else:
            continue

        day = dt.date()
        data = reading.get("data", {})
        if isinstance(data, str):
            import json as _json
            try:
                data = _json.loads(data)
            except (ValueError, TypeError):
                continue

        by_date.setdefault(day, []).append(data)

    # Aggregate each day
    rows: list[DailyRow] = []
    for day in sorted(by_date.keys()):
        day_readings = by_date[day]
        row = DailyRow(date=day, machine_id=machine_id, reading_count=len(day_readings))

        if sensor_type == "electrical":
            row = _aggregate_electrical(row, day_readings)
        elif sensor_type == "vibration":
            row = _aggregate_vibration(row, day_readings)
        elif sensor_type == "gas":
            row = _aggregate_gas(row, day_readings)

        rows.append(row)

    return rows


def _aggregate_electrical(row: DailyRow, readings: list[dict]) -> DailyRow:
    """Compute daily means for electrical signals."""
    accums: dict[str, list[float]] = {f: [] for f in _ELECTRICAL_FIELDS}

    for data in readings:
        for fld in _ELECTRICAL_FIELDS:
            val = data.get(fld)
            if val is not None and isinstance(val, (int, float)):
                accums[fld].append(float(val))

    # Simple means
    if accums["current_a_avg"]:
        row.current_a_avg = _mean(accums["current_a_avg"])
    if accums["voltage_thd_percent"]:
        row.voltage_thd_percent = _mean(accums["voltage_thd_percent"])
    if accums["current_thd_percent"]:
        row.current_thd_percent = _mean(accums["current_thd_percent"])
    if accums["power_factor_avg"]:
        row.power_factor_avg = _mean(accums["power_factor_avg"])
    if accums["current_a_neutral"]:
        row.current_a_neutral = _mean(accums["current_a_neutral"])
    if accums["frequency_hz"]:
        row.frequency_hz = _mean(accums["frequency_hz"])

    # Derive phase imbalance
    if accums["current_a_l1"] and accums["current_a_l2"] and accums["current_a_l3"]:
        row.phase_imbalance_percent = compute_phase_imbalance(
            _mean(accums["current_a_l1"]),
            _mean(accums["current_a_l2"]),
            _mean(accums["current_a_l3"]),
        )

    return row


def _aggregate_vibration(row: DailyRow, readings: list[dict]) -> DailyRow:
    """Compute daily means for vibration signals."""
    z_rms_vals: list[float] = []
    for data in readings:
        val = data.get("z_axis_rms_velocity_mm_sec")
        if val is not None and isinstance(val, (int, float)):
            z_rms_vals.append(float(val))

    if z_rms_vals:
        row.z_rms_velocity_mm_sec = _mean(z_rms_vals)

    return row


def _aggregate_gas(row: DailyRow, readings: list[dict]) -> DailyRow:
    """Compute daily means for gas / thermal panel signals.

    §8 — wires gas into the existing PdM pipeline so the Health Index
    sees gas_concentration_ppm and internal_panel_temp_c trends.
    Same pattern as ``_aggregate_electrical`` / ``_aggregate_vibration``.
    """
    accums: dict[str, list[float]] = {f: [] for f in _GAS_FIELDS}

    for data in readings:
        for fld in _GAS_FIELDS:
            val = data.get(fld)
            if val is not None and isinstance(val, (int, float)):
                accums[fld].append(float(val))

    if accums["gas_concentration_ppm"]:
        row.gas_concentration_ppm = _mean(accums["gas_concentration_ppm"])
    if accums["internal_panel_temp_c"]:
        row.internal_panel_temp_c = _mean(accums["internal_panel_temp_c"])

    return row


def compute_rolling_slopes(
    daily_rows: list[DailyRow],
    window_days: int = 7,
    signals: list[str] | None = None,
) -> list[dict[str, float | None]]:
    """Compute trailing rolling slopes for each tracked signal.

    Uses least-squares linear regression (polyfit degree 1) over the
    trailing ``window_days`` window. Returns NaN until the warmup
    period is met.

    Parameters
    ----------
    daily_rows : list[DailyRow]
        Chronologically sorted daily feature rows.
    window_days : int
        Trailing window size in days. Default 7.
    signals : list[str], optional
        Which signal fields to compute slopes for. Defaults to all
        non-None numeric fields.

    Returns
    -------
    list[dict[str, float | None]]
        One dict per row, keyed by ``"{signal}_slope_7d"``.
        ``None`` if insufficient data in the window.
    """
    if signals is None:
        signals = [
            "current_a_avg",
            "voltage_thd_percent",
            "current_thd_percent",
            "power_factor_avg",
            "current_a_neutral",
            "phase_imbalance_percent",
            "frequency_hz",
            "z_rms_velocity_mm_sec",
            "gas_concentration_ppm",
            "internal_panel_temp_c",
        ]

    results: list[dict[str, float | None]] = []

    for i, row in enumerate(daily_rows):
        slopes: dict[str, float | None] = {}

        # Determine the window: up to window_days rows ending at i
        start = max(0, i - window_days + 1)
        window = daily_rows[start : i + 1]

        for sig in signals:
            slope_key = f"{sig}_slope_{window_days}d"

            # Extract non-None values with their indices
            points: list[tuple[int, float]] = []
            for j, w_row in enumerate(window):
                val = getattr(w_row, sig, None)
                if val is not None:
                    points.append((j, val))

            if len(points) < max(3, window_days // 2):
                # Not enough data points for a meaningful slope
                slopes[slope_key] = None
            else:
                slopes[slope_key] = _polyfit_slope(points)

        results.append(slopes)

    return results


def enrich_daily_features(
    readings: list[dict[str, Any]],
    machine_id: str,
    sensor_type: str = "electrical",
    slope_window: int = 7,
) -> tuple[list[DailyRow], list[dict[str, float | None]]]:
    """Full preprocessing pipeline: aggregate → slopes.

    Convenience function that runs ``aggregate_daily`` then
    ``compute_rolling_slopes`` in one call.

    Returns
    -------
    tuple
        ``(daily_rows, slopes)`` — the daily aggregates and their
        trailing slope features.
    """
    daily_rows = aggregate_daily(readings, machine_id, sensor_type)
    slopes = compute_rolling_slopes(daily_rows, window_days=slope_window)
    return daily_rows, slopes


# ── Internal helpers ─────────────────────────────────────────────────────


def _mean(values: list[float]) -> float:
    """Safe mean that handles empty lists."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _polyfit_slope(points: list[tuple[int, float]]) -> float:
    """Least-squares linear regression slope.

    Uses the direct formula: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
    No numpy dependency.

    Parameters
    ----------
    points : list[tuple[int, float]]
        (x_index, y_value) pairs.

    Returns
    -------
    float
        The slope of the best-fit line.
    """
    n = len(points)
    if n < 2:
        return 0.0

    x_mean = sum(p[0] for p in points) / n
    y_mean = sum(p[1] for p in points) / n

    numerator = 0.0
    denominator = 0.0

    for x, y in points:
        dx = x - x_mean
        numerator += dx * (y - y_mean)
        denominator += dx * dx

    if denominator == 0.0:
        return 0.0

    return numerator / denominator
