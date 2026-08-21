"""
Bill of Materials (BOM) + Procurement Lead Times — OI-73
==========================================================

Codifies the complete hardware BOM for the 2-node POC:
  - **compressor-01**: HP Compressor (25–40 bar)
  - **isbm-01**: ISBM Machine (Nissei ASB-70DPH)
  - **floor**: Ambient monitoring
  - **infrastructure**: Gateway, jumbo display, cabling

Sources:
  - PRD §3 Sensor List (costs, models, availability)
  - PRD §8 Risks (vibration node critical path)
  - ``config/edge_nodes.json`` (device_ids, Modbus addresses)
  - ``Docs/sesnor-fetures.md`` (datasheets, parameters)

Key constraints:
  - Vibration node (Banner Q45VT / NCD MEMS) is the **critical-path** item
    with 1–2 week lead time (PRD §8).
  - Total CapEx target: ₹95,000–₹1,20,000 (PRD §3).
  - All items must be non-invasive install compatible.

This module provides:
  - ``BOMItem``: a single BOM line item
  - ``BOMSheet``: the full BOM with cost/lead-time analysis
  - ``generate_bom_report()``: structured report for export
  - ``get_critical_path_items()``: items that gate the install timeline

Usage::

    from omniview.edge.bom import BOMSheet, generate_bom_report

    bom = BOMSheet()
    bom.print_sheet()
    critical = bom.get_critical_path_items()
    report = generate_bom_report()
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


class Availability(str, Enum):
    """Procurement availability classification."""

    VERY_HIGH = "very_high"       # In stock, ships in 1–3 days
    HIGH = "high"                 # Standard stock, ships in 3–7 days
    MEDIUM = "medium"             # 1–2 week lead time
    LOW = "low"                   # 2–4 week lead time
    CRITICAL = "critical"         # 4+ weeks, may delay project


class BOMCategory(str, Enum):
    """BOM item category."""

    SENSOR = "sensor"
    METER = "meter"
    TRANSDUCER = "transducer"
    GATEWAY = "gateway"
    DISPLAY = "display"
    CABLING = "cabling"
    MOUNTING = "mounting"
    POWER = "power"
    ANCILLARY = "ancillary"


class ProcurementStatus(str, Enum):
    """Procurement tracking status."""

    NOT_ORDERED = "not_ordered"
    ORDERED = "ordered"
    SHIPPED = "shipped"
    RECEIVED = "received"
    INSPECTED = "inspected"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class BOMItem:
    """A single line item in the Bill of Materials.

    Parameters
    ----------
    item_id : str
        Unique BOM line identifier (e.g. ``"BOM-001"``).
    name : str
        Human-readable item name.
    make_model : str
        Manufacturer make and model.
    category : BOMCategory
        Item category.
    function : str
        What the item does in the system.
    node : str
        Which node(s) this item serves.
    device_id : str
        Corresponding device_id from edge_nodes.json (empty for ancillary).
    quantity : int
        Number of units required.
    unit_cost_inr_low : float
        Low estimate of unit cost in INR.
    unit_cost_inr_high : float
        High estimate of unit cost in INR.
    lead_time_days_min : int
        Minimum procurement lead time in days.
    lead_time_days_max : int
        Maximum procurement lead time in days.
    availability : Availability
        Availability classification.
    vendor_location : str
        Vendor location / source.
    is_critical_path : bool
        Whether this item gates the install timeline.
    install_method : str
        How this item is physically installed (non-invasive).
    notes : str
        Additional notes, references to PRD sections, etc.
    status : ProcurementStatus
        Current procurement status.
    """

    item_id: str
    name: str
    make_model: str
    category: BOMCategory
    function: str
    node: str
    device_id: str
    quantity: int
    unit_cost_inr_low: float
    unit_cost_inr_high: float
    lead_time_days_min: int
    lead_time_days_max: int
    availability: Availability
    vendor_location: str
    is_critical_path: bool = False
    install_method: str = ""
    notes: str = ""
    status: ProcurementStatus = ProcurementStatus.NOT_ORDERED

    @property
    def total_cost_low(self) -> float:
        """Low estimate of total cost (unit_cost × quantity)."""
        return self.unit_cost_inr_low * self.quantity

    @property
    def total_cost_high(self) -> float:
        """High estimate of total cost (unit_cost × quantity)."""
        return self.unit_cost_inr_high * self.quantity

    @property
    def lead_time_display(self) -> str:
        """Human-readable lead time string."""
        if self.lead_time_days_min == self.lead_time_days_max:
            return f"{self.lead_time_days_min} days"
        return f"{self.lead_time_days_min}–{self.lead_time_days_max} days"

    @property
    def cost_display(self) -> str:
        """Human-readable cost range string."""
        if self.unit_cost_inr_low == self.unit_cost_inr_high:
            return f"₹{self.unit_cost_inr_low:,.0f}"
        return f"₹{self.unit_cost_inr_low:,.0f}–₹{self.unit_cost_inr_high:,.0f}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for reporting."""
        return {
            "item_id": self.item_id,
            "name": self.name,
            "make_model": self.make_model,
            "category": self.category.value,
            "function": self.function,
            "node": self.node,
            "device_id": self.device_id,
            "quantity": self.quantity,
            "unit_cost_inr_low": self.unit_cost_inr_low,
            "unit_cost_inr_high": self.unit_cost_inr_high,
            "total_cost_low": self.total_cost_low,
            "total_cost_high": self.total_cost_high,
            "lead_time_days_min": self.lead_time_days_min,
            "lead_time_days_max": self.lead_time_days_max,
            "lead_time_display": self.lead_time_display,
            "availability": self.availability.value,
            "vendor_location": self.vendor_location,
            "is_critical_path": self.is_critical_path,
            "install_method": self.install_method,
            "notes": self.notes,
            "status": self.status.value,
        }


