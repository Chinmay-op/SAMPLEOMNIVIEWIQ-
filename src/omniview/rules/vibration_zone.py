"""
F06 — ISO 10816-3 Vibration Zone Classifier (``vibration_zone``)
=================================================================

Pure threshold classifier — no ML.  Maps RMS velocity (mm/s) to
ISO 10816-3 vibration zones and emits events on zone transitions
or when the machine enters Zone C/D.

Zone boundaries (Class II, per contract)::

    Zone A:  ≤ VIB_ZONE_B_BOUNDARY   (good)
    Zone B:  ≤ VIB_ZONE_C_BOUNDARY   (acceptable)
    Zone C:  ≤ VIB_ZONE_D_BOUNDARY   (alert)
    Zone D:  >  VIB_ZONE_D_BOUNDARY  (danger — trip)

Design rationale:
    The international standard defines the bands.  You don't learn
    what Zone C is — ISO already told you.

Reference: Feature Spec F06, ISO 10816-3 Table 1, PRD FR6.

.. warning::

    PLACEHOLDER boundaries from the Layer 3 contract (Class II).
    Reconcile against the actual machine's mounting class + power
    rating during Phase 0 site data collection.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.config import (
    VIB_ZONE_B_BOUNDARY,
    VIB_ZONE_C_BOUNDARY,
    VIB_ZONE_D_BOUNDARY,
)

logger = logging.getLogger(__name__)


# ── Zone boundaries ─────────────────────────────────────────────────────

ZONE_TABLE = {
    "A": (0.0, VIB_ZONE_B_BOUNDARY),
    "B": (VIB_ZONE_B_BOUNDARY, VIB_ZONE_C_BOUNDARY),
    "C": (VIB_ZONE_C_BOUNDARY, VIB_ZONE_D_BOUNDARY),
    "D": (VIB_ZONE_D_BOUNDARY, float("inf")),
}


def classify_zone(rms_velocity_mms: float) -> str:
    """Return ISO 10816-3 zone letter for a given RMS velocity."""
    if rms_velocity_mms <= VIB_ZONE_B_BOUNDARY:
        return "A"
    if rms_velocity_mms <= VIB_ZONE_C_BOUNDARY:
        return "B"
    if rms_velocity_mms <= VIB_ZONE_D_BOUNDARY:
        return "C"
    return "D"


# ── Event dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class VibrationZoneEvent:
    """Layer 3 event emitted on zone change or Zone C/D entry."""

    device_id: str
    timestamp: datetime
    event_type: str = "vibration_zone"
    severity: str = "alert"
    rms_velocity_mms: float = 0.0
    zone: str = ""
    prev_zone: str = ""
    zone_changed: bool = False
    synthetic: bool = True
    threshold_refs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        d["event_id"] = str(uuid.uuid4())
        d["source_unit"] = "vibration_zone"
        return d


# ── Detector ─────────────────────────────────────────────────────────────


class VibrationZoneDetector:
    """Stateful per-device vibration zone classifier.

    Tracks the previous zone per device and emits events on:
    - Any zone transition (A→B, B→C, etc.)
    - Sustained Zone C or D (even without transition)

    Parameters
    ----------
    emit_on_cd_only : bool
        If True (default), only emit on Zone C/D or transitions
        involving C/D.  If False, emit on ANY zone change.
    """

    def __init__(self, emit_on_cd_only: bool = True) -> None:
        self._emit_cd_only = emit_on_cd_only
        # device_id → {"zone": str, "alerted_zone": str}
        self._state: dict[str, dict[str, str]] = {}

    def evaluate(self, sample: dict[str, Any]) -> VibrationZoneEvent | None:
        """Evaluate a single vibration reading.

        Parameters
        ----------
        sample : dict
            Must contain ``device_id``, ``timestamp``, and data fields
            for RMS velocity (``rms_velocity_mms`` or
            ``z_axis_rms_velocity_mm_sec``).

        Returns
        -------
        VibrationZoneEvent | None
        """
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        data = sample.get("data", sample)

        # Extract RMS velocity (accept multiple field names)
        rms = self._get_float(
            data,
            "rms_velocity_mms",
            "rms_velocity_combined_mms",
            "z_axis_rms_velocity_mm_sec",
            "rms_velocity_mm_sec",
        )

        if rms is None or rms < 0:
            return None

        zone = classify_zone(rms)

        # Initialise device state
        state = self._state.get(device_id)
        if state is None:
            state = {"zone": zone, "alerted_zone": ""}
            self._state[device_id] = state

        prev_zone = state["zone"]
        zone_changed = zone != prev_zone
        state["zone"] = zone

        # Determine severity
        severity = "info"
        if zone == "C":
            severity = "alert"
        elif zone == "D":
            severity = "critical"

        # Decide whether to emit
        should_emit = False
        if zone in ("C", "D"):
            # Always emit on C/D if we haven't alerted for this zone yet
            if state["alerted_zone"] != zone:
                should_emit = True
        elif zone_changed and not self._emit_cd_only:
            should_emit = True

        if should_emit:
            state["alerted_zone"] = zone
            return VibrationZoneEvent(
                device_id=device_id,
                timestamp=ts,
                rms_velocity_mms=round(rms, 3),
                zone=zone,
                prev_zone=prev_zone,
                zone_changed=zone_changed,
                severity=severity,
                synthetic=sample.get("synthetic", True),
                threshold_refs={
                    "zone_b_boundary_mms": VIB_ZONE_B_BOUNDARY,
                    "zone_c_boundary_mms": VIB_ZONE_C_BOUNDARY,
                    "zone_d_boundary_mms": VIB_ZONE_D_BOUNDARY,
                    "iso_standard": "ISO 10816-3 Class II",
                    "note": "PLACEHOLDER — reconcile against site machine nameplate",
                },
            )

        # On transition back to A/B, clear the alert so future C/D re-fires
        if zone in ("A", "B"):
            state["alerted_zone"] = ""

        return None

    def reset(self, device_id: str | None = None) -> None:
        """Reset state for one device or all."""
        if device_id:
            self._state.pop(device_id, None)
        else:
            self._state.clear()

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
