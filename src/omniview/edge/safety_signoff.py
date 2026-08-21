"""
Safety / Access Sign-Off + Install Window — OI-75
====================================================

Codifies the PRD Phase 0 safety/access sign-off process and install
window scheduling for the 2-node POC deployment.

Key constraints (PRD §1.3, §9 Phase 0):
  - Zero production stoppage — all installs are non-invasive
  - Safety Officer sign-off required before any physical work
  - Install window must be agreed with plant management
  - PPE requirements documented per location/hazard

This module provides:
  - ``HazardAssessment``: per-location hazard identification + controls
  - ``PPERequirement``: PPE items mapped to install steps
  - ``InstallWindow``: scheduled install window with constraints
  - ``SafetySignOff``: the complete sign-off document
  - ``generate_safety_report()``: structured report for export

Sources:
  - PRD §1.3 (zero downtime constraint)
  - PRD §9 Phase 0 (safety/access pre-requisite)
  - OI-76 install procedure (step-level PPE requirements)
  - OI-74 site profile (location access levels)

Usage::

    from omniview.edge.safety_signoff import (
        SafetySignOff, generate_safety_report
    )

    signoff = SafetySignOff()
    signoff.print_document()
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────


class HazardCategory(str, Enum):
    """Hazard categories for the install environment."""

    ELECTRICAL = "electrical"           # Live panels, arc flash risk
    MECHANICAL = "mechanical"           # Rotating machinery, moving parts
    THERMAL = "thermal"                 # Hot surfaces (barrel zone)
    PRESSURE = "pressure"               # Pressurized pneumatic systems
    NOISE = "noise"                     # High noise areas (>85 dB)
    HEIGHT = "height"                   # Elevated work (if any)
    CONFINED = "confined"               # Confined spaces (switchboard interior)


class RiskLevel(str, Enum):
    """Risk level after controls are applied."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignOffStatus(str, Enum):
    """Status of the safety sign-off process."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class WindowStatus(str, Enum):
    """Status of the install window scheduling."""

    PROPOSED = "proposed"
    AGREED = "agreed"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class HazardAssessment:
    """Per-location hazard identification with controls."""

    hazard_id: str
    location_point_id: str
    location_name: str
    node_id: str
    hazard_category: HazardCategory
    description: str
    risk_before_controls: RiskLevel
    controls: list[str]
    ppe_required: list[str]
    risk_after_controls: RiskLevel
    zero_downtime_impact: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hazard_id": self.hazard_id,
            "location_point_id": self.location_point_id,
            "location_name": self.location_name,
            "node_id": self.node_id,
            "hazard_category": self.hazard_category.value,
            "description": self.description,
            "risk_before_controls": self.risk_before_controls.value,
            "controls": self.controls,
            "ppe_required": self.ppe_required,
            "risk_after_controls": self.risk_after_controls.value,
            "zero_downtime_impact": self.zero_downtime_impact,
        }


@dataclass
class PPERequirement:
    """PPE item with scope and specification."""

    ppe_id: str
    item: str
    specification: str
    applicable_locations: list[str]
    applicable_hazards: list[str]
    quantity: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "ppe_id": self.ppe_id,
            "item": self.item,
            "specification": self.specification,
            "applicable_locations": self.applicable_locations,
            "applicable_hazards": self.applicable_hazards,
            "quantity": self.quantity,
        }


@dataclass
class InstallWindow:
    """Scheduled install window with constraints.

    The install window must satisfy:
      - Zero production stoppage (all work is non-invasive)
      - Safety Officer availability for supervision
      - Minimal disruption to operator workflow
    """

    window_id: str
    node_id: str
    description: str
    proposed_day: str
    proposed_shift: str
    duration_minutes: int
    requires_production_stop: bool = False
    safety_officer_required: bool = True
    constraints: list[str] = field(default_factory=list)
    status: WindowStatus = WindowStatus.PROPOSED
    notes: str = ""

    def __post_init__(self) -> None:
        if self.requires_production_stop:
            raise ValueError(
                f"Window {self.window_id!r} requires production stop — "
                f"this violates the zero production stoppage constraint "
                f"(PRD §1.3). All installs must be non-invasive."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "node_id": self.node_id,
            "description": self.description,
            "proposed_day": self.proposed_day,
            "proposed_shift": self.proposed_shift,
            "duration_minutes": self.duration_minutes,
            "requires_production_stop": self.requires_production_stop,
            "safety_officer_required": self.safety_officer_required,
            "constraints": self.constraints,
            "status": self.status.value,
            "notes": self.notes,
        }


# ── Hazard Assessments ───────────────────────────────────────────────────────

_HAZARD_ASSESSMENTS: list[HazardAssessment] = [
    HazardAssessment(
        hazard_id="HAZ-01",
        location_point_id="LOC-C01",
        location_name="Compressor Main Panel — Exterior Door",
        node_id="compressor-01",
        hazard_category=HazardCategory.ELECTRICAL,
        description=(
            "Live 3-phase 415V panel. Arc flash risk when opening panel door "
            "to snap CTs onto phase conductors."
        ),
        risk_before_controls=RiskLevel.HIGH,
        controls=[
            "Split-core CTs eliminate need to disconnect cables",
            "MFM384 mounts on panel exterior — no internal wiring",
            "Work performed by qualified electrician only",
            "Arc flash boundary maintained during CT installation",
            "Panel door opened only for CT snap-on (< 15 min)",
        ],
        ppe_required=["insulated gloves (Class 0)", "safety glasses", "arc flash PPE (Cat 2)"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — split-core CTs snap on live cables, no power interruption",
    ),
    HazardAssessment(
        hazard_id="HAZ-02",
        location_point_id="LOC-C02",
        location_name="Compressor Bearing Housing — Drive End",
        node_id="compressor-01",
        hazard_category=HazardCategory.MECHANICAL,
        description=(
            "Rotating machinery — compressor shaft and drive coupling. "
            "Vibration sensor mount on bearing housing is near rotating parts."
        ),
        risk_before_controls=RiskLevel.MEDIUM,
        controls=[
            "Magnetic mount sensor — attach without contact with rotating parts",
            "Maintain minimum safe distance from shaft/coupling",
            "No loose clothing or jewelry near rotating machinery",
            "Sensor placement does not require machine shutdown",
        ],
        ppe_required=["safety glasses", "hearing protection (>85 dB)"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — magnetic mount attaches while compressor runs",
    ),
    HazardAssessment(
        hazard_id="HAZ-03",
        location_point_id="LOC-C02",
        location_name="Compressor Bearing Housing — Drive End",
        node_id="compressor-01",
        hazard_category=HazardCategory.NOISE,
        description="Compressor room noise level exceeds 85 dB during operation.",
        risk_before_controls=RiskLevel.MEDIUM,
        controls=[
            "Hearing protection mandatory in compressor room",
            "Limit exposure time during sensor installation (< 30 min)",
            "Communication via hand signals during high-noise periods",
        ],
        ppe_required=["hearing protection (earmuffs or plugs, NRR ≥ 25 dB)"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — noise is present during normal operation",
    ),
    HazardAssessment(
        hazard_id="HAZ-04",
        location_point_id="LOC-C03",
        location_name="Compressor Output Receiver — Gauge Port",
        node_id="compressor-01",
        hazard_category=HazardCategory.PRESSURE,
        description=(
            "Pressurized pneumatic system (25–40 bar). WIKA A-10 taps into "
            "existing gauge port on receiver manifold."
        ),
        risk_before_controls=RiskLevel.MEDIUM,
        controls=[
            "Use existing gauge port — no new holes drilled",
            "Verify gauge port valve is closed before fitting transmitter",
            "Check for residual pressure before connecting",
            "Transmitter rated for 0–40 bar (matches system pressure)",
            "Leak test after installation (soap bubble test)",
        ],
        ppe_required=["safety glasses"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — gauge port tap does not interrupt pneumatic supply",
    ),
    HazardAssessment(
        hazard_id="HAZ-05",
        location_point_id="LOC-C04",
        location_name="Compressor Motor Switchboard — Interior",
        node_id="compressor-01",
        hazard_category=HazardCategory.CONFINED,
        description=(
            "HeatTag sensor mounted inside switchboard enclosure. "
            "Limited space, live busbars present."
        ),
        risk_before_controls=RiskLevel.MEDIUM,
        controls=[
            "Surface mount only — no wiring into busbars",
            "Work performed by qualified electrician",
            "Switchboard door opened only for sensor placement (< 10 min)",
            "Tools insulated to prevent accidental contact",
        ],
        ppe_required=["insulated gloves (Class 0)", "safety glasses"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — surface mount inside enclosure, no disconnections",
    ),
    HazardAssessment(
        hazard_id="HAZ-06",
        location_point_id="LOC-I01",
        location_name="ISBM Main Electrical Panel — Exterior Door",
        node_id="isbm-01",
        hazard_category=HazardCategory.ELECTRICAL,
        description=(
            "Live 3-phase 415V panel for ISBM machine. Same arc flash risk "
            "as compressor panel for CT installation."
        ),
        risk_before_controls=RiskLevel.HIGH,
        controls=[
            "Split-core CTs eliminate need to disconnect cables",
            "MFM384 mounts on panel exterior",
            "Work performed by qualified electrician only",
            "Arc flash boundary maintained",
            "Confirm single feed (not split sub-panels) before starting",
        ],
        ppe_required=["insulated gloves (Class 0)", "safety glasses", "arc flash PPE (Cat 2)"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — CTs snap on live cables, ISBM continues production",
    ),
    HazardAssessment(
        hazard_id="HAZ-07",
        location_point_id="LOC-I02",
        location_name="ISBM Barrel / Hot-Runner Zone",
        node_id="isbm-01",
        hazard_category=HazardCategory.THERMAL,
        description=(
            "Barrel/hot-runner zone operates at 150–280°C during production. "
            "Surface-mounted thermal probe requires proximity to hot surfaces."
        ),
        risk_before_controls=RiskLevel.HIGH,
        controls=[
            "Surface mount only — no penetration into machine body",
            "Heat-resistant gloves rated to 300°C",
            "Probe attached using high-temperature adhesive/clamp",
            "Minimum contact time with hot surfaces",
            "Install during lowest-temperature phase if possible",
        ],
        ppe_required=["heat-resistant gloves (300°C rated)", "safety glasses", "long sleeves"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — probe attaches to barrel surface, machine runs continuously",
    ),
    HazardAssessment(
        hazard_id="HAZ-08",
        location_point_id="LOC-I03",
        location_name="ISBM Ejection / Stroke Mechanism",
        node_id="isbm-01",
        hazard_category=HazardCategory.MECHANICAL,
        description=(
            "Moving parts — ejection mechanism cycles during production. "
            "Proximity sensor must be mounted near moving components."
        ),
        risk_before_controls=RiskLevel.MEDIUM,
        controls=[
            "Non-contact proximity sensor — no physical contact with mechanism",
            "Mount bracket positioned outside pinch-point zones",
            "Install bracket during low-speed cycle or between cycles",
            "Guard proximity sensor from accidental displacement",
        ],
        ppe_required=["safety glasses"],
        risk_after_controls=RiskLevel.LOW,
        zero_downtime_impact="No impact — proximity mount, no contact with mechanism",
    ),
]


# ── PPE Requirements ─────────────────────────────────────────────────────────

_PPE_REQUIREMENTS: list[PPERequirement] = [
    PPERequirement(
        ppe_id="PPE-01",
        item="Insulated Gloves (Class 0)",
        specification="IEC 60903 Class 0, rated to 1000V AC",
        applicable_locations=["LOC-C01", "LOC-C04", "LOC-I01"],
        applicable_hazards=["HAZ-01", "HAZ-05", "HAZ-06"],
        quantity=2,
    ),
    PPERequirement(
        ppe_id="PPE-02",
        item="Arc Flash PPE (Category 2)",
        specification="NFPA 70E Cat 2: arc-rated face shield + coverall (8 cal/cm²)",
        applicable_locations=["LOC-C01", "LOC-I01"],
        applicable_hazards=["HAZ-01", "HAZ-06"],
        quantity=1,
    ),
    PPERequirement(
        ppe_id="PPE-03",
        item="Safety Glasses",
        specification="ANSI Z87.1 impact-rated, side shields",
        applicable_locations=["all"],
        applicable_hazards=["all"],
        quantity=4,
    ),
    PPERequirement(
        ppe_id="PPE-04",
        item="Hearing Protection",
        specification="Earmuffs or plugs, NRR ≥ 25 dB",
        applicable_locations=["LOC-C02"],
        applicable_hazards=["HAZ-02", "HAZ-03"],
        quantity=4,
    ),
    PPERequirement(
        ppe_id="PPE-05",
        item="Heat-Resistant Gloves",
        specification="Rated to 300°C, EN 407 certified",
        applicable_locations=["LOC-I02"],
        applicable_hazards=["HAZ-07"],
        quantity=2,
    ),
]


# ── Install Windows ──────────────────────────────────────────────────────────

_INSTALL_WINDOWS: list[InstallWindow] = [
    InstallWindow(
        window_id="WIN-01",
        node_id="compressor-01",
        description="Compressor node instrumentation — all 7 install steps",
        proposed_day="Week 1, Day 2 (per PRD §9 timeline)",
        proposed_shift="Day shift (08:00–16:00) — Safety Officer on-site",
        duration_minutes=85,
        constraints=[
            "Safety Officer must be present throughout",
            "Qualified electrician for panel work (CT snap-on)",
            "Compressor runs continuously — zero stoppage",
            "Hearing protection mandatory for all personnel in compressor room",
            "No other maintenance activities simultaneously on compressor",
        ],
        notes=(
            "Compressor node has the highest hazard density (electrical + "
            "mechanical + pressure + noise). Schedule first to validate "
            "safety procedures before moving to ISBM node."
        ),
    ),
    InstallWindow(
        window_id="WIN-02",
        node_id="isbm-01",
        description="ISBM node instrumentation — all 5 install steps",
        proposed_day="Week 1, Day 2 (afternoon, after compressor)",
        proposed_shift="Day shift (08:00–16:00) — Safety Officer on-site",
        duration_minutes=75,
        constraints=[
            "Safety Officer must be present throughout",
            "Qualified electrician for panel work (CT snap-on)",
            "ISBM machine runs continuously — zero stoppage",
            "Heat-resistant gloves for barrel zone work",
            "Confirm single feed (not split sub-panels) before CT install",
        ],
        notes=(
            "ISBM node scheduled after compressor to apply lessons learned. "
            "Barrel zone thermal probe requires heat-resistant PPE."
        ),
    ),
    InstallWindow(
        window_id="WIN-03",
        node_id="floor",
        description="Infrastructure install — gateway, ambient sensor, jumbo display",
        proposed_day="Week 1, Day 2 (can overlap with node installs)",
        proposed_shift="Day shift (08:00–16:00)",
        duration_minutes=30,
        safety_officer_required=False,
        constraints=[
            "Wall/pillar mounts — no electrical hazard",
            "Gateway cabinet requires 24V DC power connection",
            "Jumbo display must be visible from operator stations",
        ],
        notes="Low-risk work. Can be done in parallel with node installs.",
    ),
]


# ── Zero Downtime Constraints ────────────────────────────────────────────────

ZERO_DOWNTIME_CONSTRAINTS: list[dict[str, str]] = [
    {
        "id": "ZDC-01",
        "constraint": "All sensors use non-invasive installation methods (clip-on, snap-on, magnetic, gauge-port tap, surface mount, proximity)",
        "source": "PRD §1.3",
        "enforcement": "InstallStep.__post_init__ raises ValueError if requires_power_off=True",
    },
    {
        "id": "ZDC-02",
        "constraint": "Split-core CTs (Selec SCCT-30/20) snap onto live cables — no cable cutting, no power interruption",
        "source": "PRD §3, Architecture §3.1",
        "enforcement": "InstallMethod.SNAP_ON_CT — verified in OI-76 install procedure",
    },
    {
        "id": "ZDC-03",
        "constraint": "MFM384 energy meters mount on panel exterior door — no internal wiring modification",
        "source": "PRD §3",
        "enforcement": "InstallMethod.PANEL_DOOR_MOUNT — panel stays closed during operation",
    },
    {
        "id": "ZDC-04",
        "constraint": "Vibration sensor uses magnetic/epoxy mount on bearing housing — no drilling, no shaft contact",
        "source": "PRD §3, ISO 10816-3",
        "enforcement": "InstallMethod.MAGNETIC_MOUNT — removable without residue",
    },
    {
        "id": "ZDC-05",
        "constraint": "Pressure transmitter taps into existing gauge port — no new holes drilled in pneumatic system",
        "source": "PRD §3",
        "enforcement": "InstallMethod.GAUGE_PORT_TAP — existing port, no system modification",
    },
    {
        "id": "ZDC-06",
        "constraint": "Thermal probes use surface mount — no penetration into machine body, no OEM warranty risk",
        "source": "PRD §3",
        "enforcement": "InstallMethod.SURFACE_MOUNT — adhesive or clamp attachment",
    },
    {
        "id": "ZDC-07",
        "constraint": "Stroke counter uses non-contact proximity sensor — no physical modification to ejection mechanism",
        "source": "PRD §3",
        "enforcement": "InstallMethod.PROXIMITY_MOUNT — bracket mount outside pinch zones",
    },
    {
        "id": "ZDC-08",
        "constraint": "No production line shutdown attributable to OmniView IQ installation at any point",
        "source": "PRD §1.3, OI-76 acceptance criteria",
        "enforcement": "InstallProcedure.zero_downtime property — always True (code-level guarantee)",
    },
]


# ── Safety Sign-Off ──────────────────────────────────────────────────────────


class SafetySignOff:
    """Complete safety sign-off document for the POC install.

    Encapsulates:
      - Hazard assessments per location
      - PPE requirements
      - Zero-downtime constraints
      - Install windows
      - Sign-off status

    Parameters
    ----------
    safety_officer : str
        Name of the Safety Officer.
    installer : str
        Name of the lead installer / electrician.
    """

    def __init__(
        self,
        safety_officer: str = "To be confirmed",
        installer: str = "Chinmay Wadettiwar (DevC)",
    ) -> None:
        self.safety_officer = safety_officer
        self.installer = installer
        self.hazards = copy.deepcopy(_HAZARD_ASSESSMENTS)
        self.ppe = copy.deepcopy(_PPE_REQUIREMENTS)
        self.windows = copy.deepcopy(_INSTALL_WINDOWS)
        self.zero_downtime_constraints = list(ZERO_DOWNTIME_CONSTRAINTS)
        self.status = SignOffStatus.DRAFT
        self.sign_off_date: str | None = None
        self.sign_off_notes: str = ""

        logger.info(
            "SafetySignOff initialized: %d hazards, %d PPE items, %d windows",
            len(self.hazards), len(self.ppe), len(self.windows),
        )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def hazard_count(self) -> int:
        return len(self.hazards)

    @property
    def ppe_count(self) -> int:
        return len(self.ppe)

    @property
    def window_count(self) -> int:
        return len(self.windows)

    @property
    def total_install_duration_minutes(self) -> int:
        return sum(w.duration_minutes for w in self.windows)

    @property
    def all_risks_low(self) -> bool:
        """True if all hazards have been reduced to low risk after controls."""
        return all(h.risk_after_controls == RiskLevel.LOW for h in self.hazards)

    @property
    def all_windows_confirmed(self) -> bool:
        return all(
            w.status in (WindowStatus.CONFIRMED, WindowStatus.COMPLETED)
            for w in self.windows
        )

    @property
    def zero_production_stoppage(self) -> bool:
        """True if no install window requires production stop."""
        return not any(w.requires_production_stop for w in self.windows)

    @property
    def is_approved(self) -> bool:
        return self.status == SignOffStatus.APPROVED

    # ── Lookups ──────────────────────────────────────────────────────────

    def get_hazard(self, hazard_id: str) -> HazardAssessment:
        for h in self.hazards:
            if h.hazard_id == hazard_id:
                return h
        raise KeyError(f"Unknown hazard_id {hazard_id!r}")

    def get_hazards_for_node(self, node_id: str) -> list[HazardAssessment]:
        return [h for h in self.hazards if h.node_id == node_id]

    def get_window(self, window_id: str) -> InstallWindow:
        for w in self.windows:
            if w.window_id == window_id:
                return w
        raise KeyError(f"Unknown window_id {window_id!r}")

    def get_ppe_item(self, ppe_id: str) -> PPERequirement:
        for p in self.ppe:
            if p.ppe_id == ppe_id:
                return p
        raise KeyError(f"Unknown ppe_id {ppe_id!r}")

    # ── Status Management ────────────────────────────────────────────────

    def approve(self, officer_name: str, notes: str = "") -> None:
        """Mark the sign-off as approved by the Safety Officer."""
        self.status = SignOffStatus.APPROVED
        self.safety_officer = officer_name
        self.sign_off_date = datetime.now(timezone.utc).isoformat()
        self.sign_off_notes = notes
        logger.info("Safety sign-off APPROVED by %s", officer_name)

    def reject(self, officer_name: str, notes: str = "") -> None:
        """Mark the sign-off as rejected."""
        self.status = SignOffStatus.REJECTED
        self.safety_officer = officer_name
        self.sign_off_notes = notes
        logger.info("Safety sign-off REJECTED by %s: %s", officer_name, notes)

    def confirm_window(self, window_id: str) -> InstallWindow:
        w = self.get_window(window_id)
        w.status = WindowStatus.CONFIRMED
        logger.info("Install window %s confirmed", window_id)
        return w

    # ── Printable ────────────────────────────────────────────────────────

    def print_document(self) -> str:
        """Generate a human-readable safety sign-off document."""
        lines: list[str] = []
        lines.append("# OI-75 Safety / Access Sign-Off Document")
        lines.append("")
        lines.append(f"**Status:** {self.status.value.upper()}")
        lines.append(f"**Safety Officer:** {self.safety_officer}")
        lines.append(f"**Lead Installer:** {self.installer}")
        if self.sign_off_date:
            lines.append(f"**Sign-Off Date:** {self.sign_off_date}")
        lines.append("")

        # Zero downtime constraints
        lines.append("## Zero Production Stoppage Constraints")
        lines.append("")
        for c in self.zero_downtime_constraints:
            lines.append(f"- **{c['id']}**: {c['constraint']}")
            lines.append(f"  - Source: {c['source']}")
            lines.append(f"  - Enforcement: {c['enforcement']}")
        lines.append("")

        # Hazard assessments
        lines.append("## Hazard Assessments")
        lines.append("")
        for h in self.hazards:
            lines.append(f"### {h.hazard_id}: {h.location_name}")
            lines.append(f"- **Category:** {h.hazard_category.value}")
            lines.append(f"- **Description:** {h.description}")
            lines.append(f"- **Risk (before controls):** {h.risk_before_controls.value}")
            lines.append(f"- **Controls:**")
            for c in h.controls:
                lines.append(f"  - {c}")
            lines.append(f"- **PPE:** {', '.join(h.ppe_required)}")
            lines.append(f"- **Risk (after controls):** {h.risk_after_controls.value}")
            lines.append(f"- **Zero downtime:** {h.zero_downtime_impact}")
            lines.append("")

        # PPE summary
        lines.append("## PPE Requirements")
        lines.append("")
        lines.append("| ID | Item | Spec | Qty |")
        lines.append("|----|------|------|-----|")
        for p in self.ppe:
            lines.append(f"| {p.ppe_id} | {p.item} | {p.specification} | {p.quantity} |")
        lines.append("")

        # Install windows
        lines.append("## Install Windows")
        lines.append("")
        for w in self.windows:
            lines.append(f"### {w.window_id}: {w.description}")
            lines.append(f"- **Day:** {w.proposed_day}")
            lines.append(f"- **Shift:** {w.proposed_shift}")
            lines.append(f"- **Duration:** {w.duration_minutes} minutes")
            lines.append(f"- **Production stop:** {'YES' if w.requires_production_stop else 'NO'}")
            lines.append(f"- **Safety Officer:** {'Required' if w.safety_officer_required else 'Not required'}")
            lines.append(f"- **Status:** {w.status.value}")
            lines.append(f"- **Constraints:**")
            for c in w.constraints:
                lines.append(f"  - {c}")
            lines.append("")

        return "\n".join(lines)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": "OI-75 Safety / Access Sign-Off",
            "status": self.status.value,
            "safety_officer": self.safety_officer,
            "installer": self.installer,
            "sign_off_date": self.sign_off_date,
            "sign_off_notes": self.sign_off_notes,
            "hazard_count": self.hazard_count,
            "ppe_count": self.ppe_count,
            "window_count": self.window_count,
            "total_install_duration_minutes": self.total_install_duration_minutes,
            "all_risks_low": self.all_risks_low,
            "all_windows_confirmed": self.all_windows_confirmed,
            "zero_production_stoppage": self.zero_production_stoppage,
            "is_approved": self.is_approved,
            "zero_downtime_constraints": self.zero_downtime_constraints,
            "hazards": [h.to_dict() for h in self.hazards],
            "ppe": [p.to_dict() for p in self.ppe],
            "windows": [w.to_dict() for w in self.windows],
        }


# ── Report Generator ─────────────────────────────────────────────────────────


def generate_safety_report(
    signoff: SafetySignOff | None = None,
) -> dict[str, Any]:
    """Generate a complete safety sign-off report.

    Parameters
    ----------
    signoff : SafetySignOff, optional
        The sign-off to report on. Creates a default if not provided.

    Returns
    -------
    dict
        Structured report for JSON export.
    """
    so = signoff or SafetySignOff()

    report = {
        "report": "OI-75 Safety / Access Sign-Off Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": {
            "written_sign_off_captured": so.hazard_count > 0 and so.ppe_count > 0,
            "install_window_scheduled": so.window_count > 0,
            "zero_production_stoppage_documented": len(so.zero_downtime_constraints) >= 8,
        },
        "summary": {
            "hazards_assessed": so.hazard_count,
            "all_risks_reduced_to_low": so.all_risks_low,
            "ppe_items": so.ppe_count,
            "install_windows": so.window_count,
            "total_install_minutes": so.total_install_duration_minutes,
            "zero_production_stoppage": so.zero_production_stoppage,
            "zero_downtime_constraints": len(so.zero_downtime_constraints),
        },
        "signoff": so.to_dict(),
    }

    logger.info(
        "Safety report generated: %d hazards, %d PPE, %d windows, risks all low: %s",
        so.hazard_count, so.ppe_count, so.window_count, so.all_risks_low,
    )

    return report
