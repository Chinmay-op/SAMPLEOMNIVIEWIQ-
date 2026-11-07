"""
F07 — Cooling Malfunction Detector (``cooling_malfunction``)
============================================================

Detects when electrical energy / active power is high while cooling or barrel
temperature is anomalously low.

Sprint 5 / OI-135 / OI-145:
- Emits ``cooling_malfunction`` event when electrical energy is high and
  cooling/barrel temperature is low.
- Suggestion only: action card says service or inspect.
- Does NOT stop the machine (``stop_machine = False``).
- Does NOT add a second health index; Stage A stays ``predict_maintenance_risk``.
- Inputs: electrical power and cooling temperature — comparison only.

Physical Rationale:
-------------------
The ISBM machine's barrel is heated (PID controlled to ~255 °C) while drawing
heavy electrical current. When electrical power draw is high (>50 kW) but the
barrel/cooling temperature remains cold (<100 °C), it signals one of:
1. The cooling circuit / chiller solenoid is stuck ON, actively fighting
   heaters and wasting energy.
2. A heater element has burned out, drawing abnormal current while failing
   to heat the barrel.
3. The RTD / PT100 temperature sensor has failed or become disconnected.

Reference:
----------
- Docs/DS/LLD_Four_Core_Features.md §3 (line 57, 63–65)
- Jira Epic OI-135 / Task OI-145
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.config import (
    COOLING_POWER_THRESHOLD_KW,
    COOLING_TEMP_LOW_C,
)

logger = logging.getLogger(__name__)

# Spec constraint: labeled as PLACEHOLDER until site calibration
COOLING_IS_PLACEHOLDER: bool = True

import json
from pathlib import Path

_CALIBRATION_FILE = Path(__file__).resolve().parents[3] / "config" / "cooling_calibration.json"


def load_cooling_calibration() -> dict[str, Any] | None:
    """Load the empirical 30-day statistical calibration manifest if present."""
    if _CALIBRATION_FILE.exists():
        try:
            with open(_CALIBRATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read cooling calibration file: %s", e)
    return None


def get_cooling_thresholds() -> tuple[float, float, bool]:
    """Return (power_threshold_kw, temp_threshold_c, is_placeholder).

    If 30-day empirical calibration exists, returns data-driven equivalents.
    Otherwise falls back to config constants.
    """
    cal = load_cooling_calibration()
    if cal and isinstance(cal, dict):
        p_val = float(cal.get("power_threshold", {}).get("calibrated_production_gate_kw", COOLING_POWER_THRESHOLD_KW))
        t_val = float(cal.get("temperature_threshold", {}).get("calibrated_malfunction_threshold_c", COOLING_TEMP_LOW_C))
        return p_val, t_val, False
    return COOLING_POWER_THRESHOLD_KW, COOLING_TEMP_LOW_C, True



# ── Field Extractors ────────────────────────────────────────────────────────


def _extract_power(sample: dict[str, Any] | None) -> float | None:
    """Extract active power / energy in kW or kWh from a reading dict."""
    if not sample or not isinstance(sample, dict):
        return None

    data = sample.get("data", sample)
    if not isinstance(data, dict):
        return None

    # Priority of electrical power/energy field names (raw and wire-adapted)
    candidates = (
        "active_power_kw_total",
        "kw",
        "active_power_kw",
        "power_kw",
        "active_energy_kwh",
        "energy_kwh",
        "apparent_power_kva_total",
        "kva",
    )
    for key in candidates:
        val = data.get(key)
        if val is not None:
            try:
                f_val = float(val)
                if f_val >= 0:
                    return f_val
            except (ValueError, TypeError):
                continue

    # Fallback to current if power not directly reported: 3-phase P ≈ √3 * 415 * I * 0.9 / 1000 ≈ 0.65 * I
    current = data.get("current_a_avg") or data.get("current_a")
    if current is not None:
        try:
            return float(current) * 0.65
        except (ValueError, TypeError):
            pass

    return None


def _extract_temp(sample: dict[str, Any] | None) -> float | None:
    """Extract cooling or barrel temperature in °C from a reading dict."""
    if not sample or not isinstance(sample, dict):
        return None

    data = sample.get("data", sample)
    if not isinstance(data, dict):
        return None

    # Priority of cooling/barrel temperature field names (raw, bot, wire-adapted)
    candidates = (
        "cooling_temp_c",
        "cooling_temperature_c",
        "present_value_pv_c",
        "zone_temp_c",
        "barrel_temp_c",
        "surface_temp_c",
        "temperature_c",
        "temp_c",
    )
    for key in candidates:
        val = data.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue

    return None


def _parse_timestamp(sample: dict[str, Any] | None) -> datetime:
    """Parse or generate an ISO/UTC timestamp from a sample."""
    if sample and isinstance(sample, dict):
        for k in ("timestamp", "time", "date"):
            val = sample.get(k)
            if isinstance(val, datetime):
                return val
            if isinstance(val, str) and val.strip():
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
    return datetime.now(timezone.utc)


# ── Event Dataclass ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoolingMalfunctionEvent:
    """Layer 3 event emitted when electrical energy is high and cooling temp is low."""

    device_id: str
    timestamp: datetime
    event_type: str = "cooling_malfunction"
    severity: str = "warning"
    active_power_kw: float = 0.0
    cooling_temp_c: float = 0.0
    power_threshold_kw: float = COOLING_POWER_THRESHOLD_KW
    temp_threshold_c: float = COOLING_TEMP_LOW_C
    synthetic: bool = True
    action_suggestion: str = "service_or_inspect"
    stop_machine: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a dictionary conforming to Layer 3 event contract."""
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        d["event_id"] = str(uuid.uuid4())
        d["source_unit"] = "cooling_malfunction"
        return d


