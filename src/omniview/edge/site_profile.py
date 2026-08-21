"""
Site Walkthrough + Layer 0 Profile — OI-74
=============================================

Codifies the Week 1 Day 1–2 site walkthrough output: exact machine
locations, Layer 0 profile fields, and the location map for both POC
nodes (compressor-01 + isbm-01).

Layer 0 (Architecture §3.4) is the **Site Configuration** layer — the
site's own thresholds, tariff parameters, machine list, and physical
layout.  Nothing below this layer hardcodes site-specific facts.

This module provides:
  - ``MachineProfile``: physical machine details (nameplate, location, access)
  - ``LocationPoint``: GPS / floor-plan coordinate for a sensor mount point
  - ``LocationMap``: the full set of mount points across both nodes
  - ``Layer0Profile``: the complete site configuration profile
  - ``SiteWalkthrough``: the walkthrough checklist and findings
  - ``generate_walkthrough_report()``: structured report for export

Sources:
  - PRD §1.4 (node locations)
  - PRD §9 Phase 0 (pre-install confirmations)
  - Architecture §3.4 (Layer 0 definition)
  - ``config/edge_nodes.json`` (device / node map)

Usage::

    from omniview.edge.site_profile import (
        Layer0Profile, SiteWalkthrough, generate_walkthrough_report
    )

    profile = Layer0Profile()
    walkthrough = SiteWalkthrough(profile)
    report = generate_walkthrough_report()
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


class AccessLevel(str, Enum):
    """Physical access classification for install locations."""

    OPEN = "open"                         # No barriers, walk-up access
    PANEL_DOOR = "panel_door"             # Behind panel door (key/latch)
    ELEVATED = "elevated"                 # Requires ladder / step-up
    CONFINED = "confined"                 # Confined space — extra safety
    RESTRICTED = "restricted"             # Requires escort / sign-off


class FloorZone(str, Enum):
    """Factory floor zone classification."""

    COMPRESSOR_ROOM = "compressor_room"
    PRODUCTION_FLOOR = "production_floor"
    ELECTRICAL_ROOM = "electrical_room"
    UTILITY_AREA = "utility_area"
    CONTROL_ROOM = "control_room"
    COMMON_AREA = "common_area"


class ConfirmationStatus(str, Enum):
    """Status of a walkthrough confirmation item."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    NEEDS_REVISION = "needs_revision"
    NOT_APPLICABLE = "not_applicable"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class LocationPoint:
    """A physical mount point on the factory floor.

    Represents the exact location where a sensor or device is installed.
    """

    point_id: str
    name: str
    node_id: str
    device_id: str
    zone: FloorZone
    description: str
    access_level: AccessLevel
    floor_level: str = "Ground"
    distance_from_panel_m: float = 0.0
    cable_route_notes: str = ""
    safety_notes: str = ""
    photo_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "point_id": self.point_id,
            "name": self.name,
            "node_id": self.node_id,
            "device_id": self.device_id,
            "zone": self.zone.value,
            "description": self.description,
            "access_level": self.access_level.value,
            "floor_level": self.floor_level,
            "distance_from_panel_m": self.distance_from_panel_m,
            "cable_route_notes": self.cable_route_notes,
            "safety_notes": self.safety_notes,
        }


@dataclass
class MachineProfile:
    """Physical machine details captured during site walkthrough.

    Includes nameplate data, physical location, and access characteristics
    needed for install planning.
    """

    machine_id: str
    node_id: str
    display_name: str
    equipment_class: str
    make_model: str
    nameplate_kw: float | None
    nameplate_bar: float | None
    nameplate_voltage: str
    location_zone: FloorZone
    location_description: str
    panel_location: str
    cable_entry_description: str
    connection_type: str             # "single_feed" or "split_sub_panels"
    access_level: AccessLevel
    environmental_conditions: str
    noise_level: str
    temperature_range: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "machine_id": self.machine_id,
            "node_id": self.node_id,
            "display_name": self.display_name,
            "equipment_class": self.equipment_class,
            "make_model": self.make_model,
            "nameplate_kw": self.nameplate_kw,
            "nameplate_bar": self.nameplate_bar,
            "nameplate_voltage": self.nameplate_voltage,
            "location_zone": self.location_zone.value,
            "location_description": self.location_description,
            "panel_location": self.panel_location,
            "cable_entry_description": self.cable_entry_description,
            "connection_type": self.connection_type,
            "access_level": self.access_level.value,
            "environmental_conditions": self.environmental_conditions,
            "noise_level": self.noise_level,
            "temperature_range": self.temperature_range,
            "notes": self.notes,
        }


