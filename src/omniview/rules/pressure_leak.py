"""
F05 — Compressor Pressure-Leak Proxy Detector (``pressure_leak``)
==================================================================

Linear slope detector on loaded-only pressure windows.  Computes
``decay_rate = (bar_last − bar_first) / Δt_min`` and alerts when the
rate exceeds the configured threshold.

Algorithm::

    1. Keep only loaded==1 samples in a rolling buffer
    2. Require ≥ PRESSURE_MIN_LOADED_SAMPLES
    3. Linear slope: decay_rate = (last - first) / Δt_min
    4. Alert when decay_rate ≤ −THRESHOLD (negative = losing pressure)
    5. Reset buffer on unload transition or stale gap

Design rationale:
    Decay-while-loaded is a slope test — no ML needed for the Layer 3
    alert.  The support logistic (pressure_models.py) is promotion-gated
    and does NOT reach Layer 3.

Reference: Feature Spec F05, System Workflow §4.3, PRD FR6.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.config import (
    PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN,
    PRESSURE_MIN_LOADED_SAMPLES,
    PRESSURE_SLOPE_WINDOW_S,
)

logger = logging.getLogger(__name__)


# ── Event dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PressureLeakEvent:
    """Layer 3 event emitted when abnormal pressure decay is detected."""

    device_id: str
    timestamp: datetime
    event_type: str = "pressure_leak"
    severity: str = "alert"
    pressure_bar: float = 0.0
    decay_rate_bar_per_min: float = 0.0
    loaded: bool = True
    window_samples: int = 0
    window_duration_s: float = 0.0
    synthetic: bool = True
    threshold_refs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        d["event_id"] = str(uuid.uuid4())
        d["source_unit"] = "pressure_leak"
        return d


# ── Detector ─────────────────────────────────────────────────────────────


class PressureLeakDetector:
    """Stateful per-device pressure decay detector.

    Maintains a rolling buffer of loaded-only pressure readings and
    computes the linear slope.  Alerts on abnormal decay.

    Parameters
    ----------
    decay_threshold : float
        Threshold in bar/min (positive number; alert fires when
        actual decay_rate ≤ −threshold).
    slope_window_s : int
        Maximum age of samples in the rolling buffer (seconds).
    min_samples : int
        Minimum loaded samples required before computing slope.
    """

    def __init__(
        self,
        decay_threshold: float = PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN,
        slope_window_s: int = PRESSURE_SLOPE_WINDOW_S,
        min_samples: int = PRESSURE_MIN_LOADED_SAMPLES,
    ) -> None:
        self._threshold = decay_threshold
        self._window_s = slope_window_s
        self._min_samples = min_samples

        # device_id → deque of (epoch, bar)
        self._buffers: dict[str, deque] = {}
        self._last_loaded: dict[str, bool] = {}
        self._alerted: dict[str, bool] = {}

    def evaluate(self, sample: dict[str, Any]) -> PressureLeakEvent | None:
        """Evaluate a single pressure reading.

        Parameters
        ----------
        sample : dict
            Must contain ``device_id``, ``timestamp``, and data fields
            for pressure (``pressure_bar``) and loaded state
            (``compressor_state`` or ``loaded``).

        Returns
        -------
        PressureLeakEvent | None
        """
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        now_epoch = ts.timestamp()
        data = sample.get("data", sample)

        # Extract fields
        pressure = self._get_float(data, "pressure_bar")
        loaded = self._resolve_loaded(data)

        if pressure is None:
            return None

        # Ensure buffer exists
        if device_id not in self._buffers:
            self._buffers[device_id] = deque()
            self._last_loaded[device_id] = loaded
            self._alerted[device_id] = False

        buf = self._buffers[device_id]

        # Reset on load transition (loaded → unloaded or vice versa)
        if loaded != self._last_loaded.get(device_id):
            buf.clear()
            self._alerted[device_id] = False
        self._last_loaded[device_id] = loaded

        # Only track loaded samples
        if not loaded:
            return None

        # Add to buffer
        buf.append((now_epoch, pressure))

        # Trim old samples outside the window
        cutoff = now_epoch - self._window_s
        while buf and buf[0][0] < cutoff:
            buf.popleft()

        # Need enough samples
        if len(buf) < self._min_samples:
            return None

        # Compute linear slope
        first_epoch, first_bar = buf[0]
        last_epoch, last_bar = buf[-1]
        dt_min = (last_epoch - first_epoch) / 60.0

        if dt_min <= 0:
            return None

        decay_rate = (last_bar - first_bar) / dt_min  # negative = losing pressure

        # Alert condition: decay_rate is negative and magnitude exceeds threshold
        if decay_rate <= -self._threshold and not self._alerted.get(device_id, False):
            self._alerted[device_id] = True

            return PressureLeakEvent(
                device_id=device_id,
                timestamp=ts,
                pressure_bar=round(pressure, 2),
                decay_rate_bar_per_min=round(decay_rate, 4),
                loaded=True,
                window_samples=len(buf),
                window_duration_s=round(last_epoch - first_epoch, 1),
                synthetic=sample.get("synthetic", True),
                threshold_refs={
                    "decay_threshold_bar_per_min": self._threshold,
                    "slope_window_s": self._window_s,
                    "min_loaded_samples": self._min_samples,
                    "note": "PLACEHOLDER — pending OI-43 site WIKA calibration",
                },
            )

        return None

    def reset(self, device_id: str | None = None) -> None:
        """Reset state for one device, or all."""
        if device_id:
            self._buffers.pop(device_id, None)
            self._last_loaded.pop(device_id, None)
            self._alerted.pop(device_id, None)
        else:
            self._buffers.clear()
            self._last_loaded.clear()
            self._alerted.clear()

    @staticmethod
    def _resolve_loaded(data: dict[str, Any]) -> bool:
        """Determine loaded state from available fields."""
        if "loaded" in data:
            return bool(data["loaded"])
        cs = data.get("compressor_state", "")
        if isinstance(cs, str):
            return cs.lower() in ("loaded", "running", "on")
        return True  # default assume loaded

    @staticmethod
    def _get_float(data: dict, *keys: str) -> float | None:
        for key in keys:
            val = data.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _parse_timestamp(sample: dict[str, Any]) -> datetime:
        ts_raw = sample.get("timestamp")
        if isinstance(ts_raw, datetime):
            return ts_raw
        if isinstance(ts_raw, str):
            dt = datetime.fromisoformat(ts_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        if isinstance(ts_raw, (int, float)):
            return datetime.fromtimestamp(ts_raw, tz=timezone.utc)
        return datetime.now(timezone.utc)
