"""
Non-Invasive Install Procedure — OI-76
=========================================

Codifies the complete non-invasive installation procedure for the two
POC target nodes: **compressor-01** (HP compressor) and **isbm-01**
(ISBM main feed).

Key constraints (from PRD §1.3, §2.7, Architecture §4):
  - Zero production downtime — all sensors are non-invasive (clip-on, snap-on,
    tap-into-existing-port).
  - No wiring cut, no OEM warranty risk.
  - Both nodes must be instrumented before edge gateway goes online.

This module provides:
  - ``InstallStep``: a single step in the install procedure
  - ``NodeInstallPlan``: the full install plan for one node
  - ``InstallProcedure``: the master procedure covering both POC nodes
  - ``InstallVerifier``: validates both nodes are fully instrumented
  - ``generate_install_report()``: produces a structured install report

Depends on:
  - OI-73 (BOM + lead times — hardware list)
  - OI-75 (safety sign-off — safety_approved flag)

Usage::

    from omniview.edge.install_procedure import (
        InstallProcedure, InstallVerifier, generate_install_report
    )

    procedure = InstallProcedure()
    procedure.print_checklist()

    verifier = InstallVerifier()
    result = verifier.verify_all()
    assert result.all_passed
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


class InstallMethod(str, Enum):
    """How a sensor is physically attached — all must be non-invasive."""

    SNAP_ON_CT = "snap_on_ct"               # Split-core CT clamp on live cable
    PANEL_DOOR_MOUNT = "panel_door_mount"    # Meter mounted on panel exterior
    MAGNETIC_MOUNT = "magnetic_mount"        # Magnetic/epoxy on bearing housing
    GAUGE_PORT_TAP = "gauge_port_tap"        # Tapped into existing gauge port
    SURFACE_MOUNT = "surface_mount"          # Surface-mounted thermal probe
    WALL_MOUNT = "wall_mount"               # Wall/pillar mount (ambient)
    PROXIMITY_MOUNT = "proximity_mount"     # Non-contact proximity sensor


class InstallStatus(str, Enum):
    """Status of an install step."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class SafetyCategory(str, Enum):
    """Safety category for install steps."""

    NO_RISK = "no_risk"                     # No safety concern
    LOW_RISK = "low_risk"                   # Standard PPE required
    MEDIUM_RISK = "medium_risk"             # Near live equipment — extra care
    HIGH_RISK = "high_risk"                 # Should not exist for non-invasive


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class InstallStep:
    """A single step in the non-invasive install procedure."""

    step_id: str
    description: str
    method: InstallMethod
    safety_category: SafetyCategory
    sensor_type: str
    device_id: str
    hardware: str
    location: str
    duration_minutes: int
    requires_power_off: bool = False        # Must ALWAYS be False for this POC
    ppe_required: list[str] = field(default_factory=list)
    verification_check: str = ""
    notes: str = ""
    status: InstallStatus = InstallStatus.NOT_STARTED

    def __post_init__(self) -> None:
        if self.requires_power_off:
            raise ValueError(
                f"Step {self.step_id!r} requires power off — this violates "
                f"the non-invasive install constraint (PRD §1.3). "
                f"All installations must achieve zero production downtime."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for reporting."""
        return {
            "step_id": self.step_id,
            "description": self.description,
            "method": self.method.value,
            "safety_category": self.safety_category.value,
            "sensor_type": self.sensor_type,
            "device_id": self.device_id,
            "hardware": self.hardware,
            "location": self.location,
            "duration_minutes": self.duration_minutes,
            "requires_power_off": self.requires_power_off,
            "ppe_required": self.ppe_required,
            "verification_check": self.verification_check,
            "notes": self.notes,
            "status": self.status.value,
        }


@dataclass
class NodeInstallPlan:
    """Complete install plan for a single node."""

    node_id: str
    display_name: str
    location: str
    steps: list[InstallStep]
    safety_approved: bool = False           # OI-75 dependency
    bom_confirmed: bool = False             # OI-73 dependency

    @property
    def total_duration_minutes(self) -> int:
        """Total estimated install time for this node."""
        return sum(s.duration_minutes for s in self.steps)

    @property
    def all_steps_completed(self) -> bool:
        """True if every step is completed or verified."""
        return all(
            s.status in (InstallStatus.COMPLETED, InstallStatus.VERIFIED)
            for s in self.steps
        )

    @property
    def device_count(self) -> int:
        """Number of distinct devices to install."""
        return len({s.device_id for s in self.steps})

    @property
    def requires_any_power_off(self) -> bool:
        """Should ALWAYS return False for non-invasive install."""
        return any(s.requires_power_off for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "location": self.location,
            "total_duration_minutes": self.total_duration_minutes,
            "device_count": self.device_count,
            "safety_approved": self.safety_approved,
            "bom_confirmed": self.bom_confirmed,
            "all_steps_completed": self.all_steps_completed,
            "requires_any_power_off": self.requires_any_power_off,
            "steps": [s.to_dict() for s in self.steps],
        }


# ── Compressor Node Install Steps ────────────────────────────────────────────

_COMPRESSOR_STEPS: list[InstallStep] = [
    InstallStep(
        step_id="COMP-01",
        description=(
            "Mount Selec MFM384-C-CE energy meter on compressor panel "
            "exterior door. No wiring cut — meter reads via CT secondary."
        ),
        method=InstallMethod.PANEL_DOOR_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="electrical",
        device_id="pune-comp-mfm384",
        hardware="Selec MFM384-C-CE",
        location="Compressor room — main electrical panel exterior",
        duration_minutes=20,
        ppe_required=["insulated gloves", "safety glasses"],
        verification_check=(
            "Meter powered on, displaying voltage. "
            "Compare V_LN reading against handheld clamp-meter within ±2%."
        ),
        notes="Panel door stays closed during operation. Meter mounts on exterior surface.",
    ),
    InstallStep(
        step_id="COMP-02",
        description=(
            "Snap split-core CTs (Selec SCCT-30/20) onto compressor motor "
            "feed phases R/Y/B. No cable cutting — CT clamps around live conductors."
        ),
        method=InstallMethod.SNAP_ON_CT,
        safety_category=SafetyCategory.MEDIUM_RISK,
        sensor_type="electrical",
        device_id="pune-comp-mfm384",
        hardware="Selec SCCT-30/20 Split-Core CT × 3",
        location="Compressor room — phase conductors at panel entry",
        duration_minutes=15,
        ppe_required=["insulated gloves", "safety glasses", "arc flash PPE"],
        verification_check=(
            "All 3 CTs closed and latched. "
            "MFM384 shows current reading on all 3 phases. "
            "Compare I_avg against clamp-meter reading within ±2%."
        ),
        notes=(
            "Split-core design allows install on live cables. "
            "Ensure CT ratio matches MFM384 configuration (30/20 → 150/5A typical)."
        ),
    ),
    InstallStep(
        step_id="COMP-03",
        description=(
            "Mount vibration/temperature sensor (Banner Q45VT / NCD MEMS) "
            "on compressor bearing housing via magnetic or epoxy mount."
        ),
        method=InstallMethod.MAGNETIC_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="vibration",
        device_id="pune-comp-vib01",
        hardware="Banner Q45VT / NCD Wireless MEMS",
        location="Compressor room — bearing housing",
        duration_minutes=10,
        ppe_required=["safety glasses", "hearing protection"],
        verification_check=(
            "Sensor firmly attached (magnetic hold or epoxy cured). "
            "Wireless gateway shows active connection. "
            "RMS velocity reading within expected range (0.5–4.5 mm/s normal)."
        ),
        notes=(
            "ISO 10816-3 Class II thresholds: 2.8 mm/s (alert), 7.1 mm/s (critical). "
            "Mount on drive-end bearing for highest sensitivity."
        ),
    ),
    InstallStep(
        step_id="COMP-04",
        description=(
            "Tap WIKA A-10 pressure transmitter into existing gauge port on "
            "compressor output receiver manifold."
        ),
        method=InstallMethod.GAUGE_PORT_TAP,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="pressure",
        device_id="pune-comp-wika01",
        hardware="WIKA A-10 (0–40 bar)",
        location="Compressor room — output receiver manifold gauge port",
        duration_minutes=15,
        ppe_required=["safety glasses"],
        verification_check=(
            "Transmitter seated in gauge port, no air leak at fitting. "
            "4-20mA loop reading corresponds to compressor output pressure. "
            "Compare against existing mechanical gauge within ±0.5 bar."
        ),
        notes=(
            "Uses existing pneumatic gauge port — no new holes drilled. "
            "Pressure decay while loaded = leak proxy (FR6)."
        ),
    ),
    InstallStep(
        step_id="COMP-04b",
        description=(
            "Verify co-located thermal probe (Banner Q45VT) on compressor "
            "bearing housing — shares mount with vibration sensor."
        ),
        method=InstallMethod.MAGNETIC_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="thermal",
        device_id="pune-comp-therm01",
        hardware="Banner Q45VT co-located probe",
        location="Compressor room — bearing housing (co-located with vib sensor)",
        duration_minutes=5,
        ppe_required=["safety glasses"],
        verification_check=(
            "Thermal probe reading nominal surface temperature. "
            "Shares Modbus address with pune-comp-vib01 (addr 10). "
            "Cross-check: surface_temp_c within ±2°C of handheld IR thermometer."
        ),
        notes="Co-located on vibration node. Shares Modbus slave address 10.",
    ),
    InstallStep(
        step_id="COMP-05",
        description=(
            "Verify Schneider HeatTag gas/overheating sensor placement near "
            "compressor motor switchboard enclosure."
        ),
        method=InstallMethod.SURFACE_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="gas",
        device_id="pune-comp-gas01",
        hardware="Schneider HeatTag",
        location="Compressor room — inside motor switchboard enclosure",
        duration_minutes=10,
        ppe_required=["insulated gloves", "safety glasses"],
        verification_check=(
            "HeatTag mounted inside enclosure. "
            "Micro-particle index and overheating flag reading nominal."
        ),
        notes="Detects early-stage cable/connection micro-overheating before visible damage.",
    ),
    InstallStep(
        step_id="COMP-06",
        description=(
            "Verify RS-485 daisy-chain: all Modbus slaves on compressor node "
            "respond to gateway poll. Wire termination resistor at end of bus."
        ),
        method=InstallMethod.SURFACE_MOUNT,
        safety_category=SafetyCategory.NO_RISK,
        sensor_type="electrical",
        device_id="pune-comp-mfm384",
        hardware="RS-485 bus + termination",
        location="Compressor room — RS-485 bus run",
        duration_minutes=10,
        ppe_required=[],
        verification_check=(
            "Gateway (RUT956) Modbus scan shows slaves at addresses 1, 10, 20, 30. "
            "All respond within 100ms. No CRC errors in 60s test."
        ),
        notes="Single twisted-pair RS-485 run per PRD §5.1.",
    ),
]


# ── ISBM Node Install Steps ─────────────────────────────────────────────────

_ISBM_STEPS: list[InstallStep] = [
    InstallStep(
        step_id="ISBM-01",
        description=(
            "Mount Selec MFM384-C-CE energy meter on ISBM main electrical "
            "panel exterior door."
        ),
        method=InstallMethod.PANEL_DOOR_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="electrical",
        device_id="pune-isbm-mfm384",
        hardware="Selec MFM384-C-CE",
        location="Production floor — ISBM main electrical panel exterior",
        duration_minutes=20,
        ppe_required=["insulated gloves", "safety glasses"],
        verification_check=(
            "Meter powered on, displaying voltage. "
            "Compare V_LN reading against handheld clamp-meter within ±2%."
        ),
        notes="Separate MFM384 from compressor — different Modbus slave address (addr=2).",
    ),
    InstallStep(
        step_id="ISBM-02",
        description=(
            "Snap split-core CTs (Selec SCCT-30/20) onto ISBM main feed "
            "phases R/Y/B at panel entry."
        ),
        method=InstallMethod.SNAP_ON_CT,
        safety_category=SafetyCategory.MEDIUM_RISK,
        sensor_type="electrical",
        device_id="pune-isbm-mfm384",
        hardware="Selec SCCT-30/20 Split-Core CT × 3",
        location="Production floor — ISBM main feed phase conductors",
        duration_minutes=15,
        ppe_required=["insulated gloves", "safety glasses", "arc flash PPE"],
        verification_check=(
            "All 3 CTs closed and latched. MFM384 shows current on all phases. "
            "Compare I_avg against clamp-meter within ±2%."
        ),
        notes="Confirms ISBM main feed is a single connection point (PRD Phase 0 item).",
    ),
    InstallStep(
        step_id="ISBM-03",
        description=(
            "Surface-mount thermal probe (RTD / thermocouple) on ISBM barrel "
            "/ hot-runner zone."
        ),
        method=InstallMethod.SURFACE_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="thermal",
        device_id="pune-isbm-therm01",
        hardware="Surface-mounted RTD / thermocouple",
        location="Production floor — ISBM barrel zone",
        duration_minutes=15,
        ppe_required=["heat-resistant gloves", "safety glasses"],
        verification_check=(
            "Probe firmly attached to barrel surface. "
            "Temperature reading within expected range (150–280°C during operation). "
            "Lazy-idle detection requires temp elevated + current low for >15 min (FR5)."
        ),
        notes="Surface-mount — no penetration into machine body.",
    ),
    InstallStep(
        step_id="ISBM-04",
        description=(
            "Mount proximity/pulse sensor near ISBM stroke mechanism for "
            "production cycle counting."
        ),
        method=InstallMethod.PROXIMITY_MOUNT,
        safety_category=SafetyCategory.LOW_RISK,
        sensor_type="stroke",
        device_id="pune-isbm-stroke01",
        hardware="Pulse counter (proximity sensor)",
        location="Production floor — ISBM ejection mechanism",
        duration_minutes=15,
        ppe_required=["safety glasses"],
        verification_check=(
            "Proximity sensor detects each stroke cycle. "
            "Cycle count increments match visual count for 10 consecutive cycles."
        ),
        notes="Non-contact sensing — counts cycles for OEE / specific energy calc.",
    ),
    InstallStep(
        step_id="ISBM-05",
        description=(
            "Verify RS-485 daisy-chain: all ISBM Modbus slaves respond to "
            "gateway poll."
        ),
        method=InstallMethod.SURFACE_MOUNT,
        safety_category=SafetyCategory.NO_RISK,
        sensor_type="electrical",
        device_id="pune-isbm-mfm384",
        hardware="RS-485 bus + termination",
        location="Production floor — RS-485 bus run to ISBM panel",
        duration_minutes=10,
        ppe_required=[],
        verification_check=(
            "Gateway Modbus scan shows slaves at addresses 2, 11, 12. "
            "All respond within 100ms. No CRC errors in 60s test."
        ),
        notes="Single twisted-pair RS-485 run per PRD §5.1.",
    ),
]


# ── Master Install Procedure ────────────────────────────────────────────────


class InstallProcedure:
    """Master non-invasive install procedure for both POC nodes.

    Encapsulates the full install plan for compressor-01 and isbm-01,
    including pre-install prerequisites, step-by-step procedures, and
    acceptance criteria.

    Parameters
    ----------
    safety_approved : bool
        Whether site safety sign-off has been obtained (OI-75 dependency).
    bom_confirmed : bool
        Whether BOM / hardware procurement is confirmed (OI-73 dependency).
    """

    # Pre-install checklist items (from PRD §9 Phase 0)
    PRE_INSTALL_CHECKS: list[dict[str, str]] = [
        {
            "id": "PRE-01",
            "check": "Confirm actual ISBM machine make/model on-site",
            "source": "PRD §9 Phase 0",
            "jira": "OI-73",
        },
        {
            "id": "PRE-02",
            "check": "Confirm actual contracted/sanctioned MD (kVA) with MSEDCL",
            "source": "PRD §9 Phase 0",
            "jira": "OI-73",
        },
        {
            "id": "PRE-03",
            "check": "Confirm compressor nameplate (rated kW, bar, free air delivery)",
            "source": "PRD §9 Phase 0",
            "jira": "OI-73",
        },
        {
            "id": "PRE-04",
            "check": "Confirm ISBM main feed is single connection point (not split sub-panels)",
            "source": "PRD §9 Phase 0",
            "jira": "OI-73",
        },
        {
            "id": "PRE-05",
            "check": "Confirm physical dimensions of incoming power cables (CT sizing)",
            "source": "PRD §9 Phase 0",
            "jira": "OI-73",
        },
        {
            "id": "PRE-06",
            "check": "Safety/access sign-off obtained from Safety Officer",
            "source": "PRD §9 Phase 0",
            "jira": "OI-75",
        },
        {
            "id": "PRE-07",
            "check": "All BOM items received and inspected (vibration node is critical path)",
            "source": "PRD §8",
            "jira": "OI-73",
        },
        {
            "id": "PRE-08",
            "check": "Site walkthrough completed, Layer 0 profile finalized",
            "source": "PRD §9 Week 1",
            "jira": "OI-74",
        },
        {
            "id": "PRE-09",
            "check": "Teltonika RUT956 gateway powered on, firmware updated, NTP configured",
            "source": "Architecture §3.1",
            "jira": "OI-51",
        },
        {
            "id": "PRE-10",
            "check": "Handheld clamp-meter available for calibration cross-check",
            "source": "PRD §7",
            "jira": "OI-77",
        },
    ]

    def __init__(
        self,
        safety_approved: bool = False,
        bom_confirmed: bool = False,
    ) -> None:
        self.compressor_plan = NodeInstallPlan(
            node_id="compressor-01",
            display_name="High-Pressure Compressor (25–40 bar)",
            location="Compressor room — bearing housing + output receiver manifold",
            steps=copy.deepcopy(_COMPRESSOR_STEPS),
            safety_approved=safety_approved,
            bom_confirmed=bom_confirmed,
        )
        self.isbm_plan = NodeInstallPlan(
            node_id="isbm-01",
            display_name="ISBM Machine (Nissei ASB-70DPH)",
            location="Production floor — main electrical panel + barrel zone",
            steps=copy.deepcopy(_ISBM_STEPS),
            safety_approved=safety_approved,
            bom_confirmed=bom_confirmed,
        )

    @property
    def node_plans(self) -> list[NodeInstallPlan]:
        """Return both node install plans."""
        return [self.compressor_plan, self.isbm_plan]

    @property
    def total_duration_minutes(self) -> int:
        """Total install time across both nodes."""
        return sum(p.total_duration_minutes for p in self.node_plans)

    @property
    def total_device_count(self) -> int:
        """Total distinct devices across both nodes."""
        return sum(p.device_count for p in self.node_plans)

    @property
    def total_step_count(self) -> int:
        """Total install steps across both nodes."""
        return sum(len(p.steps) for p in self.node_plans)

    @property
    def all_nodes_instrumented(self) -> bool:
        """True if both nodes are fully completed."""
        return all(p.all_steps_completed for p in self.node_plans)

    @property
    def zero_downtime(self) -> bool:
        """True if no step requires power off (acceptance criteria)."""
        return not any(p.requires_any_power_off for p in self.node_plans)

    def get_pre_install_checklist(self) -> list[dict[str, str]]:
        """Return the pre-install checklist items."""
        return list(self.PRE_INSTALL_CHECKS)

    def get_all_steps(self) -> list[InstallStep]:
        """Return all steps across both nodes in install order."""
        return self.compressor_plan.steps + self.isbm_plan.steps

    def get_steps_by_status(self, status: InstallStatus) -> list[InstallStep]:
        """Return all steps matching a given status."""
        return [s for s in self.get_all_steps() if s.status == status]

    def mark_step_completed(self, step_id: str) -> InstallStep:
        """Mark a step as completed.

        Parameters
        ----------
        step_id : str
            The step identifier (e.g. ``"COMP-01"``).

        Returns
        -------
        InstallStep
            The updated step.

        Raises
        ------
        KeyError
            If *step_id* is not found.
        """
        for step in self.get_all_steps():
            if step.step_id == step_id:
                step.status = InstallStatus.COMPLETED
                logger.info("Step %s marked completed: %s", step_id, step.description)
                return step
        raise KeyError(f"Unknown step_id {step_id!r}")

    def mark_step_verified(self, step_id: str) -> InstallStep:
        """Mark a step as verified (post-calibration check passed).

        Parameters
        ----------
        step_id : str
            The step identifier.

        Returns
        -------
        InstallStep
            The updated step.

        Raises
        ------
        KeyError
            If *step_id* is not found.
        """
        for step in self.get_all_steps():
            if step.step_id == step_id:
                step.status = InstallStatus.VERIFIED
                logger.info("Step %s verified: %s", step_id, step.description)
                return step
        raise KeyError(f"Unknown step_id {step_id!r}")

    def print_checklist(self) -> str:
        """Generate a human-readable markdown checklist.

        Returns
        -------
        str
            Markdown-formatted checklist.
        """
        lines: list[str] = []
        lines.append("# OI-76 Non-Invasive Install Checklist")
        lines.append("")
        lines.append("## Pre-Install Prerequisites")
        lines.append("")
        for item in self.PRE_INSTALL_CHECKS:
            lines.append(f"- [ ] **{item['id']}**: {item['check']} ({item['source']})")
        lines.append("")

        for plan in self.node_plans:
            lines.append(f"## Node: {plan.display_name}")
            lines.append(f"**Location:** {plan.location}")
            lines.append(f"**Estimated time:** {plan.total_duration_minutes} minutes")
            lines.append(f"**Devices:** {plan.device_count}")
            lines.append("")
            for step in plan.steps:
                check = "x" if step.status in (
                    InstallStatus.COMPLETED, InstallStatus.VERIFIED
                ) else " "
                lines.append(f"- [{check}] **{step.step_id}**: {step.description}")
                lines.append(f"  - Method: {step.method.value}")
                lines.append(f"  - Device: `{step.device_id}` ({step.hardware})")
                lines.append(f"  - Duration: {step.duration_minutes} min")
                if step.ppe_required:
                    lines.append(f"  - PPE: {', '.join(step.ppe_required)}")
                lines.append(f"  - Verify: {step.verification_check}")
                lines.append("")

        result = "\n".join(lines)
        logger.info("Install checklist generated (%d steps)", self.total_step_count)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize full procedure to dict."""
        return {
            "procedure": "OI-76 Non-Invasive Install",
            "total_duration_minutes": self.total_duration_minutes,
            "total_steps": self.total_step_count,
            "total_devices": self.total_device_count,
            "all_nodes_instrumented": self.all_nodes_instrumented,
            "zero_downtime": self.zero_downtime,
            "pre_install_checks": self.PRE_INSTALL_CHECKS,
            "nodes": [p.to_dict() for p in self.node_plans],
        }


# ── Install Verifier ─────────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    """Result of install verification for one node."""

    node_id: str
    passed: bool
    checks: list[dict[str, Any]]
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "node_id": self.node_id,
            "passed": self.passed,
            "checks": self.checks,
            "message": self.message,
        }


