"""
omniview.rules.waste_schedule — Waste Schedule Composer (Feature 4)
===================================================================

Composes the Feature 4 ``waste_schedule`` report per LLD Section 5:
- Reads lazy-idle waste, loaded pressure, stroke bot count, demand plan,
  and Feature 2 maintenance service flag.
- Emits ``waste_schedule`` with:
    - ``machine_id``
    - ``best_run_hour``
    - ``stop_hour``
    - ``waste_where`` (``lazy_idle``, ``pressure_loaded``, ``cooling``, or ``none``)
    - ``production_rate``
    - ``synthetic``

Key Cross-Feature Contract (OI-154 / LLD §5 line 101):
    "Feature 4 waste_schedule composer verifies the flag before flagging lazy-idle waste."
    If a machine is flagged for service/maintenance, idle periods are expected
    and MUST NOT be falsely flagged as electrical waste.

Reference:
- Docs/DS/LLD_Four_Core_Features.md §5
- Jira Epic OI-133 / OI-154
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniview.rules.predictive_maintenance import get_machine_service_status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WasteSchedule:
    """Feature 4 Waste Schedule recommendation record.

    Parameters
    ----------
    machine_id : str
        Target equipment ID.
    best_run_hour : int
        Recommended hour of day (0..23) to run this equipment.
    stop_hour : int
        Hour of day (0..23) when equipment should pause or shut down.
    waste_where : str
        Source of identified waste: ``"lazy_idle"``, ``"pressure_loaded"``,
        ``"cooling"``, or ``"none"``.
    production_rate : float
        Units produced per hour (from stroke bot count).
    synthetic : bool, default True
        Whether the schedule incorporates synthetic/historical fixtures.
    waste_identified : bool, default False
        True if actionable energy waste was detected.
    details : dict[str, Any], optional
        Additional context (e.g. suppression reason, energy kWh wasted).
    """

    machine_id: str
    best_run_hour: int
    stop_hour: int
    waste_where: str
    production_rate: float
    synthetic: bool = True
    waste_identified: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_slot_kw(s: Any) -> float:
    """Safely extract adjusted kW from a SlotDemand object, dict, or numeric value."""
    if hasattr(s, "adjusted_kw"):
        return float(s.adjusted_kw)
    if isinstance(s, dict):
        val = s.get("adjusted_kw", s.get("kw", 0.0))
        return float(val)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def compose_waste_schedule(
    machine_id: str,
    demand_plan: Any | None = None,
    lazy_idle_events: list[Any] | None = None,
    stroke_count: int | float = 0,
    pressure_events: list[Any] | None = None,
    cooling_events: list[Any] | None = None,
    is_in_maintenance: bool | None = None,
    synthetic: bool = True,
    best_run_hour_fallback: int = 10,
    stop_hour_fallback: int = 18,
) -> WasteSchedule:
    """Compose a WasteSchedule report for a machine.

    Verifies the Feature 2 service flag before classifying waste:
    - If the machine is down for service/maintenance, idle stretches are
      technician activities (e.g. heater tests, calibrations) and are NOT
      flagged as electrical waste.
    - If the machine is healthy/online, evaluates lazy-idle, pressure leak,
      and thermal-cooling events against the demand plan.

    Parameters
    ----------
    machine_id : str
        Machine identifier.
    demand_plan : Any, optional
        Day-ahead demand plan (or DayAheadDemandPlan object / dict).
    lazy_idle_events : list, optional
        Detected LazyIdleEvent instances or dicts for this machine.
    stroke_count : int or float, default 0
        Observed production stroke count.
    pressure_events : list, optional
        Pressure leak events detected during loaded cycle.
    cooling_events : list, optional
        Cooling malfunction events detected.
    is_in_maintenance : bool, optional
        Override for maintenance status. Defaults to ``get_machine_service_status(machine_id)``.
    synthetic : bool, default True
        Carries synthetic flag.
    best_run_hour_fallback : int, default 10
        Default best production hour if not derived from demand plan.
    stop_hour_fallback : int, default 18
        Default shutdown/peak hour if not derived from demand plan.

    Returns
    -------
    WasteSchedule
    """
    # 1. Check Feature 2 Health Service Flag (OI-154 / LLD §5 line 101)
    if is_in_maintenance is None:
        in_maintenance = get_machine_service_status(machine_id)
    else:
        in_maintenance = bool(is_in_maintenance)

    # Calculate production rate (e.g., strokes per hour)
    prod_rate = float(stroke_count)

    # Derive best_run_hour and stop_hour from demand plan if available
    best_hour = best_run_hour_fallback
    stop_hour = stop_hour_fallback

    if demand_plan is not None:
        slots = None
        if hasattr(demand_plan, "slots"):
            slots = demand_plan.slots
        elif isinstance(demand_plan, dict) and "slots" in demand_plan:
            slots = demand_plan["slots"]

        if slots and len(slots) >= 96:
            # Group into 24 hours (4 slots per hour)
            hourly_kw: list[float] = []
            for h in range(24):
                h_slots = slots[h * 4 : (h + 1) * 4]
                avg_kw = sum(_get_slot_kw(s) for s in h_slots) / 4.0
                hourly_kw.append(avg_kw)

            # Best run hour is lowest grid demand / off-peak hour during day shift
            day_hours = list(range(6, 18))
            best_hour = min(day_hours, key=lambda h: hourly_kw[h])

            # Stop hour is peak demand hour (highest grid load)
            stop_hour = max(range(24), key=lambda h: hourly_kw[h])

    # 2. If machine is in maintenance, suppress false waste alerts
    if in_maintenance:
        logger.info(
            "Waste Schedule: Machine '%s' is in maintenance — suppressing electrical waste alerts",
            machine_id,
        )
        return WasteSchedule(
            machine_id=machine_id,
            best_run_hour=best_hour,
            stop_hour=stop_hour,
            waste_where="none",
            production_rate=prod_rate,
            synthetic=synthetic,
            waste_identified=False,
            details={
                "maintenance_suppressed": True,
                "reason": (
                    "Machine is under active service/maintenance (Health Index in critical tier "
                    "or scheduled maintenance window). Idle periods are excluded from waste flagging."
                ),
            },
        )

    # 3. Healthy / active machine: detect where the waste is
    waste_where = "none"
    waste_identified = False
    details: dict[str, Any] = {}

    if lazy_idle_events:
        waste_where = "lazy_idle"
        waste_identified = True
        first_event = lazy_idle_events[0]
        # Identify hour when waste occurred
        event_ts = getattr(first_event, "timestamp", None)
        if isinstance(first_event, dict):
            event_ts = first_event.get("timestamp")
        if isinstance(event_ts, datetime):
            stop_hour = event_ts.hour
        details["lazy_idle_event_count"] = len(lazy_idle_events)

    elif pressure_events:
        waste_where = "pressure_loaded"
        waste_identified = True
        details["pressure_event_count"] = len(pressure_events)

    elif cooling_events:
        waste_where = "cooling"
        waste_identified = True
        details["cooling_event_count"] = len(cooling_events)

    return WasteSchedule(
        machine_id=machine_id,
        best_run_hour=best_hour,
        stop_hour=stop_hour,
        waste_where=waste_where,
        production_rate=prod_rate,
        synthetic=synthetic,
        waste_identified=waste_identified,
        details=details,
    )


__all__ = [
    "WasteSchedule",
    "compose_waste_schedule",
]
