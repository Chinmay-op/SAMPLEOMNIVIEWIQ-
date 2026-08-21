"""
Tests for OI-73 — Bill of Materials + Procurement Lead Times
==============================================================

Self-contained unit tests. No DB, no MQTT, no external deps.
Verifies:
  - BOM item structure and validation
  - BOM sheet cost and lead-time analysis
  - Critical-path flagging
  - Node and category breakdowns
  - Procurement status lifecycle
  - Report generation
  - PRD §3 compliance (cost range, items, vendors)
"""

from __future__ import annotations

import json

import pytest

from omniview.edge.bom import (
    Availability,
    BOMCategory,
    BOMItem,
    BOMSheet,
    ProcurementStatus,
    generate_bom_report,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def bom() -> BOMSheet:
    """Standard POC BOM sheet."""
    return BOMSheet()


# ── TestBOMItem ──────────────────────────────────────────────────────────────


class TestBOMItem:
    """Tests for individual BOM line item."""

    def test_create_item(self):
        item = BOMItem(
            item_id="TEST-001",
            name="Test Item",
            make_model="Test Maker X100",
            category=BOMCategory.SENSOR,
            function="Testing",
            node="compressor-01",
            device_id="test-device",
            quantity=2,
            unit_cost_inr_low=1000,
            unit_cost_inr_high=2000,
            lead_time_days_min=1,
            lead_time_days_max=3,
            availability=Availability.HIGH,
            vendor_location="Test Vendor",
        )
        assert item.item_id == "TEST-001"
        assert item.quantity == 2
        assert item.status == ProcurementStatus.NOT_ORDERED

    def test_total_cost(self):
        item = BOMItem(
            item_id="T1", name="T", make_model="T", category=BOMCategory.SENSOR,
            function="T", node="t", device_id="t", quantity=3,
            unit_cost_inr_low=1000, unit_cost_inr_high=2000,
            lead_time_days_min=1, lead_time_days_max=5,
            availability=Availability.HIGH, vendor_location="T",
        )
        assert item.total_cost_low == 3000
        assert item.total_cost_high == 6000

    def test_lead_time_display_range(self):
        item = BOMItem(
            item_id="T1", name="T", make_model="T", category=BOMCategory.SENSOR,
            function="T", node="t", device_id="t", quantity=1,
            unit_cost_inr_low=100, unit_cost_inr_high=200,
            lead_time_days_min=7, lead_time_days_max=14,
            availability=Availability.MEDIUM, vendor_location="T",
        )
        assert item.lead_time_display == "7–14 days"

    def test_lead_time_display_single(self):
        item = BOMItem(
            item_id="T1", name="T", make_model="T", category=BOMCategory.SENSOR,
            function="T", node="t", device_id="t", quantity=1,
            unit_cost_inr_low=100, unit_cost_inr_high=200,
            lead_time_days_min=3, lead_time_days_max=3,
            availability=Availability.HIGH, vendor_location="T",
        )
        assert item.lead_time_display == "3 days"

    def test_cost_display(self):
        item = BOMItem(
            item_id="T1", name="T", make_model="T", category=BOMCategory.SENSOR,
            function="T", node="t", device_id="t", quantity=1,
            unit_cost_inr_low=4000, unit_cost_inr_high=6000,
            lead_time_days_min=1, lead_time_days_max=3,
            availability=Availability.VERY_HIGH, vendor_location="T",
        )
        assert "4,000" in item.cost_display
        assert "6,000" in item.cost_display

    def test_to_dict_complete(self):
        item = BOMItem(
            item_id="T1", name="Test", make_model="TM", category=BOMCategory.METER,
            function="F", node="n", device_id="d", quantity=1,
            unit_cost_inr_low=100, unit_cost_inr_high=200,
            lead_time_days_min=1, lead_time_days_max=3,
            availability=Availability.HIGH, vendor_location="V",
            is_critical_path=True, notes="Note",
        )
        d = item.to_dict()
        assert d["item_id"] == "T1"
        assert d["category"] == "meter"
        assert d["is_critical_path"] is True
        assert d["total_cost_low"] == 100
        assert d["total_cost_high"] == 200
        assert d["status"] == "not_ordered"


# ── TestBOMSheet ─────────────────────────────────────────────────────────────


class TestBOMSheet:
    """Tests for the full BOM sheet."""

    def test_item_count(self, bom: BOMSheet):
        assert bom.item_count == 19

    def test_total_quantity(self, bom: BOMSheet):
        assert bom.total_quantity >= 22  # All units summed

    def test_total_cost_range(self, bom: BOMSheet):
        # PRD §3: ₹95,000–₹1,20,000 for sensors (excl install labor)
        # Our BOM includes ancillary items too, so may be slightly higher
        assert bom.total_cost_low > 0
        assert bom.total_cost_high > bom.total_cost_low
        assert bom.total_cost_high < 200000  # Sanity ceiling

    def test_max_lead_time(self, bom: BOMSheet):
        assert bom.max_lead_time_days >= 14  # Vibration node: 1–2 weeks

    def test_has_critical_path_items(self, bom: BOMSheet):
        critical = bom.get_critical_path_items()
        assert len(critical) >= 1

    def test_critical_path_is_vibration_node(self, bom: BOMSheet):
        critical = bom.get_critical_path_items()
        names = [i.name for i in critical]
        assert any("Vibration" in n for n in names)

    def test_critical_path_lead_time(self, bom: BOMSheet):
        assert bom.critical_path_lead_time_days >= 14


# ── TestBOMItems ─────────────────────────────────────────────────────────────


class TestBOMItems:
    """Verify all expected BOM items exist (PRD §3 compliance)."""

    def test_has_mfm384_compressor(self, bom: BOMSheet):
        item = bom.get_item("BOM-001")
        assert "MFM384" in item.make_model
        assert item.node == "compressor-01"

    def test_has_mfm384_isbm(self, bom: BOMSheet):
        item = bom.get_item("BOM-002")
        assert "MFM384" in item.make_model
        assert item.node == "isbm-01"

    def test_has_ct_compressor(self, bom: BOMSheet):
        item = bom.get_item("BOM-003")
        assert "SCCT" in item.make_model
        assert item.quantity == 3  # R/Y/B phases

    def test_has_ct_isbm(self, bom: BOMSheet):
        item = bom.get_item("BOM-004")
        assert "SCCT" in item.make_model
        assert item.quantity == 3  # R/Y/B phases

    def test_has_vibration_node(self, bom: BOMSheet):
        item = bom.get_item("BOM-005")
        assert "Banner" in item.make_model or "Q45VT" in item.make_model
        assert item.is_critical_path is True

    def test_has_wika_pressure(self, bom: BOMSheet):
        item = bom.get_item("BOM-006")
        assert "WIKA" in item.make_model
        assert "A-10" in item.make_model

    def test_has_gateway(self, bom: BOMSheet):
        item = bom.get_item("BOM-012")
        assert "RUT956" in item.make_model
        assert item.category == BOMCategory.GATEWAY

    def test_has_jumbo_display(self, bom: BOMSheet):
        item = bom.get_item("BOM-013")
        assert "RS-6006" in item.make_model or "Multispan" in item.make_model
        assert item.category == BOMCategory.DISPLAY

    def test_has_heattag_gas(self, bom: BOMSheet):
        item = bom.get_item("BOM-007")
        assert "HeatTag" in item.make_model

    def test_has_thermal_isbm(self, bom: BOMSheet):
        item = bom.get_item("BOM-008")
        assert item.node == "isbm-01"
        assert item.device_id == "pune-isbm-therm01"

    def test_has_stroke_counter(self, bom: BOMSheet):
        item = bom.get_item("BOM-010")
        assert item.device_id == "pune-isbm-stroke01"

    def test_has_ambient_sensor(self, bom: BOMSheet):
        item = bom.get_item("BOM-011")
        assert item.device_id == "pune-floor-ambient01"

    def test_has_rs485_cable(self, bom: BOMSheet):
        item = bom.get_item("BOM-014")
        assert item.category == BOMCategory.CABLING

    def test_has_420ma_converter(self, bom: BOMSheet):
        item = bom.get_item("BOM-016")
        assert "Modbus" in item.function


# ── TestNodeBreakdown ────────────────────────────────────────────────────────


class TestNodeBreakdown:
    """Test node-level cost breakdown."""

    def test_compressor_items(self, bom: BOMSheet):
        items = bom.get_items_by_node("compressor-01")
        assert len(items) >= 5

    def test_isbm_items(self, bom: BOMSheet):
        items = bom.get_items_by_node("isbm-01")
        assert len(items) >= 3

    def test_cost_by_node_keys(self, bom: BOMSheet):
        breakdown = bom.get_cost_by_node()
        assert "compressor-01" in breakdown
        assert "isbm-01" in breakdown

    def test_cost_by_node_values(self, bom: BOMSheet):
        breakdown = bom.get_cost_by_node()
        for node_costs in breakdown.values():
            assert node_costs["low"] >= 0
            assert node_costs["high"] >= node_costs["low"]


# ── TestCategoryBreakdown ────────────────────────────────────────────────────


class TestCategoryBreakdown:
    """Test category-level cost breakdown."""

    def test_has_sensor_category(self, bom: BOMSheet):
        items = bom.get_items_by_category(BOMCategory.SENSOR)
        assert len(items) >= 4

    def test_has_meter_category(self, bom: BOMSheet):
        items = bom.get_items_by_category(BOMCategory.METER)
        assert len(items) == 2  # Compressor + ISBM MFM384

    def test_has_gateway_category(self, bom: BOMSheet):
        items = bom.get_items_by_category(BOMCategory.GATEWAY)
        assert len(items) == 1

    def test_cost_by_category_keys(self, bom: BOMSheet):
        breakdown = bom.get_cost_by_category()
        assert "sensor" in breakdown
        assert "meter" in breakdown
        assert "gateway" in breakdown


# ── TestProcurementLifecycle ─────────────────────────────────────────────────


class TestProcurementLifecycle:
    """Test procurement status tracking."""

    def test_initial_status(self, bom: BOMSheet):
        for item in bom.items:
            assert item.status == ProcurementStatus.NOT_ORDERED

    def test_mark_ordered(self, bom: BOMSheet):
        item = bom.mark_status("BOM-005", ProcurementStatus.ORDERED)
        assert item.status == ProcurementStatus.ORDERED

    def test_mark_received(self, bom: BOMSheet):
        bom.mark_status("BOM-005", ProcurementStatus.RECEIVED)
        item = bom.get_item("BOM-005")
        assert item.status == ProcurementStatus.RECEIVED

    def test_mark_unknown_raises(self, bom: BOMSheet):
        with pytest.raises(KeyError, match="UNKNOWN"):
            bom.mark_status("UNKNOWN-99", ProcurementStatus.ORDERED)

    def test_get_items_by_status(self, bom: BOMSheet):
        not_ordered = bom.get_items_by_status(ProcurementStatus.NOT_ORDERED)
        assert len(not_ordered) == bom.item_count

        bom.mark_status("BOM-001", ProcurementStatus.ORDERED)
        not_ordered = bom.get_items_by_status(ProcurementStatus.NOT_ORDERED)
        ordered = bom.get_items_by_status(ProcurementStatus.ORDERED)
        assert len(ordered) == 1
        assert len(not_ordered) == bom.item_count - 1


# ── TestAvailability ─────────────────────────────────────────────────────────


class TestAvailability:
    """Test availability filtering."""

    def test_very_high_availability(self, bom: BOMSheet):
        items = bom.get_items_by_availability(Availability.VERY_HIGH)
        assert len(items) >= 5

    def test_medium_availability(self, bom: BOMSheet):
        items = bom.get_items_by_availability(Availability.MEDIUM)
        assert len(items) >= 1  # At least vibration node

    def test_vibration_is_medium(self, bom: BOMSheet):
        vib = bom.get_item("BOM-005")
        assert vib.availability == Availability.MEDIUM


# ── TestBOMPrintable ─────────────────────────────────────────────────────────


class TestBOMPrintable:
    """Test the printable BOM sheet."""

    def test_markdown_output(self, bom: BOMSheet):
        md = bom.print_sheet()
        assert "# OI-73 Bill of Materials" in md
        assert "Critical-Path Items" in md
        assert "Cost Summary" in md

    def test_contains_all_items(self, bom: BOMSheet):
        md = bom.print_sheet()
        for item in bom.items:
            assert item.item_id in md

    def test_contains_cost_summary(self, bom: BOMSheet):
        md = bom.print_sheet()
        assert "Total CapEx" in md

    def test_contains_lead_time(self, bom: BOMSheet):
        md = bom.print_sheet()
        assert "lead time" in md.lower() or "Lead Time" in md


# ── TestReportGeneration ─────────────────────────────────────────────────────


class TestReportGeneration:
    """Test the BOM report generator."""

    def test_generate_report(self):
        report = generate_bom_report()
        assert report["report"] == "OI-73 BOM + Procurement Lead Times Report"
        assert "acceptance_criteria" in report
        assert "summary" in report
        assert "critical_path" in report

    def test_acceptance_criteria(self):
        report = generate_bom_report()
        ac = report["acceptance_criteria"]
        assert ac["bom_sheet_with_qty_cost_lead_time"] is True
        assert ac["critical_path_items_flagged"] is True

    def test_summary_values(self):
        report = generate_bom_report()
        summary = report["summary"]
        assert summary["total_items"] == 19
        assert summary["total_units"] >= 22
        assert summary["capex_low_inr"] > 0
        assert summary["capex_high_inr"] > summary["capex_low_inr"]
        assert summary["critical_path_lead_time_days"] >= 14

    def test_critical_path_in_report(self):
        report = generate_bom_report()
        cp = report["critical_path"]
        assert len(cp) >= 1
        assert any("Vibration" in item["name"] for item in cp)

    def test_report_json_serializable(self):
        report = generate_bom_report()
        json_str = json.dumps(report)
        assert len(json_str) > 1000
        parsed = json.loads(json_str)
        assert parsed["report"] == "OI-73 BOM + Procurement Lead Times Report"


# ── TestCostValidation ───────────────────────────────────────────────────────


class TestCostValidation:
    """Validate costs against PRD §3 estimates."""

    def test_mfm384_cost_range(self, bom: BOMSheet):
        """PRD §3: MFM384 ₹4,000–₹6,000."""
        item = bom.get_item("BOM-001")
        assert item.unit_cost_inr_low == 4000
        assert item.unit_cost_inr_high == 6000

    def test_ct_cost_range(self, bom: BOMSheet):
        """PRD §3: SCCT ₹1,500–₹2,000/phase."""
        item = bom.get_item("BOM-003")
        assert item.unit_cost_inr_low == 1500
        assert item.unit_cost_inr_high == 2000

    def test_vibration_cost_range(self, bom: BOMSheet):
        """PRD §3: Banner Q45VT ₹25,000–₹35,000."""
        item = bom.get_item("BOM-005")
        assert item.unit_cost_inr_low == 25000
        assert item.unit_cost_inr_high == 35000

    def test_wika_cost_range(self, bom: BOMSheet):
        """PRD §3: WIKA A-10 ~₹15,000."""
        item = bom.get_item("BOM-006")
        assert 10000 <= item.unit_cost_inr_low <= 20000

    def test_gateway_cost_range(self, bom: BOMSheet):
        """PRD §3: RUT956 ₹22,000–₹29,000."""
        item = bom.get_item("BOM-012")
        assert item.unit_cost_inr_low == 22000
        assert item.unit_cost_inr_high == 29000

    def test_jumbo_cost_range(self, bom: BOMSheet):
        """PRD §3: RS-6006 ₹15,000–₹22,000."""
        item = bom.get_item("BOM-013")
        assert item.unit_cost_inr_low == 15000
        assert item.unit_cost_inr_high == 22000


# ── TestDeviceIdMapping ──────────────────────────────────────────────────────


class TestDeviceIdMapping:
    """Verify device_ids match edge_nodes.json config."""

    EXPECTED_DEVICE_IDS = [
        "pune-comp-mfm384",
        "pune-comp-vib01",
        "pune-comp-wika01",
        "pune-comp-therm01",
        "pune-comp-gas01",
        "pune-isbm-mfm384",
        "pune-isbm-therm01",
        "pune-isbm-stroke01",
        "pune-floor-ambient01",
    ]

    def test_all_device_ids_present(self, bom: BOMSheet):
        bom_device_ids = {i.device_id for i in bom.items if i.device_id}
        for did in self.EXPECTED_DEVICE_IDS:
            assert did in bom_device_ids, f"device_id {did!r} missing from BOM"

    def test_no_unknown_device_ids(self, bom: BOMSheet):
        bom_device_ids = {i.device_id for i in bom.items if i.device_id}
        known = set(self.EXPECTED_DEVICE_IDS)
        for did in bom_device_ids:
            assert did in known, f"Unexpected device_id {did!r} in BOM"