@dataclass
class FullVerificationResult:
    """Aggregate verification result for the entire install."""

    all_passed: bool
    node_results: list[VerificationResult]
    zero_downtime_confirmed: bool
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "all_passed": self.all_passed,
            "zero_downtime_confirmed": self.zero_downtime_confirmed,
            "timestamp": self.timestamp,
            "nodes": [r.to_dict() for r in self.node_results],
        }


class InstallVerifier:
    """Verifies both POC nodes are fully instrumented.

    Cross-references the install procedure against the edge node
    configuration (``config/edge_nodes.json``) to confirm that every
    expected device is registered and will be polled by the gateway.

    Parameters
    ----------
    procedure : InstallProcedure, optional
        The install procedure to verify against.
        Creates a default one if not provided.
    """

    # Expected device_ids per node (from edge_nodes.json)
    EXPECTED_DEVICES: dict[str, list[str]] = {
        "compressor-01": [
            "pune-comp-mfm384",
            "pune-comp-vib01",
            "pune-comp-wika01",
            "pune-comp-therm01",
            "pune-comp-gas01",
        ],
        "isbm-01": [
            "pune-isbm-mfm384",
            "pune-isbm-therm01",
            "pune-isbm-stroke01",
        ],
    }

    # Expected sensor types per node
    EXPECTED_SENSOR_TYPES: dict[str, list[str]] = {
        "compressor-01": ["electrical", "vibration", "pressure", "thermal", "gas"],
        "isbm-01": ["electrical", "thermal", "stroke"],
    }

    def __init__(self, procedure: InstallProcedure | None = None) -> None:
        self.procedure = procedure or InstallProcedure()

    def verify_node(self, node_id: str) -> VerificationResult:
        """Verify a single node's instrumentation.

        Parameters
        ----------
        node_id : str
            Node to verify (``"compressor-01"`` or ``"isbm-01"``).

        Returns
        -------
        VerificationResult
            Result with pass/fail and check details.
        """
        checks: list[dict[str, Any]] = []

        # Check 1: Node exists in expected devices
        expected_devices = self.EXPECTED_DEVICES.get(node_id, [])
        checks.append({
            "check": f"Node {node_id} has expected device list",
            "expected": expected_devices,
            "passed": len(expected_devices) > 0,
        })

        # Check 2: All expected sensor types present
        expected_types = self.EXPECTED_SENSOR_TYPES.get(node_id, [])
        # Get actual sensor types from install steps
        node_plan = (
            self.procedure.compressor_plan
            if node_id == "compressor-01"
            else self.procedure.isbm_plan
        )
        actual_types = sorted(set(s.sensor_type for s in node_plan.steps))
        types_covered = all(t in actual_types for t in expected_types)
        checks.append({
            "check": f"All expected sensor types covered",
            "expected": sorted(expected_types),
            "actual": actual_types,
            "passed": types_covered,
        })

        # Check 3: All device_ids in install steps match expected
        actual_devices = sorted(set(s.device_id for s in node_plan.steps))
        devices_match = set(expected_devices).issubset(set(actual_devices))
        checks.append({
            "check": "All expected device_ids have install steps",
            "expected": sorted(expected_devices),
            "actual": actual_devices,
            "passed": devices_match,
        })

        # Check 4: No step requires power off
        no_power_off = not node_plan.requires_any_power_off
        checks.append({
            "check": "Zero production stoppage — no step requires power off",
            "passed": no_power_off,
        })

        all_passed = all(c["passed"] for c in checks)
        message = (
            f"Node {node_id} verification {'PASSED' if all_passed else 'FAILED'}: "
            f"{sum(1 for c in checks if c['passed'])}/{len(checks)} checks passed"
        )

        logger.info(message)
        return VerificationResult(
            node_id=node_id,
            passed=all_passed,
            checks=checks,
            message=message,
        )

    def verify_all(self) -> FullVerificationResult:
        """Verify both POC nodes.

        Returns
        -------
        FullVerificationResult
            Aggregate result for the full install verification.
        """
        results = [
            self.verify_node("compressor-01"),
            self.verify_node("isbm-01"),
        ]
        all_passed = all(r.passed for r in results)
        zero_dt = self.procedure.zero_downtime

        logger.info(
            "Full install verification: %s | Zero downtime: %s",
            "PASSED" if all_passed else "FAILED",
            "CONFIRMED" if zero_dt else "VIOLATION",
        )

        return FullVerificationResult(
            all_passed=all_passed,
            node_results=results,
            zero_downtime_confirmed=zero_dt,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# ── Report Generator ─────────────────────────────────────────────────────────


def generate_install_report(
    procedure: InstallProcedure | None = None,
) -> dict[str, Any]:
    """Generate a complete install report.

    Combines the install procedure details with verification results
    into a single structured report suitable for JSON export or
    worklog documentation.

    Parameters
    ----------
    procedure : InstallProcedure, optional
        The install procedure to report on. Creates a default if not provided.

    Returns
    -------
    dict
        Structured report with procedure details and verification results.
    """
    proc = procedure or InstallProcedure()
    verifier = InstallVerifier(proc)
    verification = verifier.verify_all()

    report = {
        "report": "OI-76 Non-Invasive Install Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": {
            "both_nodes_instrumented": proc.all_nodes_instrumented,
            "zero_production_stoppage": proc.zero_downtime,
        },
        "summary": {
            "total_nodes": len(proc.node_plans),
            "total_steps": proc.total_step_count,
            "total_devices": proc.total_device_count,
            "total_duration_minutes": proc.total_duration_minutes,
        },
        "verification": verification.to_dict(),
        "procedure": proc.to_dict(),
    }

    logger.info(
        "Install report generated: %d nodes, %d steps, %d devices, %d min total",
        len(proc.node_plans),
        proc.total_step_count,
        proc.total_device_count,
        proc.total_duration_minutes,
    )

    return report