# ── Location Map ─────────────────────────────────────────────────────────────
# Mount points from PRD §1.4 and Architecture §3.1

_LOCATION_POINTS: list[LocationPoint] = [
    # ── Compressor Node ──────────────────────────────────────────────────
    LocationPoint(
        point_id="LOC-C01",
        name="Compressor Main Panel — Exterior Door",
        node_id="compressor-01",
        device_id="pune-comp-mfm384",
        zone=FloorZone.COMPRESSOR_ROOM,
        description=(
            "MFM384 energy meter mount on the exterior door of the "
            "compressor main electrical panel. CTs (SCCT-30/20) snap onto "
            "phase conductors at the panel cable entry point."
        ),
        access_level=AccessLevel.PANEL_DOOR,
        distance_from_panel_m=0.0,
        cable_route_notes=(
            "RS-485 bus run starts here. Twisted-pair cable routes along "
            "cable tray to bearing housing (~8m) and then to receiver "
            "manifold gauge port (~3m further)."
        ),
        safety_notes=(
            "Live 3-phase panel. Arc flash PPE required when opening door. "
            "CTs can be snapped on with panel door open — no power interruption."
        ),
    ),
    LocationPoint(
        point_id="LOC-C02",
        name="Compressor Bearing Housing — Drive End",
        node_id="compressor-01",
        device_id="pune-comp-vib01",
        zone=FloorZone.COMPRESSOR_ROOM,
        description=(
            "Vibration/temperature sensor (Banner Q45VT) mount point on the "
            "drive-end bearing housing of the HP compressor. Magnetic or "
            "epoxy attachment. Co-located thermal probe (pune-comp-therm01) "
            "shares this mount."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=8.0,
        cable_route_notes="Wireless sensor — no cable needed. Wireless gateway within 15m line-of-sight.",
        safety_notes="Hearing protection required. Rotating machinery — maintain safe distance from shaft.",
    ),
    LocationPoint(
        point_id="LOC-C03",
        name="Compressor Output Receiver — Gauge Port",
        node_id="compressor-01",
        device_id="pune-comp-wika01",
        zone=FloorZone.COMPRESSOR_ROOM,
        description=(
            "WIKA A-10 pressure transmitter taps into the existing gauge "
            "port on the compressor output receiver manifold. Uses existing "
            "port — no new holes drilled."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=11.0,
        cable_route_notes=(
            "4-20mA signal cable runs to Modbus converter (DigiRail-2A) "
            "mounted on DIN-rail near the panel (~11m cable run)."
        ),
        safety_notes="Pressurized system (25–40 bar). Verify gauge port is depressurized before fitting.",
    ),
    LocationPoint(
        point_id="LOC-C04",
        name="Compressor Motor Switchboard — Interior",
        node_id="compressor-01",
        device_id="pune-comp-gas01",
        zone=FloorZone.COMPRESSOR_ROOM,
        description=(
            "Schneider HeatTag gas/overheating sensor mounted inside the "
            "compressor motor switchboard enclosure for micro-particle and "
            "thermal rise detection."
        ),
        access_level=AccessLevel.PANEL_DOOR,
        distance_from_panel_m=1.0,
        cable_route_notes="RS-485 bus — short run from main panel.",
        safety_notes="Inside live switchboard enclosure. Insulated gloves required.",
    ),

    # ── ISBM Node ────────────────────────────────────────────────────────
    LocationPoint(
        point_id="LOC-I01",
        name="ISBM Main Electrical Panel — Exterior Door",
        node_id="isbm-01",
        device_id="pune-isbm-mfm384",
        zone=FloorZone.PRODUCTION_FLOOR,
        description=(
            "MFM384 energy meter mount on the exterior door of the ISBM "
            "main electrical panel. CTs snap onto the ISBM main feed "
            "phase conductors at panel entry."
        ),
        access_level=AccessLevel.PANEL_DOOR,
        distance_from_panel_m=0.0,
        cable_route_notes=(
            "RS-485 bus run starts here. Routes to barrel zone (~6m) and "
            "then to ejection mechanism (~4m further)."
        ),
        safety_notes=(
            "Live 3-phase panel. Arc flash PPE required when opening door. "
            "Confirm single connection point (not split sub-panels) before install."
        ),
    ),
    LocationPoint(
        point_id="LOC-I02",
        name="ISBM Barrel / Hot-Runner Zone",
        node_id="isbm-01",
        device_id="pune-isbm-therm01",
        zone=FloorZone.PRODUCTION_FLOOR,
        description=(
            "Surface-mounted thermal probe (RTD/thermocouple) on the ISBM "
            "barrel or hot-runner zone. Monitors process temperature for "
            "lazy-idle detection (FR5)."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=6.0,
        cable_route_notes="Modbus RTU cable from panel to barrel zone (~6m).",
        safety_notes=(
            "High surface temperature (150–280°C during operation). "
            "Heat-resistant gloves required. Do not touch barrel surface directly."
        ),
    ),
    LocationPoint(
        point_id="LOC-I03",
        name="ISBM Ejection / Stroke Mechanism",
        node_id="isbm-01",
        device_id="pune-isbm-stroke01",
        zone=FloorZone.PRODUCTION_FLOOR,
        description=(
            "Proximity sensor mount near the ISBM ejection/stroke mechanism "
            "for production cycle counting. Non-contact sensing."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=10.0,
        cable_route_notes="Modbus RTU cable continuation from barrel zone (~4m further).",
        safety_notes="Moving parts — maintain safe distance during operation.",
    ),

    # ── Floor / Infrastructure ───────────────────────────────────────────
    LocationPoint(
        point_id="LOC-F01",
        name="Shop Floor — Ambient Sensor Mount",
        node_id="floor",
        device_id="pune-floor-ambient01",
        zone=FloorZone.COMMON_AREA,
        description=(
            "Schneider TH110 ambient temperature/humidity sensor mounted on "
            "a wall or pillar near the production area. Establishes baseline "
            "environmental conditions."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=0.0,
        cable_route_notes="Modbus RTU cable to gateway (~15m estimated).",
        safety_notes="No specific safety concerns — wall mount at ~1.5m height.",
    ),
    LocationPoint(
        point_id="LOC-F02",
        name="Shop Floor — Jumbo Display Mount",
        node_id="floor",
        device_id="",
        zone=FloorZone.COMMON_AREA,
        description=(
            "Multispan RS-6006 jumbo LED display mounted on a wall or "
            "pillar near the main electrical panel, visible to operators "
            "on the production floor. Shows live kVA vs. contracted demand."
        ),
        access_level=AccessLevel.OPEN,
        distance_from_panel_m=5.0,
        cable_route_notes="Modbus RTU cable from gateway (~5m).",
        safety_notes="Mount at eye level (~1.6m). Ensure visibility from operator stations.",
    ),
    LocationPoint(
        point_id="LOC-F03",
        name="Control Cabinet — Edge Gateway",
        node_id="floor",
        device_id="",
        zone=FloorZone.ELECTRICAL_ROOM,
        description=(
            "Teltonika RUT956 edge gateway mounted in a control cabinet or "
            "on DIN-rail near the main electrical panel. Central hub for "
            "all Modbus polling, NTP sync, offline buffer, and MQTT bridge."
        ),
        access_level=AccessLevel.PANEL_DOOR,
        distance_from_panel_m=2.0,
        cable_route_notes=(
            "RS-485 bus runs from here to both node panels. "
            "4G antenna cable routed to exterior or window for best signal."
        ),
        safety_notes="24V DC power. Ensure adequate ventilation in cabinet.",
    ),
]


# ── Machine Profiles ─────────────────────────────────────────────────────────
# Captured during site walkthrough (PRD §9 Phase 0)

_MACHINE_PROFILES: list[MachineProfile] = [
    MachineProfile(
        machine_id="MACH-COMP-01",
        node_id="compressor-01",
        display_name="High-Pressure Compressor (25–40 bar)",
        equipment_class="rotary_screw_compressor",
        make_model="To be confirmed on-site (PRD §9 Phase 0)",
        nameplate_kw=37,
        nameplate_bar=40,
        nameplate_voltage="415V 3-phase",
        location_zone=FloorZone.COMPRESSOR_ROOM,
        location_description=(
            "Compressor room — dedicated space adjacent to the production "
            "floor. Houses the HP compressor, receiver tank, and associated "
            "pneumatic distribution manifold."
        ),
        panel_location=(
            "Main electrical panel on the wall adjacent to the compressor. "
            "Panel door exterior is accessible for MFM384 mounting."
        ),
        cable_entry_description=(
            "3-phase power cables enter from the top of the panel. "
            "Sufficient clearance for split-core CT installation around "
            "individual phase conductors."
        ),
        connection_type="single_feed",
        access_level=AccessLevel.OPEN,
        environmental_conditions=(
            "Enclosed room with mechanical ventilation. Higher ambient "
            "temperature than production floor due to compressor heat "
            "dissipation. Moderate dust levels."
        ),
        noise_level="High (>85 dB) — hearing protection required",
        temperature_range="30–45°C ambient (compressor room)",
        notes=(
            "Confirm actual make/model during walkthrough (PRD §9 Phase 0). "
            "Metaplan assumes 37 kW rated power and 40 bar rated pressure. "
            "Confirm compressor nameplate: rated kW, bar, free air delivery."
        ),
    ),
    MachineProfile(
        machine_id="MACH-ISBM-01",
        node_id="isbm-01",
        display_name="ISBM Machine (Nissei ASB-70DPH)",
        equipment_class="injection_stretch_blow_molder",
        make_model="Nissei ASB-70DPH (to be confirmed on-site)",
        nameplate_kw=None,
        nameplate_bar=None,
        nameplate_voltage="415V 3-phase",
        location_zone=FloorZone.PRODUCTION_FLOOR,
        location_description=(
            "Main production floor — the ISBM machine occupies a significant "
            "footprint. Includes injection unit, stretch-blow unit, barrel/"
            "hot-runner zone, and ejection mechanism."
        ),
        panel_location=(
            "Main electrical panel near the ISBM machine, typically on the "
            "wall or integrated into the machine's control cabinet. Panel "
            "door exterior is accessible for MFM384 mounting."
        ),
        cable_entry_description=(
            "Confirm whether ISBM main feed is a single connection point "
            "or split across sub-panels (PRD §9 Phase 0 item). "
            "Cable dimensions needed for correct CT sizing."
        ),
        connection_type="single_feed",
        access_level=AccessLevel.OPEN,
        environmental_conditions=(
            "Open production floor with ambient ventilation. High thermal "
            "radiation near barrel/hot-runner zone (150–280°C). "
            "Standard industrial dust levels."
        ),
        noise_level="Moderate (70–80 dB)",
        temperature_range="25–35°C ambient (production floor), 150–280°C barrel zone",
        notes=(
            "Confirm actual make/model during walkthrough. "
            "Metaplan assumes Nissei ASB-70DPH. "
            "Critical: confirm single feed vs. split sub-panels for CT placement."
        ),
    ),
]


# ── Layer 0 Profile ──────────────────────────────────────────────────────────


@dataclass
class TariffProfile:
    """MSEDCL tariff parameters for the site."""

    utility: str = "MSEDCL"
    tariff_category: str = "HT-I"
    contracted_demand_kva: float = 500.0
    penalty_rate_per_kva: float = 350.0
    billing_window_minutes: int = 15
    confirmed: bool = False
    notes: str = (
        "All values are metaplan defaults (PRD §8). Must confirm with "
        "site finance officer and actual MSEDCL bill before Week 1."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "utility": self.utility,
            "tariff_category": self.tariff_category,
            "contracted_demand_kva": self.contracted_demand_kva,
            "penalty_rate_per_kva": self.penalty_rate_per_kva,
            "billing_window_minutes": self.billing_window_minutes,
            "confirmed": self.confirmed,
            "notes": self.notes,
        }


@dataclass
class SiteInfo:
    """Basic site identification and physical details."""

    site_id: str = "pune-isbm"
    name: str = "ISBM-PET Bottle Manufacturing, Pune"
    address: str = "Pune, Maharashtra, India"
    timezone: str = "Asia/Kolkata"
    utility_jurisdiction: str = "MSEDCL HT-I"
    existing_digital_infra: str = "None (no PLC, no SCADA, no exportable meter)"
    internet_connectivity: str = "4G LTE (unreliable — offline buffering required)"
    operating_hours: str = "24/7 continuous production"
    shift_pattern: str = "3 shifts × 8 hours"
    safety_officer_contact: str = "To be confirmed during walkthrough"

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "address": self.address,
            "timezone": self.timezone,
            "utility_jurisdiction": self.utility_jurisdiction,
            "existing_digital_infra": self.existing_digital_infra,
            "internet_connectivity": self.internet_connectivity,
            "operating_hours": self.operating_hours,
            "shift_pattern": self.shift_pattern,
            "safety_officer_contact": self.safety_officer_contact,
        }


class Layer0Profile:
    """Complete Layer 0 site configuration profile.

    Layer 0 (Architecture §3.4) is the **Site Configuration** layer.
    Nothing below this layer hardcodes site-specific facts. This profile
    captures all site-specific parameters needed by the rest of the stack.

    Parameters
    ----------
    site : SiteInfo, optional
        Site identification details.
    tariff : TariffProfile, optional
        Tariff / billing parameters.
    machines : list[MachineProfile], optional
        Machine inventory.
    locations : list[LocationPoint], optional
        Sensor mount point locations.
    """

    def __init__(
        self,
        site: SiteInfo | None = None,
        tariff: TariffProfile | None = None,
        machines: list[MachineProfile] | None = None,
        locations: list[LocationPoint] | None = None,
    ) -> None:
        self.site = site or SiteInfo()
        self.tariff = tariff or TariffProfile()
        self.machines = machines if machines is not None else copy.deepcopy(_MACHINE_PROFILES)
        self.locations = locations if locations is not None else copy.deepcopy(_LOCATION_POINTS)

        logger.info(
            "Layer0Profile loaded: site=%s, machines=%d, locations=%d",
            self.site.site_id,
            len(self.machines),
            len(self.locations),
        )

    # ── Lookups ──────────────────────────────────────────────────────────

    @property
    def machine_count(self) -> int:
        return len(self.machines)

    @property
    def location_count(self) -> int:
        return len(self.locations)

    def get_machine(self, machine_id: str) -> MachineProfile:
        """Return a machine by ID.

        Raises KeyError if not found.
        """
        for m in self.machines:
            if m.machine_id == machine_id:
                return m
        raise KeyError(f"Unknown machine_id {machine_id!r}")

    def get_machine_by_node(self, node_id: str) -> MachineProfile | None:
        """Return the machine profile for a given node_id."""
        for m in self.machines:
            if m.node_id == node_id:
                return m
        return None

    def get_locations_for_node(self, node_id: str) -> list[LocationPoint]:
        """Return all location points for a given node."""
        return [loc for loc in self.locations if loc.node_id == node_id]

    def get_location(self, point_id: str) -> LocationPoint:
        """Return a location point by ID.

        Raises KeyError if not found.
        """
        for loc in self.locations:
            if loc.point_id == point_id:
                return loc
        raise KeyError(f"Unknown point_id {point_id!r}")

    def get_locations_by_zone(self, zone: FloorZone) -> list[LocationPoint]:
        """Return all location points in a given floor zone."""
        return [loc for loc in self.locations if loc.zone == zone]

    # ── Printable ────────────────────────────────────────────────────────

    def print_profile(self) -> str:
        """Generate a human-readable Layer 0 profile document.

        Returns
        -------
        str
            Markdown-formatted profile.
        """
        lines: list[str] = []
        lines.append("# Layer 0 — Site Configuration Profile")
        lines.append("")

        # Site info
        lines.append("## Site Information")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        for k, v in self.site.to_dict().items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")

        # Tariff
        lines.append("## Tariff / Billing Parameters")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        for k, v in self.tariff.to_dict().items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")

        # Machines
        lines.append("## Machine Inventory")
        lines.append("")
        for m in self.machines:
            lines.append(f"### {m.display_name}")
            lines.append(f"- **Node:** `{m.node_id}`")
            lines.append(f"- **Class:** {m.equipment_class}")
            lines.append(f"- **Make/Model:** {m.make_model}")
            if m.nameplate_kw is not None:
                lines.append(f"- **Rated Power:** {m.nameplate_kw} kW")
            if m.nameplate_bar is not None:
                lines.append(f"- **Rated Pressure:** {m.nameplate_bar} bar")
            lines.append(f"- **Voltage:** {m.nameplate_voltage}")
            lines.append(f"- **Zone:** {m.location_zone.value}")
            lines.append(f"- **Connection:** {m.connection_type}")
            lines.append(f"- **Environment:** {m.environmental_conditions}")
            lines.append(f"- **Noise:** {m.noise_level}")
            lines.append(f"- **Temperature:** {m.temperature_range}")
            if m.notes:
                lines.append(f"- **Notes:** {m.notes}")
            lines.append("")

        # Location map
        lines.append("## Location Map")
        lines.append("")
        lines.append(
            "| ID | Name | Node | Zone | Access | Distance to Panel |"
        )
        lines.append(
            "|----|------|------|------|--------|-------------------|"
        )
        for loc in self.locations:
            lines.append(
                f"| {loc.point_id} | {loc.name} | {loc.node_id} | "
                f"{loc.zone.value} | {loc.access_level.value} | "
                f"{loc.distance_from_panel_m}m |"
            )
        lines.append("")

        result = "\n".join(lines)
        logger.info("Layer 0 profile generated")
        return result

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full profile to dict."""
        return {
            "layer": "Layer 0 — Site Configuration",
            "site": self.site.to_dict(),
            "tariff": self.tariff.to_dict(),
            "machines": [m.to_dict() for m in self.machines],
            "locations": [loc.to_dict() for loc in self.locations],
            "machine_count": self.machine_count,
            "location_count": self.location_count,
        }


# ── Site Walkthrough ─────────────────────────────────────────────────────────


@dataclass
class WalkthroughItem:
    """A single walkthrough checklist item."""

    item_id: str
    check: str
    source: str
    node: str
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    finding: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "check": self.check,
            "source": self.source,
            "node": self.node,
            "status": self.status.value,
            "finding": self.finding,
        }


_WALKTHROUGH_ITEMS: list[WalkthroughItem] = [
    # ── Compressor confirmations ─────────────────────────────────────────
    WalkthroughItem(
        item_id="WT-01",
        check="Confirm compressor make/model (nameplate reading)",
        source="PRD §9 Phase 0",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-02",
        check="Confirm compressor rated kW, bar, free air delivery",
        source="PRD §9 Phase 0",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-03",
        check="Confirm compressor panel location and exterior door access",
        source="PRD §1.4",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-04",
        check="Confirm cable dimensions at panel entry for CT sizing",
        source="PRD §9 Phase 0",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-05",
        check="Confirm bearing housing mount point for vibration sensor",
        source="PRD §1.4",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-06",
        check="Confirm existing gauge port on receiver manifold for pressure tap",
        source="PRD §1.4",
        node="compressor-01",
    ),
    WalkthroughItem(
        item_id="WT-07",
        check="Confirm RS-485 cable route from panel to bearing housing (~8m)",
        source="Architecture §5.1",
        node="compressor-01",
    ),

    # ── ISBM confirmations ───────────────────────────────────────────────
    WalkthroughItem(
        item_id="WT-08",
        check="Confirm ISBM machine make/model (nameplate reading)",
        source="PRD §9 Phase 0",
        node="isbm-01",
    ),
    WalkthroughItem(
        item_id="WT-09",
        check="Confirm ISBM main feed is single connection point (not split sub-panels)",
        source="PRD §9 Phase 0",
        node="isbm-01",
    ),
    WalkthroughItem(
        item_id="WT-10",
        check="Confirm cable dimensions at ISBM panel entry for CT sizing",
        source="PRD §9 Phase 0",
        node="isbm-01",
    ),
    WalkthroughItem(
        item_id="WT-11",
        check="Confirm barrel/hot-runner zone thermal probe mount point",
        source="PRD §1.4",
        node="isbm-01",
    ),
    WalkthroughItem(
        item_id="WT-12",
        check="Confirm ejection mechanism proximity sensor mount point",
        source="PRD §1.4",
        node="isbm-01",
    ),
    WalkthroughItem(
        item_id="WT-13",
        check="Confirm RS-485 cable route from panel to barrel and ejection (~10m)",
        source="Architecture §5.1",
        node="isbm-01",
    ),

    # ── Site-wide confirmations ──────────────────────────────────────────
    WalkthroughItem(
        item_id="WT-14",
        check="Confirm contracted/sanctioned maximum demand (kVA) with MSEDCL",
        source="PRD §9 Phase 0",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-15",
        check="Obtain last 12 months MSEDCL bills (max demand + penalty line items)",
        source="PRD §9 Phase 0",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-16",
        check="Confirm gateway (RUT956) mounting location and 4G signal strength",
        source="Architecture §3.1",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-17",
        check="Confirm jumbo display mount location (visible to operators)",
        source="PRD §1.4",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-18",
        check="Confirm ambient sensor mount location (wall/pillar)",
        source="PRD §1.4",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-19",
        check="Confirm safety sign-off and installation window with Safety Officer",
        source="PRD §9 Phase 0",
        node="all",
    ),
    WalkthroughItem(
        item_id="WT-20",
        check="Confirm 24V DC power availability for gateway and sensors",
        source="Architecture §3.1",
        node="all",
    ),
]


class SiteWalkthrough:
    """Site walkthrough checklist and findings manager.

    Parameters
    ----------
    profile : Layer0Profile, optional
        The Layer 0 profile to validate against.
    """

    def __init__(self, profile: Layer0Profile | None = None) -> None:
        self.profile = profile or Layer0Profile()
        self.items = copy.deepcopy(_WALKTHROUGH_ITEMS)
        logger.info("SiteWalkthrough initialized: %d items", len(self.items))

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def confirmed_count(self) -> int:
        return sum(
            1 for i in self.items if i.status == ConfirmationStatus.CONFIRMED
        )

    @property
    def pending_count(self) -> int:
        return sum(
            1 for i in self.items if i.status == ConfirmationStatus.PENDING
        )

    @property
    def all_confirmed(self) -> bool:
        return all(
            i.status in (ConfirmationStatus.CONFIRMED, ConfirmationStatus.NOT_APPLICABLE)
            for i in self.items
        )

    def get_item(self, item_id: str) -> WalkthroughItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(f"Unknown walkthrough item {item_id!r}")

    def get_items_by_node(self, node: str) -> list[WalkthroughItem]:
        return [i for i in self.items if i.node == node or i.node == "all"]

    def get_items_by_status(self, status: ConfirmationStatus) -> list[WalkthroughItem]:
        return [i for i in self.items if i.status == status]

    def confirm_item(self, item_id: str, finding: str = "") -> WalkthroughItem:
        item = self.get_item(item_id)
        item.status = ConfirmationStatus.CONFIRMED
        item.finding = finding
        logger.info("Walkthrough item %s confirmed: %s", item_id, item.check)
        return item

    def flag_revision(self, item_id: str, finding: str = "") -> WalkthroughItem:
        item = self.get_item(item_id)
        item.status = ConfirmationStatus.NEEDS_REVISION
        item.finding = finding
        logger.info("Walkthrough item %s needs revision: %s", item_id, finding)
        return item

    def print_checklist(self) -> str:
        lines: list[str] = []
        lines.append("# OI-74 Site Walkthrough Checklist")
        lines.append("")
        lines.append(f"**Total items:** {self.item_count}")
        lines.append(f"**Confirmed:** {self.confirmed_count}")
        lines.append(f"**Pending:** {self.pending_count}")
        lines.append("")

        current_node = ""
        for item in self.items:
            if item.node != current_node:
                current_node = item.node
                label = {
                    "compressor-01": "Compressor Node",
                    "isbm-01": "ISBM Node",
                    "all": "Site-Wide",
                }.get(current_node, current_node)
                lines.append(f"## {label}")
                lines.append("")

            status_mark = {
                ConfirmationStatus.CONFIRMED: "x",
                ConfirmationStatus.PENDING: " ",
                ConfirmationStatus.NEEDS_REVISION: "!",
                ConfirmationStatus.NOT_APPLICABLE: "-",
            }.get(item.status, " ")
            lines.append(f"- [{status_mark}] **{item.item_id}**: {item.check}")
            if item.finding:
                lines.append(f"  - Finding: {item.finding}")

        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "walkthrough": "OI-74 Site Walkthrough",
            "item_count": self.item_count,
            "confirmed_count": self.confirmed_count,
            "pending_count": self.pending_count,
            "all_confirmed": self.all_confirmed,
            "items": [i.to_dict() for i in self.items],
        }


# ── Report Generator ─────────────────────────────────────────────────────────


def generate_walkthrough_report(
    profile: Layer0Profile | None = None,
) -> dict[str, Any]:
    """Generate a complete walkthrough + Layer 0 profile report.

    Parameters
    ----------
    profile : Layer0Profile, optional
        The profile to report on. Creates a default if not provided.

    Returns
    -------
    dict
        Structured report suitable for JSON export.
    """
    prof = profile or Layer0Profile()
    walkthrough = SiteWalkthrough(prof)

    report = {
        "report": "OI-74 Site Walkthrough + Layer 0 Profile",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": {
            "location_map_for_both_nodes": (
                len(prof.get_locations_for_node("compressor-01")) > 0
                and len(prof.get_locations_for_node("isbm-01")) > 0
            ),
            "layer_0_profile_draft_complete": (
                prof.machine_count >= 2
                and prof.location_count >= 8
            ),
        },
        "summary": {
            "machines": prof.machine_count,
            "locations": prof.location_count,
            "walkthrough_items": walkthrough.item_count,
            "zones_covered": len(set(loc.zone.value for loc in prof.locations)),
        },
        "layer0_profile": prof.to_dict(),
        "walkthrough": walkthrough.to_dict(),
    }

    logger.info(
        "Walkthrough report generated: %d machines, %d locations, %d checklist items",
        prof.machine_count, prof.location_count, walkthrough.item_count,
    )

    return report