# ── Pure Evaluator Function ─────────────────────────────────────────────────


def evaluate_cooling_malfunction(
    first: float | dict[str, Any],
    second: float | dict[str, Any] | None = None,
    power_threshold_kw: float | None = None,
    temp_threshold_c: float | None = None,
    device_id: str | None = None,
    timestamp: datetime | None = None,
    synthetic: bool = True,
) -> CoolingMalfunctionEvent | None:
    """Pure comparison evaluator for cooling malfunction.

    Can be invoked in multiple modes:
    1. Direct numeric comparison:
       ``evaluate_cooling_malfunction(power_kw=65.0, temp_c=80.0)``
    2. Synthetic pair of rows (LLD §3 line 65):
       ``evaluate_cooling_malfunction(electrical_row, thermal_cooling_row)``
    3. Single composite row containing both power and temperature:
       ``evaluate_cooling_malfunction(composite_row)``

    Returns
    -------
    CoolingMalfunctionEvent | None
        Event if power > threshold AND temperature < threshold, else None.
    """
    power_val: float | None = None
    temp_val: float | None = None
    dev_id: str = device_id or "unknown-machine"
    ts: datetime = timestamp or datetime.now(timezone.utc)

    # Mode 1: First argument is a number (direct power)
    if isinstance(first, (int, float)):
        power_val = float(first)
        if isinstance(second, (int, float)):
            temp_val = float(second)
        elif isinstance(second, dict):
            temp_val = _extract_temp(second)
            if not device_id:
                dev_id = str(second.get("device_id", dev_id))

    # Mode 2 or 3: First argument is a dict
    elif isinstance(first, dict):
        if not device_id:
            dev_id = str(first.get("device_id", dev_id))
        if timestamp is None:
            ts = _parse_timestamp(first)

        # Try extracting power from first
        power_val = _extract_power(first)
        # Try extracting temp from first in case it's a single joined/composite sample
        temp_val = _extract_temp(first)

        # If a second dict is provided (synthetic pair of rows)
        if isinstance(second, dict):
            if not device_id and "device_id" in second:
                dev_id = str(second["device_id"])
            second_temp = _extract_temp(second)
            if second_temp is not None:
                temp_val = second_temp
            second_power = _extract_power(second)
            if power_val is None and second_power is not None:
                power_val = second_power
        elif isinstance(second, (int, float)):
            temp_val = float(second)

    # Validate that both power and temp are known numbers
    if power_val is None or temp_val is None:
        return None

    cal_p, cal_t, is_ph = get_cooling_thresholds()
    effective_p = power_threshold_kw if power_threshold_kw is not None else cal_p
    effective_t = temp_threshold_c if temp_threshold_c is not None else cal_t

    # Core comparator condition (LLD §3): high electrical energy + low cooling temperature
    if power_val > effective_p and temp_val < effective_t:
        return CoolingMalfunctionEvent(
            device_id=dev_id,
            timestamp=ts,
            event_type="cooling_malfunction",
            severity="warning",
            active_power_kw=round(power_val, 2),
            cooling_temp_c=round(temp_val, 2),
            power_threshold_kw=effective_p,
            temp_threshold_c=effective_t,
            synthetic=synthetic,
            action_suggestion="service_or_inspect",
            stop_machine=False,
            details={
                "power_exceeds_by_kw": round(power_val - effective_p, 2),
                "temp_below_by_c": round(effective_t - temp_val, 2),
                "is_placeholder_threshold": COOLING_IS_PLACEHOLDER,
                "is_calibrated": not is_ph,
                "calibration_source": "30-day physical simulation" if not is_ph else "uncalibrated_placeholder",
            },
        )

    return None


