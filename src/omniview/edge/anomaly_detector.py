"""
omniview.edge.anomaly_detector — Unified Cross-Family Anomaly Detection Engine
================================================================================

A single, self-calibrating anomaly detector that works on ANY numeric
time-series data from ANY sensor family. It uses three statistical methods:

1. Z-Score    — detects spikes and sudden drops
2. Slope      — detects gradual decreases (slow leaks, degrading bearings)
3. CUSUM      — detects slow cumulative drift invisible to Z-score

Usage:
    from omniview.edge.anomaly_detector import AnomalyDetector

    detector = AnomalyDetector()
    alerts = detector.ingest(payload)  # payload is a standard bot dict
    # alerts is a list of alert dicts (empty if everything is normal)

Design Principles:
    - Zero external dependencies (no MQTT, no schemas, no bot imports)
    - Self-calibrating: uses rolling statistics, not hardcoded thresholds
    - Scale-independent: works on 38 bar pressure AND 255°C temperature
    - Stateful: maintains per-metric rolling windows across calls
"""

import math
import datetime
from collections import defaultdict


class MetricWindow:
    """Rolling window of the last N readings for a single metric.

    Each unique (device_id, field_name) pair gets its own MetricWindow.
    The window automatically discards old values when it reaches capacity.

    Parameters
    ----------
    size : int
        Maximum number of readings to retain. Default 30.
    """

    def __init__(self, size: int = 30):
        self.values: list[float] = []
        self.size = size

    def push(self, value: float):
        """Add a new reading to the window."""
        self.values.append(value)
        if len(self.values) > self.size:
            self.values.pop(0)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def is_ready(self) -> bool:
        """Need at least 10 readings before statistics are meaningful."""
        return self.count >= 10

    @property
    def mean(self) -> float:
        if not self.values:
            return 0.0
        return sum(self.values) / len(self.values)

    @property
    def std(self) -> float:
        """Population standard deviation."""
        if len(self.values) < 2:
            return 0.0
        m = self.mean
        variance = sum((x - m) ** 2 for x in self.values) / len(self.values)
        return math.sqrt(variance)

    def z_score(self, value: float) -> float:
        """Calculate Z-score of a value against the current window.

        Returns 0.0 if standard deviation is zero (all identical values).
        """
        s = self.std
        if s == 0.0:
            return 0.0
        return (value - self.mean) / s

    def slope(self) -> float:
        """Calculate the linear regression slope over the window.

        Uses least-squares regression: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
        where x is the index (0, 1, 2, ...) and y is the value.

        A negative slope indicates a gradual decrease.
        Returns 0.0 if insufficient data.
        """
        n = len(self.values)
        if n < 10:
            return 0.0

        x_mean = (n - 1) / 2.0
        y_mean = self.mean

        numerator = 0.0
        denominator = 0.0
        for i, y in enumerate(self.values):
            dx = i - x_mean
            numerator += dx * (y - y_mean)
            denominator += dx * dx

        if denominator == 0.0:
            return 0.0

        return numerator / denominator


