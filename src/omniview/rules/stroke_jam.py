"""
Stroke Jam / Idle Rule
======================

Deterministic jam and idle detector for machine stroke / proximity sensors.
Consumes ``stroke`` family readings.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

STROKE_JAM_SUSTAINED_S: float = 30.0
STROKE_IDLE_SUSTAINED_S: float = 120.0
STROKE_STALE_TIMEOUT_S: float = 300.0

@dataclass(frozen=True)
class StrokeAnomalyEvent:
    """Immutable Layer 3 event emitted when stroke anomalies are met."""
    
    device_id: str
    timestamp: datetime
    event_type: str = "stroke_anomaly"
    severity: str = "WARNING"
    strokes_in_interval: int = 0
    last_cycle_time_seconds: float = 0.0
    signal_quality: int = 255
    device_status_code: int = 0
    condition_duration_s: float = 0.0
    tier: str = ""
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe plain dict."""
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

class StrokeJamDetector:
    """Stateful per-device stroke anomaly detector."""

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}

    def evaluate(self, sample: dict[str, Any]) -> StrokeAnomalyEvent | None:
        """Evaluate a single stroke reading."""
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        now_epoch = ts.timestamp()
        data = sample.get("data", sample)

        strokes = int(data.get("strokes_in_interval", 0))
        cycle_time = float(data.get("last_cycle_time_seconds", 0.0))
        sig_q = int(data.get("signal_quality", 255))
        status_code = int(data.get("device_status_code", 0))

        # Initialise or refresh device state
        state = self._state.get(device_id)
        if state is None:
            state = {"condition_since": None, "last_seen": now_epoch, "last_tier": ""}
            self._state[device_id] = state

        # Stale-stream reset
        if (now_epoch - state["last_seen"]) > STROKE_STALE_TIMEOUT_S:
            self.reset(device_id)
            state = self._state[device_id]

        state["last_seen"] = now_epoch

        tier, severity = self._classify(strokes, cycle_time, sig_q)

        if tier is None:
            # Condition cleared — reset sustained timer
            state["condition_since"] = None
            state["last_tier"] = ""
            return None

        # New condition or tier changed — start timer
        if state["condition_since"] is None or state["last_tier"] != tier:
            state["condition_since"] = now_epoch
            state["last_tier"] = tier
            return None
            
        condition_duration = now_epoch - state["condition_since"]
        
        # Sustained duration gate
        if tier == "FAULT":
            req_duration = 0.0
        elif tier == "CRITICAL_JAM":
            req_duration = STROKE_JAM_SUSTAINED_S
        else: # WARNING_IDLE
            req_duration = STROKE_IDLE_SUSTAINED_S

        if condition_duration < req_duration:
            return None

        state["last_tier"] = tier

        event = StrokeAnomalyEvent(
            device_id=device_id,
            timestamp=ts,
            severity=severity,
            strokes_in_interval=strokes,
            last_cycle_time_seconds=cycle_time,
            signal_quality=sig_q,
            device_status_code=status_code,
            condition_duration_s=condition_duration,
            tier=tier,
            synthetic=bool(sample.get("synthetic", data.get("synthetic", True))),
        )
        
        logger.info(
            "stroke_anomaly %s on %s — %s (strokes: %d, sig_q: %d, cycle: %.1fs, sustained %.0fs)",
            severity, device_id, tier, strokes, sig_q, cycle_time, condition_duration
        )
        
        return event

    def reset(self, device_id: str) -> None:
        """Reset tracked state for a device (e.g. stream went stale)."""
        self._state[device_id] = {
            "condition_since": None,
            "last_seen": 0.0,
            "last_tier": "",
        }

    @staticmethod
    def _classify(strokes: int, cycle_time: float, sig_q: int) -> tuple[str | None, str]:
        if cycle_time >= 900.0:
            return "FAULT", "ERROR"
        if strokes == 0:
            if sig_q <= 180:
                return "CRITICAL_JAM", "CRITICAL"
            else:
                return "WARNING_IDLE", "WARNING"
        return None, ""

    @staticmethod
    def _parse_timestamp(sample: dict[str, Any]) -> datetime:
        raw = sample.get("timestamp")
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw
        if isinstance(raw, str):
            cleaned = raw.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                pass
        return datetime.now(timezone.utc)
