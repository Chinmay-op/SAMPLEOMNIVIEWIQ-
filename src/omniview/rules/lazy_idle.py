"""
F04 — Lazy-Idle / Heater-While-Idle Waste Detector (``lazy_idle``)
===================================================================

Deterministic threshold rule: detects when a zone/barrel temperature
remains elevated while electrical current indicates the machine is
idle — sustained for a configurable duration (default 15 min).

Algorithm (no ML)::

    condition = zone_temp_c > THRESHOLD_C  AND  current_a < THRESHOLD_A
    If condition sustained ≥ DURATION_MIN → emit lazy_idle event

Design rationale:
    The physics is unambiguous: heat + no current = waste.  A model
    would only add opacity.  The lab logistic (idle_models.py) stays
    promotion-gated and is NOT Layer 3.

Reference: Feature Spec F04, System Workflow §4.3, PRD FR5.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.config import (
    LAZY_IDLE_DURATION_MIN,
    LAZY_IDLE_RULE_CURRENT_A,
    LAZY_IDLE_RULE_TEMP_C,
)

logger = logging.getLogger(__name__)


# ── Event dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class LazyIdleEvent:
    """Layer 3 event emitted when lazy-idle condition is sustained."""

    device_id: str
    timestamp: datetime
    event_type: str = "lazy_idle"
    severity: str = "alert"
    zone_temp_c: float = 0.0
    current_a: float = 0.0
    duration_min: float = 0.0
    synthetic: bool = True
    threshold_refs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        d["event_id"] = str(uuid.uuid4())
        d["source_unit"] = "lazy_idle"
        return d


# ── Detector ─────────────────────────────────────────────────────────────


class LazyIdleDetector:
    """Stateful per-device lazy-idle detector.

    Tracks ``condition_since`` per device to implement the sustained-
    duration gate.

    Parameters
    ----------
    temp_threshold_c : float
        Zone temperature above which the machine is considered "hot".
    current_threshold_a : float
        Current below which the machine is considered "idle".
    duration_min : int
        Minimum sustained minutes before an event fires.
    """

    def __init__(
        self,
        temp_threshold_c: float = LAZY_IDLE_RULE_TEMP_C,
        current_threshold_a: float = LAZY_IDLE_RULE_CURRENT_A,
        duration_min: int = LAZY_IDLE_DURATION_MIN,
    ) -> None:
        self._temp_threshold = temp_threshold_c
        self._current_threshold = current_threshold_a
        self._duration_min = duration_min

        # device_id → {condition_since: float|None, last_seen: float, alerted: bool}
        self._state: dict[str, dict[str, Any]] = {}

    def evaluate(self, sample: dict[str, Any]) -> LazyIdleEvent | None:
        """Evaluate a single reading that has both thermal and electrical data.

        Parameters
        ----------
        sample : dict
            Must contain ``device_id``, ``timestamp``, and data fields
            for temperature (``zone_temp_c`` or ``present_value_pv_c``)
            and current (``current_a`` or ``current_a_avg``).

        Returns
        -------
        LazyIdleEvent | None
        """
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        now_epoch = ts.timestamp()
        data = sample.get("data", sample)

        # Extract fields (accept both adapted and raw names)
        temp = self._get_float(data, "zone_temp_c", "present_value_pv_c")
        current = self._get_float(data, "current_a", "current_a_avg")

        if temp is None or current is None:
            return None

        # Initialise device state
        state = self._state.get(device_id)
        if state is None:
            state = {"condition_since": None, "last_seen": now_epoch, "alerted": False}
            self._state[device_id] = state

        # Stale-stream reset (>5 min gap)
        if (now_epoch - state["last_seen"]) > 300:
            self._reset_device(device_id)
            state = self._state[device_id]

        state["last_seen"] = now_epoch

        # Check condition: hot AND idle
        is_hot = temp > self._temp_threshold
        is_idle = current < self._current_threshold
        condition_met = is_hot and is_idle

        if condition_met:
            if state["condition_since"] is None:
                state["condition_since"] = now_epoch
                state["alerted"] = False

            duration_s = now_epoch - state["condition_since"]
            duration_min = duration_s / 60.0

            if duration_min >= self._duration_min and not state["alerted"]:
                state["alerted"] = True
                return LazyIdleEvent(
                    device_id=device_id,
                    timestamp=ts,
                    zone_temp_c=round(temp, 1),
                    current_a=round(current, 3),
                    duration_min=round(duration_min, 1),
                    synthetic=sample.get("synthetic", True),
                    threshold_refs={
                        "temp_threshold_c": self._temp_threshold,
                        "current_threshold_a": self._current_threshold,
                        "duration_min": self._duration_min,
                        "note": "PLACEHOLDER — pending OI-79 site calibration",
                    },
                )
        else:
            # Condition broken — reset timer
            state["condition_since"] = None
            state["alerted"] = False

        return None

    def reset(self, device_id: str | None = None) -> None:
        """Reset state for one device, or all devices."""
        if device_id:
            self._state.pop(device_id, None)
            self._reset_device(device_id)
        else:
            self._state.clear()

    def _reset_device(self, device_id: str) -> None:
        self._state[device_id] = {
            "condition_since": None,
            "last_seen": 0.0,
            "alerted": False,
        }

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