class AnomalyDetector:
    """Unified cross-family anomaly detection engine.

    Maintains per-metric rolling windows and applies three statistical
    checks to every incoming reading:

    1. Z-Score check (|z| > z_threshold) → spike or sudden drop
    2. Slope check (slope < -slope_threshold) → gradual decrease
    3. CUSUM check (cumulative sum > cusum_threshold) → slow drift

    Parameters
    ----------
    window_size : int
        Number of recent readings to keep per metric. Default 30.
    z_threshold : float
        Z-score threshold for spike/drop detection. Default 3.0.
    slope_threshold : float
        Absolute slope threshold for gradual decrease. Default 0.05.
        (Slope is normalized by dividing by the mean, making it scale-independent.)
    cusum_threshold : float
        CUSUM accumulator threshold for drift detection. Default 5.0.
    """

    def __init__(
        self,
        window_size: int = 30,
        z_threshold: float = 3.5,
        slope_threshold: float = 0.03,
        cusum_threshold: float = 5.0,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.slope_threshold = slope_threshold
        self.cusum_threshold = cusum_threshold

        # Per-metric state
        self.windows: dict[str, MetricWindow] = {}
        self.cusum_pos: dict[str, float] = defaultdict(float)
        self.cusum_neg: dict[str, float] = defaultdict(float)

    def _get_window(self, key: str) -> MetricWindow:
        """Get or create a MetricWindow for a metric key."""
        if key not in self.windows:
            self.windows[key] = MetricWindow(size=self.window_size)
        return self.windows[key]

    def _check_zscore(self, key: str, value: float, window: MetricWindow) -> dict | None:
        """Check for spike or sudden drop using Z-score."""
        z = window.z_score(value)

        if abs(z) > self.z_threshold:
            if z > 0:
                anomaly_type = "spike"
            else:
                anomaly_type = "sudden_drop"

            return {
                "metric": key,
                "anomaly_type": anomaly_type,
                "severity": "high" if abs(z) > 5.0 else "medium",
                "value": round(value, 4),
                "mean": round(window.mean, 4),
                "std": round(window.std, 4),
                "z_score": round(z, 2),
            }
        return None

    def _check_slope(self, key: str, window: MetricWindow) -> dict | None:
        """Check for gradual decrease using normalized linear regression slope."""
        if not window.is_ready:
            return None

        raw_slope = window.slope()
        mean = window.mean

        # Normalize slope by dividing by mean to make it scale-independent.
        # A slope of -0.5 on a 255°C signal is trivial (0.2%),
        # but a slope of -0.5 on a 3.0 mm/s signal is catastrophic (17%).
        if abs(mean) < 1e-6:
            return None

        normalized_slope = raw_slope / abs(mean)

        if normalized_slope < -self.slope_threshold:
            return {
                "metric": key,
                "anomaly_type": "gradual_decrease",
                "severity": "medium" if normalized_slope > -0.1 else "high",
                "slope": round(raw_slope, 6),
                "normalized_slope": round(normalized_slope, 6),
                "mean": round(mean, 4),
                "window_size": window.count,
            }
        return None

    def _check_cusum(self, key: str, value: float, window: MetricWindow) -> dict | None:
        """Check for slow cumulative drift using CUSUM (Cumulative Sum Control Chart).

        CUSUM detects small, persistent shifts in the mean that Z-score misses
        because each individual reading is only slightly off.
        """
        if not window.is_ready:
            return None

        mean = window.mean
        std = window.std

        if std == 0.0:
            return None

        # Normalized deviation from mean
        deviation = (value - mean) / std

        # CUSUM accumulators (reset to 0 when they go negative/positive respectively)
        # This is the tabular CUSUM method
        slack = 1.0  # Allow one standard deviation of natural drift
        self.cusum_pos[key] = max(0.0, self.cusum_pos[key] + deviation - slack)
        self.cusum_neg[key] = max(0.0, self.cusum_neg[key] - deviation - slack)

        triggered_direction = None
        cusum_value = 0.0

        if self.cusum_pos[key] > self.cusum_threshold:
            triggered_direction = "upward_drift"
            cusum_value = self.cusum_pos[key]
            self.cusum_pos[key] = 0.0  # Reset after alert

        if self.cusum_neg[key] > self.cusum_threshold:
            triggered_direction = "downward_drift"
            cusum_value = self.cusum_neg[key]
            self.cusum_neg[key] = 0.0  # Reset after alert

        if triggered_direction:
            return {
                "metric": key,
                "anomaly_type": triggered_direction,
                "severity": "medium",
                "cusum_value": round(cusum_value, 2),
                "value": round(value, 4),
                "mean": round(mean, 4),
            }
        return None

    def ingest(self, payload: dict) -> list[dict]:
        """Feed a standard bot payload through the detector.

        Extracts all numeric fields from payload["data"], pushes each into
        its per-metric rolling window, and runs all three statistical checks.

        Parameters
        ----------
        payload : dict
            A standard bot payload with keys: device_id, timestamp, sensor_type, data.

        Returns
        -------
        list[dict]
            A list of alert dicts. Empty list if everything is normal.
        """
        alerts = []

        device_id = payload.get("device_id", "unknown")
        timestamp = payload.get("timestamp", "")
        sensor_type = payload.get("sensor_type", "unknown")
        data = payload.get("data", {})

        for field_name, value in data.items():
            # Only process numeric values
            if not isinstance(value, (int, float)):
                continue

            # Build a unique key for this metric
            key = f"{device_id}:{field_name}"

            window = self._get_window(key)

            # ── Smart Filters (skip non-sensor fields) ──────────────────

            # Filter 1: Skip binary/boolean fields (only ever 0 or 1)
            if window.count >= 5:
                unique_vals = set(window.values)
                if unique_vals <= {0, 1, 0.0, 1.0, True, False}:
                    window.push(value)
                    continue

            # Filter 2: Skip monotonically increasing counters
            # (energy accumulators, stroke counters, operating hours)
            if window.count >= 10:
                diffs = [window.values[i+1] - window.values[i] for i in range(len(window.values)-1)]
                if all(d >= 0 for d in diffs) and any(d > 0 for d in diffs):
                    # Every step is non-negative and at least one is positive → counter
                    window.push(value)
                    continue

            # Run checks BEFORE pushing (so the new value is compared against history)
            if window.is_ready:
                # 1. Z-Score check (spikes and sudden drops)
                z_alert = self._check_zscore(key, value, window)
                if z_alert:
                    z_alert["device_id"] = device_id
                    z_alert["sensor_type"] = sensor_type
                    z_alert["timestamp"] = timestamp
                    alerts.append(z_alert)

                # 2. CUSUM check (slow cumulative drift)
                cusum_alert = self._check_cusum(key, value, window)
                if cusum_alert:
                    cusum_alert["device_id"] = device_id
                    cusum_alert["sensor_type"] = sensor_type
                    cusum_alert["timestamp"] = timestamp
                    alerts.append(cusum_alert)

            # Push AFTER checking (so current value doesn't pollute its own baseline)
            window.push(value)

            # 3. Slope check (gradual decrease — needs the new value in the window)
            if window.is_ready:
                slope_alert = self._check_slope(key, window)
                if slope_alert:
                    slope_alert["device_id"] = device_id
                    slope_alert["sensor_type"] = sensor_type
                    slope_alert["timestamp"] = timestamp
                    alerts.append(slope_alert)

        return alerts
