"""
omniview.rules.demand_slots — 96-Slot Day-Ahead Demand Aggregator (Feature 3)
=============================================================================

Aggregates 96-slot (15-minute intervals, 24 hours) day-ahead grid demand profiles.
Implements the Health Attachment contract from LLD Section 4 (lines 85 & 89):

    "Health attachment. If feature 2 reports a machine down for service,
    drop that machine's labeled share from the affected slots. The share
    is an input value on the machine record. It is not a new demand equation."

    "One test that a 96-slot call returns 96 slots and carries synthetic: true
    on campus history. One test that a 'machine in maintenance' flag reduces
    the labeled share and does not change the HD-graph function."

Reference:
- Docs/DS/LLD_Four_Core_Features.md §4
- Docs/DS/HD_graph_Master_Demand_Blueprint.md
- Jira Epic OI-136 / OI-154
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from omniview.rules.predictive_maintenance import get_machine_service_status

logger = logging.getLogger(__name__)

NUM_SLOTS_PER_DAY = 96
SLOT_DURATION_MINUTES = 15


@dataclass(frozen=True)
class MachineRecord:
    """Equipment record defining its labeled share in total campus grid demand.

    Parameters
    ----------
    machine_id : str
        Machine identifier (e.g. "isbm-main-feed", "compressor-01").
    labeled_share_kw : float
        Nominal active load drawn by this machine during production (in kW).
    affected_slots : list[int], optional
        Slots affected by this machine (0 to 95). If None, defaults to all 96 slots.
    name : str, optional
        Human-readable name or description of the equipment.
    """

    machine_id: str
    labeled_share_kw: float
    affected_slots: list[int] | None = None
    name: str = ""

    def get_effective_slots(self) -> set[int]:
        if self.affected_slots is None:
            return set(range(NUM_SLOTS_PER_DAY))
        return set(s for s in self.affected_slots if 0 <= s < NUM_SLOTS_PER_DAY)


@dataclass
class SlotDemand:
    """Demand state for a single 15-minute slot (1 of 96).

    Parameters
    ----------
    slot_index : int
        Slot index in range 0..95.
    time_label : str
        Start time of the interval ("HH:MM").
    baseline_kw : float
        Forecasted active demand prior to health adjustments.
    adjusted_kw : float
        Demand after dropping shares for machines in service/maintenance.
    excluded_kw : float
        Total kW curtailed due to machine maintenance.
    machines_in_maintenance : list[str]
        List of machine IDs down for service during this slot.
    """

    slot_index: int
    time_label: str
    baseline_kw: float
    adjusted_kw: float
    excluded_kw: float = 0.0
    machines_in_maintenance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DayAheadDemandPlan:
    """Full 24-hour day-ahead demand forecast comprising exactly 96 slots.

    Parameters
    ----------
    date : str
        Forecast date string (YYYY-MM-DD).
    slots : list[SlotDemand]
        The 96 fifteen-minute demand intervals.
    synthetic : bool, default True
        Whether the profile incorporates synthetic/campus history.
    total_baseline_kwh : float
        Integrated energy across the day before health exclusions.
    total_adjusted_kwh : float
        Integrated energy across the day after dropping offline shares.
    total_curtailed_kwh : float
        Total energy reduction from machines undergoing service.
    machines_down_for_service : list[str]
        Distinct machine IDs identified as down for service.
    """

    date: str
    slots: list[SlotDemand]
    synthetic: bool = True
    total_baseline_kwh: float = 0.0
    total_adjusted_kwh: float = 0.0
    total_curtailed_kwh: float = 0.0
    machines_down_for_service: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "slot_count": len(self.slots),
            "synthetic": self.synthetic,
            "total_baseline_kwh": round(self.total_baseline_kwh, 2),
            "total_adjusted_kwh": round(self.total_adjusted_kwh, 2),
            "total_curtailed_kwh": round(self.total_curtailed_kwh, 2),
            "machines_down_for_service": list(self.machines_down_for_service),
            "slots": [s.to_dict() for s in self.slots],
        }


def format_slot_time(slot_index: int) -> str:
    """Return 'HH:MM' string for a 0..95 slot index."""
    minutes_from_midnight = (slot_index % NUM_SLOTS_PER_DAY) * SLOT_DURATION_MINUTES
    hours = minutes_from_midnight // 60
    mins = minutes_from_midnight % 60
    return f"{hours:02d}:{mins:02d}"


def generate_baseline_campus_slots(
    peak_kw: float = 430.0,
    base_kw: float = 190.0,
) -> list[float]:
    """Generate realistic diurnal 96-slot campus baseline profile (in kW).

    Simulates standard industrial shift patterns:
    - Shift 1 (08:00–16:00, slots 32–64): High production ramp & peak.
    - Shift 2 (16:00–24:00, slots 64–95): Active production with slight evening peak.
    - Shift 3 / Night (00:00–08:00, slots 0–31): Reduced baseline & auxiliary load.
    """
    slots: list[float] = []
    for s in range(NUM_SLOTS_PER_DAY):
        # Sine-modulated day-shift hump centered at 13:00 (slot 52)
        radian = (s - 16) * (2 * math.pi / NUM_SLOTS_PER_DAY)
        modulation = max(0.0, math.sin(radian / 2)) ** 2
        kw = base_kw + (peak_kw - base_kw) * modulation
        slots.append(round(kw, 2))
    return slots


def aggregate_96_slot_demand(
    baseline_slots: list[float] | None = None,
    machine_records: list[MachineRecord] | None = None,
    date_str: str | None = None,
    synthetic: bool = True,
    service_status_fn: Callable[[str], bool] | None = None,
) -> DayAheadDemandPlan:
    """Compute 96-slot day-ahead demand plan, dropping machines flagged for maintenance.

    Parameters
    ----------
    baseline_slots : list[float], optional
        List of 96 baseline kW demands. If None, generates realistic campus baseline.
    machine_records : list[MachineRecord], optional
        List of machine records with their labeled kW shares.
    date_str : str, optional
        Target plan date (YYYY-MM-DD). Defaults to current UTC date.
    synthetic : bool, default True
        Carries synthetic flag per LLD §4 line 89.
    service_status_fn : Callable[[str], bool], optional
        Function to check whether a machine is down for service.
        Defaults to ``get_machine_service_status``.

    Returns
    -------
    DayAheadDemandPlan
        Container with 96 adjusted slots, curtailed energy totals, and excluded machines.
    """
    check_status = service_status_fn or get_machine_service_status

    if baseline_slots is None:
        raw_baselines = generate_baseline_campus_slots()
    else:
        raw_baselines = list(baseline_slots)
        # Pad or truncate strictly to 96 slots
        if len(raw_baselines) < NUM_SLOTS_PER_DAY:
            last_val = raw_baselines[-1] if raw_baselines else 250.0
            raw_baselines.extend([last_val] * (NUM_SLOTS_PER_DAY - len(raw_baselines)))
        elif len(raw_baselines) > NUM_SLOTS_PER_DAY:
            raw_baselines = raw_baselines[:NUM_SLOTS_PER_DAY]

    target_date = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    machines = machine_records or []

    # Identify which machines are flagged for maintenance
    down_machines: dict[str, MachineRecord] = {}
    for m in machines:
        if check_status(m.machine_id):
            down_machines[m.machine_id] = m
            logger.info(
                "Health Attachment: Machine '%s' is down for service — excluding %.1f kW share",
                m.machine_id,
                m.labeled_share_kw,
            )

    slots: list[SlotDemand] = []
    total_base_kwh = 0.0
    total_adj_kwh = 0.0

    for s_idx, base_val in enumerate(raw_baselines):
        time_lbl = format_slot_time(s_idx)
        adj_val = base_val
        curtailed_kw = 0.0
        active_down: list[str] = []

        for m_id, m_rec in down_machines.items():
            if s_idx in m_rec.get_effective_slots():
                adj_val = max(0.0, adj_val - m_rec.labeled_share_kw)
                curtailed_kw += m_rec.labeled_share_kw
                active_down.append(m_id)

        slots.append(
            SlotDemand(
                slot_index=s_idx,
                time_label=time_lbl,
                baseline_kw=round(base_val, 2),
                adjusted_kw=round(adj_val, 2),
                excluded_kw=round(curtailed_kw, 2),
                machines_in_maintenance=active_down,
            )
        )

        # 15 minutes = 0.25 hours
        total_base_kwh += base_val * (SLOT_DURATION_MINUTES / 60.0)
        total_adj_kwh += adj_val * (SLOT_DURATION_MINUTES / 60.0)

    curtailed_kwh = max(0.0, total_base_kwh - total_adj_kwh)

    return DayAheadDemandPlan(
        date=target_date,
        slots=slots,
        synthetic=synthetic,
        total_baseline_kwh=round(total_base_kwh, 2),
        total_adjusted_kwh=round(total_adj_kwh, 2),
        total_curtailed_kwh=round(curtailed_kwh, 2),
        machines_down_for_service=sorted(down_machines.keys()),
    )


__all__ = [
    "NUM_SLOTS_PER_DAY",
    "SLOT_DURATION_MINUTES",
    "MachineRecord",
    "SlotDemand",
    "DayAheadDemandPlan",
    "format_slot_time",
    "generate_baseline_campus_slots",
    "aggregate_96_slot_demand",
]