# ── BOM Items ────────────────────────────────────────────────────────────────
# Source: PRD §3 Sensor List + Docs/sesnor-fetures.md + config/edge_nodes.json

_BOM_ITEMS: list[BOMItem] = [
    # ── Primary Sensors ──────────────────────────────────────────────────
    BOMItem(
        item_id="BOM-001",
        name="Digital Energy Meter (Compressor)",
        make_model="Selec MFM384-C-CE",
        category=BOMCategory.METER,
        function="3-phase kVA/kW/PF/THD measurement, Class 0.5S accuracy",
        node="compressor-01",
        device_id="pune-comp-mfm384",
        quantity=1,
        unit_cost_inr_low=4000,
        unit_cost_inr_high=6000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Selec Controls — Navi Mumbai / pan-India distributors",
        install_method="Panel door mount — exterior surface, no wiring cut",
        notes="RS485 Modbus RTU. Modbus slave address: 1. PRD §3.",
    ),
    BOMItem(
        item_id="BOM-002",
        name="Digital Energy Meter (ISBM)",
        make_model="Selec MFM384-C-CE",
        category=BOMCategory.METER,
        function="3-phase kVA/kW/PF/THD measurement, Class 0.5S accuracy",
        node="isbm-01",
        device_id="pune-isbm-mfm384",
        quantity=1,
        unit_cost_inr_low=4000,
        unit_cost_inr_high=6000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Selec Controls — Navi Mumbai / pan-India distributors",
        install_method="Panel door mount — exterior surface, no wiring cut",
        notes="RS485 Modbus RTU. Modbus slave address: 2. PRD §3.",
    ),
    BOMItem(
        item_id="BOM-003",
        name="Split-Core Current Transformers (Compressor)",
        make_model="Selec SCCT-30/20",
        category=BOMCategory.TRANSDUCER,
        function="Non-invasive current sensing on live 3-phase conductors",
        node="compressor-01",
        device_id="pune-comp-mfm384",
        quantity=3,
        unit_cost_inr_low=1500,
        unit_cost_inr_high=2000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Selec Controls — Navi Mumbai / pan-India distributors",
        install_method="Snap-on CT clamp around live cable — no cable cutting",
        notes=(
            "Split-core design allows install on energized conductors. "
            "CT ratio must match MFM384 configuration. 3 units for R/Y/B phases."
        ),
    ),
    BOMItem(
        item_id="BOM-004",
        name="Split-Core Current Transformers (ISBM)",
        make_model="Selec SCCT-30/20",
        category=BOMCategory.TRANSDUCER,
        function="Non-invasive current sensing on live 3-phase conductors",
        node="isbm-01",
        device_id="pune-isbm-mfm384",
        quantity=3,
        unit_cost_inr_low=1500,
        unit_cost_inr_high=2000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Selec Controls — Navi Mumbai / pan-India distributors",
        install_method="Snap-on CT clamp around live cable — no cable cutting",
        notes="3 units for R/Y/B phases on ISBM main feed.",
    ),
    BOMItem(
        item_id="BOM-005",
        name="Vibration & Temperature Node",
        make_model="Banner Q45VT / NCD Wireless MEMS",
        category=BOMCategory.SENSOR,
        function=(
            "ISO 10816-3 RMS vibration velocity (mm/s), "
            "triaxial acceleration (g), co-located surface temperature (°C)"
        ),
        node="compressor-01",
        device_id="pune-comp-vib01",
        quantity=1,
        unit_cost_inr_low=25000,
        unit_cost_inr_high=35000,
        lead_time_days_min=7,
        lead_time_days_max=14,
        availability=Availability.MEDIUM,
        vendor_location="Banner Engineering — import via authorized distributor",
        is_critical_path=True,
        install_method="Magnetic/epoxy mount on compressor bearing housing",
        notes=(
            "⚠ CRITICAL PATH ITEM — 1–2 week lead time (PRD §8). "
            "Must be ordered immediately to avoid compressing baseline window. "
            "ISO 10816-3 Class II thresholds: 2.8 mm/s (alert), 7.1 mm/s (critical). "
            "Wireless Modbus, slave address: 10. "
            "Datasheet: Banner QM42VT/Q45VT (info.bannerengineering.com)."
        ),
    ),
    BOMItem(
        item_id="BOM-006",
        name="Pressure Transmitter",
        make_model="WIKA A-10 (0–40 bar, 4-20mA)",
        category=BOMCategory.TRANSDUCER,
        function="Pneumatic line pressure + decay rate for leak proxy (FR6)",
        node="compressor-01",
        device_id="pune-comp-wika01",
        quantity=1,
        unit_cost_inr_low=13000,
        unit_cost_inr_high=17000,
        lead_time_days_min=2,
        lead_time_days_max=5,
        availability=Availability.HIGH,
        vendor_location="WIKA India — Pune local manufacturing",
        install_method="Tap into existing gauge port on compressor output receiver",
        notes=(
            "Uses existing pneumatic gauge port — no new holes drilled. "
            "4-20mA loop output → Modbus converter. Modbus slave address: 20. "
            "WIKA has Pune manufacturing — fast local procurement."
        ),
    ),
    BOMItem(
        item_id="BOM-007",
        name="Gas / Particle Overheating Sensor",
        make_model="Schneider Electric PowerLogic HeatTag",
        category=BOMCategory.SENSOR,
        function="Early-stage cable/connection micro-overheating detection",
        node="compressor-01",
        device_id="pune-comp-gas01",
        quantity=1,
        unit_cost_inr_low=8000,
        unit_cost_inr_high=12000,
        lead_time_days_min=3,
        lead_time_days_max=7,
        availability=Availability.HIGH,
        vendor_location="Schneider Electric — pan-India distributors",
        install_method="Surface mount inside switchboard enclosure",
        notes=(
            "Micro-particle index + overheating flag. Modbus RTU, slave address: 30. "
            "Detects insulation degradation before visible damage."
        ),
    ),
    BOMItem(
        item_id="BOM-008",
        name="Surface Thermal Probe (ISBM Barrel)",
        make_model="RTD / PT100 thermocouple",
        category=BOMCategory.SENSOR,
        function="Barrel/hot-runner zone temperature for lazy-idle detection (FR5)",
        node="isbm-01",
        device_id="pune-isbm-therm01",
        quantity=1,
        unit_cost_inr_low=2000,
        unit_cost_inr_high=4000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Local industrial instrumentation supplier — Pune",
        install_method="Surface-mounted on barrel — no penetration into machine body",
        notes=(
            "Modbus RTU, slave address: 11. "
            "Lazy-idle: temp elevated + current low for >15 min = LAZY_IDLE_EVENT."
        ),
    ),
    BOMItem(
        item_id="BOM-009",
        name="Co-located Thermal Probe (Compressor)",
        make_model="Banner Q45VT co-located probe",
        category=BOMCategory.SENSOR,
        function="Compressor bearing surface temperature (co-located with vibration)",
        node="compressor-01",
        device_id="pune-comp-therm01",
        quantity=1,
        unit_cost_inr_low=0,
        unit_cost_inr_high=0,
        lead_time_days_min=0,
        lead_time_days_max=0,
        availability=Availability.VERY_HIGH,
        vendor_location="Included with BOM-005 (Banner Q45VT)",
        install_method="Co-located on vibration sensor mount — no separate install",
        notes=(
            "Shares Modbus address with pune-comp-vib01 (addr 10). "
            "No additional cost — thermal channel is built into the Q45VT node."
        ),
    ),
    BOMItem(
        item_id="BOM-010",
        name="Production Stroke Counter",
        make_model="Proximity sensor (pulse counter)",
        category=BOMCategory.SENSOR,
        function="Production cycle counting for OEE / specific energy calc",
        node="isbm-01",
        device_id="pune-isbm-stroke01",
        quantity=1,
        unit_cost_inr_low=1500,
        unit_cost_inr_high=3000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Local industrial sensor supplier — Pune",
        install_method="Non-contact proximity mount near ejection mechanism",
        notes="Modbus RTU, slave address: 12. Polled at 15s (electrical cadence).",
    ),
    BOMItem(
        item_id="BOM-011",
        name="Ambient Temperature & Humidity Sensor",
        make_model="Schneider TH110 / Easergy CL110",
        category=BOMCategory.SENSOR,
        function="Shop floor ambient baseline for cooling load correlation",
        node="floor",
        device_id="pune-floor-ambient01",
        quantity=1,
        unit_cost_inr_low=3000,
        unit_cost_inr_high=5000,
        lead_time_days_min=2,
        lead_time_days_max=5,
        availability=Availability.HIGH,
        vendor_location="Schneider Electric — pan-India distributors",
        install_method="Wall/pillar mount on shop floor",
        notes="Modbus RTU, slave address: 40. Correlated with compressor/ISBM on/off.",
    ),

    # ── Infrastructure ───────────────────────────────────────────────────
    BOMItem(
        item_id="BOM-012",
        name="Edge Gateway / Central Unit",
        make_model="Teltonika RUT956",
        category=BOMCategory.GATEWAY,
        function=(
            "Modbus master polling, NTP timestamp, offline buffer, "
            "MQTT bridge, dual-SIM 4G LTE failover"
        ),
        node="all",
        device_id="",
        quantity=1,
        unit_cost_inr_low=22000,
        unit_cost_inr_high=29000,
        lead_time_days_min=3,
        lead_time_days_max=7,
        availability=Availability.HIGH,
        vendor_location="Teltonika Networks — import via authorized distributor (EU)",
        install_method="DIN-rail or shelf mount in control cabinet",
        notes=(
            "Brain of the deployment. RS232/RS485 + 4G LTE Cat 4. "
            "RutOS firmware. Single point of failure for POC (acceptable per PRD §8). "
            "Handles offline buffering (FR7) and NTP sync."
        ),
    ),
    BOMItem(
        item_id="BOM-013",
        name="Jumbo Floor Display",
        make_model="Multispan RS-6006",
        category=BOMCategory.DISPLAY,
        function="Operator-facing live kVA / active warnings display",
        node="floor",
        device_id="",
        quantity=1,
        unit_cost_inr_low=15000,
        unit_cost_inr_high=22000,
        lead_time_days_min=2,
        lead_time_days_max=5,
        availability=Availability.HIGH,
        vendor_location="Multispan India — Thane / pan-India distributors",
        install_method="Wall/pillar mount on factory floor, visible to operators",
        notes=(
            "4-inch 6-digit LED. Modbus input. "
            "Shows live kVA vs. contracted demand + active warning indicators. "
            "Datasheet: multispanindia.com/product-detail.php/jumbo-display."
        ),
    ),

    # ── Cabling & Ancillary ──────────────────────────────────────────────
    BOMItem(
        item_id="BOM-014",
        name="RS-485 Twisted Pair Cable",
        make_model="Belden 9841 or equivalent (shielded 120Ω)",
        category=BOMCategory.CABLING,
        function="Modbus RTU bus — daisy-chain all slaves per node to gateway",
        node="all",
        device_id="",
        quantity=2,
        unit_cost_inr_low=500,
        unit_cost_inr_high=1000,
        lead_time_days_min=1,
        lead_time_days_max=2,
        availability=Availability.VERY_HIGH,
        vendor_location="Local electrical supplier — Pune",
        install_method="Surface-run cable tray or conduit",
        notes="2 runs: one for compressor node, one for ISBM node. ~25m each estimated.",
    ),
    BOMItem(
        item_id="BOM-015",
        name="RS-485 Bus Termination Resistors",
        make_model="120Ω ¼W resistor",
        category=BOMCategory.ANCILLARY,
        function="Proper RS-485 bus termination to prevent signal reflections",
        node="all",
        device_id="",
        quantity=4,
        unit_cost_inr_low=5,
        unit_cost_inr_high=10,
        lead_time_days_min=1,
        lead_time_days_max=1,
        availability=Availability.VERY_HIGH,
        vendor_location="Local electronics supplier",
        install_method="Soldered at each end of RS-485 bus run",
        notes="2 per bus run (beginning + end). PRD §5.1.",
    ),
    BOMItem(
        item_id="BOM-016",
        name="4-20mA to Modbus RTU Converter",
        make_model="Novus DigiRail-2A or equivalent",
        category=BOMCategory.ANCILLARY,
        function="Converts WIKA A-10 analog output to Modbus RTU digital",
        node="compressor-01",
        device_id="pune-comp-wika01",
        quantity=1,
        unit_cost_inr_low=3000,
        unit_cost_inr_high=5000,
        lead_time_days_min=2,
        lead_time_days_max=5,
        availability=Availability.HIGH,
        vendor_location="Novus Automation / local distributor",
        install_method="DIN-rail mount adjacent to pressure transmitter",
        notes="Bridges WIKA A-10 4-20mA loop to RS-485 bus.",
    ),
    BOMItem(
        item_id="BOM-017",
        name="DIN-Rail Power Supply (24V DC)",
        make_model="Mean Well HDR-30-24 or equivalent",
        category=BOMCategory.POWER,
        function="Power supply for gateway, sensors, and Modbus converters",
        node="all",
        device_id="",
        quantity=2,
        unit_cost_inr_low=1200,
        unit_cost_inr_high=2000,
        lead_time_days_min=1,
        lead_time_days_max=3,
        availability=Availability.VERY_HIGH,
        vendor_location="Mean Well — pan-India distributors",
        install_method="DIN-rail mount in control cabinet",
        notes="One per node cluster. 24V DC for gateway + sensor accessories.",
    ),
    BOMItem(
        item_id="BOM-018",
        name="Mounting Hardware Kit",
        make_model="Assorted brackets, DIN rail, conduit fittings",
        category=BOMCategory.MOUNTING,
        function="Physical mounting for all sensors, gateway, and display",
        node="all",
        device_id="",
        quantity=1,
        unit_cost_inr_low=1500,
        unit_cost_inr_high=3000,
        lead_time_days_min=1,
        lead_time_days_max=2,
        availability=Availability.VERY_HIGH,
        vendor_location="Local hardware supplier — Pune",
        install_method="Various: DIN-rail, wall anchors, cable ties, panel screws",
        notes="Includes magnetic mounts for vibration sensor, epoxy as backup.",
    ),
    BOMItem(
        item_id="BOM-019",
        name="4G LTE SIM Cards (Dual-SIM)",
        make_model="Jio / Airtel industrial M2M SIM",
        category=BOMCategory.ANCILLARY,
        function="Cellular connectivity for edge gateway — dual-SIM failover",
        node="all",
        device_id="",
        quantity=2,
        unit_cost_inr_low=100,
        unit_cost_inr_high=200,
        lead_time_days_min=1,
        lead_time_days_max=2,
        availability=Availability.VERY_HIGH,
        vendor_location="Jio / Airtel — local outlet",
        install_method="Insert into Teltonika RUT956 SIM slots",
        notes=(
            "Dual-SIM for failover. Monthly data plan ~₹200–500/month. "
            "4G signal inside metal building is a known risk (PRD §8) — "
            "mitigated by offline buffering."
        ),
    ),
]