# ── Stateful Detector for Streaming Telemetry ───────────────────────────────


class CoolingMalfunctionDetector:
    """Stateful detector for cooling malfunction over streaming sensor feeds.

    Accepts telemetry from ``electrical``, ``thermal``, or ``cooling`` sensor
    families, tracks the most recent readings per device within a time window,
    and emits a ``CoolingMalfunctionEvent`` when the comparison threshold is breached.

    Adheres to the ``Detector`` protocol (``evaluate(sample) -> Event | None``).
    """

    def __init__(
        self,
        power_threshold_kw: float | None = None,
        temp_threshold_c: float | None = None,
        cache_window_seconds: float = 300.0,
        cooldown_seconds: float = 300.0,
    ) -> None:
        cal_p, cal_t, _ = get_cooling_thresholds()
        self.power_threshold_kw = power_threshold_kw if power_threshold_kw is not None else cal_p
        self.temp_threshold_c = temp_threshold_c if temp_threshold_c is not None else cal_t
        self.cache_window_seconds = cache_window_seconds
        self.cooldown_seconds = cooldown_seconds

        # device_id -> {"power_kw": float, "power_ts": datetime, "temp_c": float, "temp_ts": datetime, "last_alert_ts": datetime}
        self._state: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        """Reset internal caches."""
        self._state.clear()

    def evaluate_pair(
        self,
        electrical_sample: dict[str, Any],
        cooling_sample: dict[str, Any],
    ) -> CoolingMalfunctionEvent | None:
        """Evaluate a synthetic or synchronized pair of rows directly."""
        return evaluate_cooling_malfunction(
            first=electrical_sample,
            second=cooling_sample,
            power_threshold_kw=self.power_threshold_kw,
            temp_threshold_c=self.temp_threshold_c,
        )

    def evaluate(self, sample: dict[str, Any]) -> CoolingMalfunctionEvent | None:
        """Evaluate a single sample from the live sensor stream.

        Parameters
        ----------
        sample : dict
            Reading dict from TSDB or wire adapter. May belong to
            ``electrical``, ``thermal``, or ``cooling`` sensor families.

        Returns
        -------
        CoolingMalfunctionEvent | None
        """
        if not sample or not isinstance(sample, dict):
            return None

        device_id = str(sample.get("device_id", "unknown-machine"))
        ts = _parse_timestamp(sample)

        # Get or init device state
        state = self._state.setdefault(
            device_id,
            {
                "power_kw": None,
                "power_ts": None,
                "temp_c": None,
                "temp_ts": None,
                "last_alert_ts": None,
            },
        )

        # Check for power reading
        power = _extract_power(sample)
        if power is not None:
            state["power_kw"] = power
            state["power_ts"] = ts

        # Check for temperature reading
        temp = _extract_temp(sample)
        if temp is not None:
            state["temp_c"] = temp
            state["temp_ts"] = ts

        # Verify we have both readings
        cur_power = state.get("power_kw")
        cur_temp = state.get("temp_c")
        power_ts = state.get("power_ts")
        temp_ts = state.get("temp_ts")

        if cur_power is None or cur_temp is None or power_ts is None or temp_ts is None:
            return None

        # Check that readings are temporally correlated within cache window
        time_diff = abs((power_ts - temp_ts).total_seconds())
        if time_diff > self.cache_window_seconds:
            return None

        # Check cooldown to prevent alert storms
        last_alert = state.get("last_alert_ts")
        if last_alert is not None:
            elapsed_since_alert = abs((ts - last_alert).total_seconds())
            if elapsed_since_alert < self.cooldown_seconds:
                return None

        # Evaluate comparison
        event = evaluate_cooling_malfunction(
            first=cur_power,
            second=cur_temp,
            power_threshold_kw=self.power_threshold_kw,
            temp_threshold_c=self.temp_threshold_c,
            device_id=device_id,
            timestamp=ts,
            synthetic=bool(sample.get("synthetic", True)),
        )

        if event is not None:
            state["last_alert_ts"] = ts

        return event


__all__ = [
    "COOLING_IS_PLACEHOLDER",
    "CoolingMalfunctionEvent",
    "CoolingMalfunctionDetector",
    "evaluate_cooling_malfunction",
]
