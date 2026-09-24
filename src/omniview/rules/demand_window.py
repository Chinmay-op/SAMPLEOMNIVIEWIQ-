"""
F02 — Live 15-Minute Max-Demand Risk Detector (``md_risk``)
============================================================

Deterministic window-integral detector that mirrors MSEDCL's own
15-minute integration period.  Fires an ``md_risk`` event when the
projected average demand for the current window is forecast to
breach the contracted demand — with enough lead time (~4 min) for
a human to shed load.

Algorithm (no ML)::

    Per tick (≤15 s cadence):
        kva = normalize(raw)
        Δt  = tick.timestamp − prev.timestamp   (minutes)
        accumulated_kva_minutes += kva × Δt

    Mid-window projection:
        projected = (accumulated + kva × time_remaining) / 15

    Alert condition:
        projected ≥ contract_demand  AND  T_minutes ≥ MD_ALERT_MINUTE

Design rationale:
    Must match MSEDCL's own billing integration exactly — no room for
    a learned approximation.  A deterministic integral is defensible
    against the client's bill.

Reference: Feature Spec F02, Layer 3 contract §4.1, PRD FR3–FR4.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.config import (
    CONTRACTED_DEMAND_KVA,
    MD_ALERT_MINUTE,
    MD_WINDOW_MINUTES,
)

logger = logging.getLogger(__name__)


# ── Event dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class MDRiskEvent:
    """Layer 3 event emitted when projected demand breaches contract."""

    device_id: str
    timestamp: datetime
    event_type: str = "md_risk"
    severity: str = "critical"
    kva: float = 0.0
    accumulated_kva_minutes: float = 0.0
    projected_demand_kva: float = 0.0
    avg_demand_kva: float = 0.0
    session_peak_demand: float = 0.0
    contract_demand: float = CONTRACTED_DEMAND_KVA
    t_minutes: float = 0.0
    window_start: str = ""
    window_end: str = ""
    slot_of_day: int = 0
    projected_breach: bool = False
    synthetic: bool = True
    threshold_refs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        d["event_id"] = str(uuid.uuid4())
        d["source_unit"] = "demand_window"
        return d


# ── Detector ─────────────────────────────────────────────────────────────


class DemandWindowDetector:
    """Stateful rolling 15-minute kVA demand window detector.

    Tracks accumulated kVA-minutes within the current MSEDCL integration
    window and projects whether the average will breach the contracted
    demand.

    Parameters
    ----------
    contract_demand_kva : float
        Contracted sanctioned demand (default from config).
    window_minutes : int
        Integration window length (default 15, per MSEDCL).
    alert_minute : int
        Minute within the window at which to fire (default 11).
    """

    def __init__(
        self,
        contract_demand_kva: float = CONTRACTED_DEMAND_KVA,
        window_minutes: int = MD_WINDOW_MINUTES,
        alert_minute: int = MD_ALERT_MINUTE,
    ) -> None:
        self._contract = contract_demand_kva
        self._window_min = window_minutes
        self._alert_min = alert_minute

        # Per-window state
        self._accumulated: float = 0.0
        self._window_start: datetime | None = None
        self._prev_ts: datetime | None = None
        self._peak_kva: float = 0.0
        self._alerted_this_window: bool = False

    def evaluate(self, sample: dict[str, Any]) -> MDRiskEvent | None:
        """Evaluate a single electrical reading.

        Parameters
        ----------
        sample : dict
            Must contain ``timestamp`` and either ``kva`` (adapted) or
            ``apparent_power_kva_total`` (raw DevB).  Also accepts
            ``kw`` + ``var`` for √(kw² + var²) fallback.

        Returns
        -------
        MDRiskEvent | None
        """
        ts = self._parse_timestamp(sample)
        data = sample.get("data", sample)

        # Resolve kVA from available fields
        kva = self._resolve_kva(data)
        if kva is None or kva < 0:
            return None

        # Track peak
        self._peak_kva = max(self._peak_kva, kva)

        # Window management
        if self._window_start is None:
            self._reset_window(ts)

        elapsed_min = (ts - self._window_start).total_seconds() / 60.0

        # Window rollover
        if elapsed_min >= self._window_min:
            self._reset_window(ts)
            elapsed_min = 0.0

        # Accumulate kVA-minutes
        if self._prev_ts is not None:
            dt_min = (ts - self._prev_ts).total_seconds() / 60.0
            if 0 < dt_min <= 2.0:  # sanity: skip gaps > 2 min
                self._accumulated += kva * dt_min

        self._prev_ts = ts

        # Project
        time_remaining = max(0, self._window_min - elapsed_min)
        if elapsed_min > 0:
            projected = (self._accumulated + kva * time_remaining) / self._window_min
        else:
            projected = kva

        avg = self._accumulated / elapsed_min if elapsed_min > 0 else kva

        # Alert condition: projected breach AND past alert minute
        projected_breach = projected >= self._contract

        if (
            projected_breach
            and elapsed_min >= self._alert_min
            and not self._alerted_this_window
        ):
            self._alerted_this_window = True

            hour = ts.hour
            minute = ts.minute
            slot = (hour * 60 + minute) // self._window_min

            return MDRiskEvent(
                device_id=sample.get("device_id", "unknown"),
                timestamp=ts,
                kva=round(kva, 2),
                accumulated_kva_minutes=round(self._accumulated, 2),
                projected_demand_kva=round(projected, 2),
                avg_demand_kva=round(avg, 2),
                session_peak_demand=round(self._peak_kva, 2),
                contract_demand=self._contract,
                t_minutes=round(elapsed_min, 1),
                window_start=self._window_start.isoformat(),
                window_end="",
                slot_of_day=slot,
                projected_breach=True,
                synthetic=sample.get("synthetic", True),
                threshold_refs={
                    "contract_demand_kva": self._contract,
                    "alert_minute": self._alert_min,
                    "window_minutes": self._window_min,
                },
            )

        return None

    def reset(self) -> None:
        """Reset all state."""
        self._accumulated = 0.0
        self._window_start = None
        self._prev_ts = None
        self._peak_kva = 0.0
        self._alerted_this_window = False

    def _reset_window(self, ts: datetime) -> None:
        self._accumulated = 0.0
        self._window_start = ts
        self._alerted_this_window = False

    @staticmethod
    def _resolve_kva(data: dict[str, Any]) -> float | None:
        """Resolve kVA from adapted or raw field names."""
        # Adapted short name
        if "kva" in data:
            try:
                return float(data["kva"])
            except (ValueError, TypeError):
                return None

        # Raw DevB name
        if "apparent_power_kva_total" in data:
            try:
                return float(data["apparent_power_kva_total"])
            except (ValueError, TypeError):
                return None

        # Fallback: √(kw² + var²)
        kw = data.get("kw") or data.get("active_power_kw_total")
        var = data.get("var") or data.get("reactive_power_kvar_total")
        if kw is not None and var is not None:
            try:
                return math.sqrt(float(kw) ** 2 + float(var) ** 2)
            except (ValueError, TypeError):
                return None

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