# ── BOM Sheet ────────────────────────────────────────────────────────────────


class BOMSheet:
    """Complete Bill of Materials for the 2-node POC.

    Provides cost analysis, lead-time tracking, critical-path flagging,
    and procurement status management.

    Parameters
    ----------
    items : list[BOMItem], optional
        Custom item list. Defaults to the standard POC BOM.
    """

    def __init__(self, items: list[BOMItem] | None = None) -> None:
        self.items = items if items is not None else copy.deepcopy(_BOM_ITEMS)
        logger.info(
            "BOMSheet loaded: %d items, ₹%,.0f–₹%,.0f total",
            len(self.items),
            self.total_cost_low,
            self.total_cost_high,
        )

    # ── Cost Analysis ────────────────────────────────────────────────────

    @property
    def total_cost_low(self) -> float:
        """Low estimate of total BOM cost (INR)."""
        return sum(item.total_cost_low for item in self.items)

    @property
    def total_cost_high(self) -> float:
        """High estimate of total BOM cost (INR)."""
        return sum(item.total_cost_high for item in self.items)

    @property
    def total_cost_display(self) -> str:
        """Human-readable total cost range."""
        return f"₹{self.total_cost_low:,.0f}–₹{self.total_cost_high:,.0f}"

    # ── Item Counts ──────────────────────────────────────────────────────

    @property
    def item_count(self) -> int:
        """Total number of BOM line items."""
        return len(self.items)

    @property
    def total_quantity(self) -> int:
        """Total number of physical units to procure."""
        return sum(item.quantity for item in self.items)

    # ── Lead Time Analysis ───────────────────────────────────────────────

    @property
    def max_lead_time_days(self) -> int:
        """Maximum lead time across all items (project-level constraint)."""
        return max(item.lead_time_days_max for item in self.items)

    @property
    def critical_path_lead_time_days(self) -> int:
        """Maximum lead time of critical-path items only."""
        critical = self.get_critical_path_items()
        if not critical:
            return 0
        return max(item.lead_time_days_max for item in critical)

    # ── Lookups ──────────────────────────────────────────────────────────

    def get_item(self, item_id: str) -> BOMItem:
        """Retrieve a BOM item by its ID.

        Raises
        ------
        KeyError
            If *item_id* is not in the BOM.
        """
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(
            f"Unknown item_id {item_id!r}. "
            f"Known items: {[i.item_id for i in self.items]}"
        )

    def get_items_by_node(self, node: str) -> list[BOMItem]:
        """Return all items for a specific node."""
        return [i for i in self.items if i.node == node or i.node == "all"]

    def get_items_by_category(self, category: BOMCategory) -> list[BOMItem]:
        """Return all items of a specific category."""
        return [i for i in self.items if i.category == category]

    def get_critical_path_items(self) -> list[BOMItem]:
        """Return items flagged as critical-path.

        These items have the longest lead times and gate the install
        timeline. The vibration node is the primary critical-path item
        per PRD §8.
        """
        return [i for i in self.items if i.is_critical_path]

    def get_items_by_status(self, status: ProcurementStatus) -> list[BOMItem]:
        """Return all items with a given procurement status."""
        return [i for i in self.items if i.status == status]

    def get_items_by_availability(self, availability: Availability) -> list[BOMItem]:
        """Return all items with a given availability level."""
        return [i for i in self.items if i.availability == availability]

    # ── Status Management ────────────────────────────────────────────────

    def mark_status(self, item_id: str, status: ProcurementStatus) -> BOMItem:
        """Update the procurement status of a BOM item.

        Parameters
        ----------
        item_id : str
            The item to update.
        status : ProcurementStatus
            The new status.

        Returns
        -------
        BOMItem
            The updated item.
        """
        item = self.get_item(item_id)
        item.status = status
        logger.info("BOM item %s → %s: %s", item_id, status.value, item.name)
        return item

    # ── Node Cost Breakdown ──────────────────────────────────────────────

    def get_cost_by_node(self) -> dict[str, dict[str, float]]:
        """Return cost breakdown per node.

        Returns
        -------
        dict
            ``{node_id: {"low": float, "high": float}}``
        """
        breakdown: dict[str, dict[str, float]] = {}
        for item in self.items:
            node = item.node
            if node not in breakdown:
                breakdown[node] = {"low": 0, "high": 0}
            breakdown[node]["low"] += item.total_cost_low
            breakdown[node]["high"] += item.total_cost_high
        return breakdown

    # ── Category Cost Breakdown ──────────────────────────────────────────

    def get_cost_by_category(self) -> dict[str, dict[str, float]]:
        """Return cost breakdown per category.

        Returns
        -------
        dict
            ``{category: {"low": float, "high": float}}``
        """
        breakdown: dict[str, dict[str, float]] = {}
        for item in self.items:
            cat = item.category.value
            if cat not in breakdown:
                breakdown[cat] = {"low": 0, "high": 0}
            breakdown[cat]["low"] += item.total_cost_low
            breakdown[cat]["high"] += item.total_cost_high
        return breakdown

    # ── Printable Sheet ──────────────────────────────────────────────────

    def print_sheet(self) -> str:
        """Generate a human-readable markdown BOM sheet.

        Returns
        -------
        str
            Markdown-formatted BOM sheet.
        """
        lines: list[str] = []
        lines.append("# OI-73 Bill of Materials — 2-Node POC")
        lines.append("")
        lines.append(f"**Total items:** {self.item_count}")
        lines.append(f"**Total units:** {self.total_quantity}")
        lines.append(f"**Estimated CapEx:** {self.total_cost_display}")
        lines.append(
            f"**Critical-path lead time:** {self.critical_path_lead_time_days} days"
        )
        lines.append("")

        # Group by category
        categories_seen: list[str] = []
        for item in self.items:
            cat = item.category.value
            if cat not in categories_seen:
                categories_seen.append(cat)

        for cat in categories_seen:
            cat_items = [i for i in self.items if i.category.value == cat]
            lines.append(f"## {cat.replace('_', ' ').title()}")
            lines.append("")
            lines.append(
                "| ID | Item | Make/Model | Qty | Unit Cost | "
                "Lead Time | Avail | Critical? |"
            )
            lines.append(
                "|----|----- |------------|-----|-----------|"
                "-----------|-------|-----------|"
            )
            for item in cat_items:
                cp = "⚠ YES" if item.is_critical_path else "—"
                lines.append(
                    f"| {item.item_id} | {item.name} | {item.make_model} | "
                    f"{item.quantity} | {item.cost_display} | "
                    f"{item.lead_time_display} | {item.availability.value} | {cp} |"
                )
            lines.append("")

        # Critical path summary
        critical = self.get_critical_path_items()
        if critical:
            lines.append("## ⚠ Critical-Path Items")
            lines.append("")
            for item in critical:
                lines.append(
                    f"- **{item.item_id}**: {item.name} ({item.make_model}) — "
                    f"lead time {item.lead_time_display}"
                )
                lines.append(f"  - {item.notes}")
            lines.append("")

        # Cost summary
        lines.append("## Cost Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total CapEx (low) | ₹{self.total_cost_low:,.0f} |")
        lines.append(f"| Total CapEx (high) | ₹{self.total_cost_high:,.0f} |")
        lines.append(
            f"| Max lead time | {self.max_lead_time_days} days |"
        )
        lines.append(
            f"| Critical-path lead time | "
            f"{self.critical_path_lead_time_days} days |"
        )
        lines.append("")

        result = "\n".join(lines)
        logger.info("BOM sheet generated (%d items)", self.item_count)
        return result

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full BOM to dict."""
        return {
            "bom": "OI-73 Bill of Materials — 2-Node POC",
            "item_count": self.item_count,
            "total_quantity": self.total_quantity,
            "total_cost_low": self.total_cost_low,
            "total_cost_high": self.total_cost_high,
            "max_lead_time_days": self.max_lead_time_days,
            "critical_path_lead_time_days": self.critical_path_lead_time_days,
            "critical_path_items": [
                i.to_dict() for i in self.get_critical_path_items()
            ],
            "cost_by_node": self.get_cost_by_node(),
            "cost_by_category": self.get_cost_by_category(),
            "items": [i.to_dict() for i in self.items],
        }


# ── Report Generator ─────────────────────────────────────────────────────────


def generate_bom_report(bom: BOMSheet | None = None) -> dict[str, Any]:
    """Generate a complete BOM report.

    Combines the BOM sheet with cost analysis, lead-time analysis, and
    critical-path assessment into a single structured report.

    Parameters
    ----------
    bom : BOMSheet, optional
        The BOM sheet to report on. Creates the default POC BOM if not
        provided.

    Returns
    -------
    dict
        Structured report suitable for JSON export.
    """
    sheet = bom or BOMSheet()

    report = {
        "report": "OI-73 BOM + Procurement Lead Times Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": {
            "bom_sheet_with_qty_cost_lead_time": True,
            "critical_path_items_flagged": len(sheet.get_critical_path_items()) > 0,
        },
        "summary": {
            "total_items": sheet.item_count,
            "total_units": sheet.total_quantity,
            "capex_low_inr": sheet.total_cost_low,
            "capex_high_inr": sheet.total_cost_high,
            "max_lead_time_days": sheet.max_lead_time_days,
            "critical_path_lead_time_days": sheet.critical_path_lead_time_days,
        },
        "critical_path": [i.to_dict() for i in sheet.get_critical_path_items()],
        "cost_by_node": sheet.get_cost_by_node(),
        "cost_by_category": sheet.get_cost_by_category(),
        "bom": sheet.to_dict(),
    }

    logger.info(
        "BOM report generated: %d items, ₹%,.0f–₹%,.0f, "
        "critical path %d days",
        sheet.item_count,
        sheet.total_cost_low,
        sheet.total_cost_high,
        sheet.critical_path_lead_time_days,
    )

    return report
