"""
Tests for OI-74 — Site Walkthrough + Layer 0 Profile
======================================================

Self-contained unit tests. No DB, no MQTT, no external deps.
Verifies:
  - Layer 0 profile structure (site, tariff, machines, locations)
  - Location map completeness for both nodes
  - Machine profile details
  - Walkthrough checklist lifecycle
  - Report generation and acceptance criteria
"""

from __future__ import annotations

import json

import pytest

from omniview.edge.site_profile import (
    AccessLevel,
    ConfirmationStatus,
    FloorZone,
    Layer0Profile,
    LocationPoint,
    MachineProfile,
    SiteInfo,
    SiteWalkthrough,
    TariffProfile,
    WalkthroughItem,
    generate_walkthrough_report,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def profile() -> Layer0Profile:
    return Layer0Profile()


@pytest.fixture
def walkthrough(profile: Layer0Profile) -> SiteWalkthrough:
    return SiteWalkthrough(profile)


# ── TestSiteInfo ─────────────────────────────────────────────────────────────


class TestSiteInfo:

    def test_default_site_id(self):
        s = SiteInfo()
        assert s.site_id == "pune-isbm"

    def test_timezone(self):
        s = SiteInfo()
        assert s.timezone == "Asia/Kolkata"

    def test_to_dict(self):
        d = SiteInfo().to_dict()
        assert "site_id" in d
        assert "operating_hours" in d
        assert d["operating_hours"] == "24/7 continuous production"


# ── TestTariffProfile ────────────────────────────────────────────────────────


class TestTariffProfile:

    def test_defaults(self):
        t = TariffProfile()
        assert t.utility == "MSEDCL"
        assert t.contracted_demand_kva == 500.0
        assert t.billing_window_minutes == 15

    def test_to_dict(self):
        d = TariffProfile().to_dict()
        assert d["contracted_demand_kva"] == 500.0
        assert d["penalty_rate_per_kva"] == 350.0


# ── TestLocationPoint ────────────────────────────────────────────────────────


class TestLocationPoint:

    def test_create_point(self):
        loc = LocationPoint(
            point_id="TEST-01", name="Test", node_id="test",
            device_id="dev", zone=FloorZone.COMPRESSOR_ROOM,
            description="Test point", access_level=AccessLevel.OPEN,
        )
        assert loc.point_id == "TEST-01"
        assert loc.zone == FloorZone.COMPRESSOR_ROOM

    def test_to_dict(self):
        loc = LocationPoint(
            point_id="T", name="T", node_id="n", device_id="d",
            zone=FloorZone.PRODUCTION_FLOOR, description="D",
            access_level=AccessLevel.PANEL_DOOR,
        )
        d = loc.to_dict()
        assert d["zone"] == "production_floor"
        assert d["access_level"] == "panel_door"


# ── TestMachineProfile ───────────────────────────────────────────────────────


class TestMachineProfile:

    def test_compressor_profile(self, profile: Layer0Profile):
        m = profile.get_machine("MACH-COMP-01")
        assert m.node_id == "compressor-01"
        assert m.nameplate_kw == 37
        assert m.nameplate_bar == 40
        assert m.connection_type == "single_feed"

    def test_isbm_profile(self, profile: Layer0Profile):
        m = profile.get_machine("MACH-ISBM-01")
        assert m.node_id == "isbm-01"
        assert "Nissei" in m.make_model
        assert m.connection_type == "single_feed"

    def test_compressor_zone(self, profile: Layer0Profile):
        m = profile.get_machine("MACH-COMP-01")
        assert m.location_zone == FloorZone.COMPRESSOR_ROOM

    def test_isbm_zone(self, profile: Layer0Profile):
        m = profile.get_machine("MACH-ISBM-01")
        assert m.location_zone == FloorZone.PRODUCTION_FLOOR

    def test_unknown_machine_raises(self, profile: Layer0Profile):
        with pytest.raises(KeyError):
            profile.get_machine("UNKNOWN")

    def test_machine_by_node(self, profile: Layer0Profile):
        m = profile.get_machine_by_node("compressor-01")
        assert m is not None
        assert m.machine_id == "MACH-COMP-01"

    def test_machine_by_unknown_node(self, profile: Layer0Profile):
        m = profile.get_machine_by_node("nonexistent")
        assert m is None

    def test_machine_to_dict(self, profile: Layer0Profile):
        m = profile.get_machine("MACH-COMP-01")
        d = m.to_dict()
        assert d["nameplate_kw"] == 37
        assert d["location_zone"] == "compressor_room"


# ── TestLayer0Profile ────────────────────────────────────────────────────────


class TestLayer0Profile:

    def test_machine_count(self, profile: Layer0Profile):
        assert profile.machine_count == 2

    def test_location_count(self, profile: Layer0Profile):
        assert profile.location_count == 10

    def test_compressor_locations(self, profile: Layer0Profile):
        locs = profile.get_locations_for_node("compressor-01")
        assert len(locs) == 4  # Panel, bearing, gauge port, switchboard

    def test_isbm_locations(self, profile: Layer0Profile):
        locs = profile.get_locations_for_node("isbm-01")
        assert len(locs) == 3  # Panel, barrel, ejection

    def test_floor_locations(self, profile: Layer0Profile):
        locs = profile.get_locations_for_node("floor")
        assert len(locs) == 3  # Ambient, jumbo, gateway

    def test_locations_by_zone(self, profile: Layer0Profile):
        comp_room = profile.get_locations_by_zone(FloorZone.COMPRESSOR_ROOM)
        assert len(comp_room) >= 4

    def test_location_lookup(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-C01")
        assert loc.node_id == "compressor-01"
        assert "MFM384" in loc.description

    def test_unknown_location_raises(self, profile: Layer0Profile):
        with pytest.raises(KeyError):
            profile.get_location("LOC-UNKNOWN")

    def test_to_dict_keys(self, profile: Layer0Profile):
        d = profile.to_dict()
        assert "site" in d
        assert "tariff" in d
        assert "machines" in d
        assert "locations" in d
        assert d["machine_count"] == 2
        assert d["location_count"] == 10

    def test_json_serializable(self, profile: Layer0Profile):
        d = profile.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["layer"] == "Layer 0 — Site Configuration"

    def test_print_profile_markdown(self, profile: Layer0Profile):
        md = profile.print_profile()
        assert "# Layer 0" in md
        assert "Site Information" in md
        assert "Machine Inventory" in md
        assert "Location Map" in md
        assert "LOC-C01" in md
        assert "LOC-I01" in md


# ── TestLocationMapDetails ───────────────────────────────────────────────────


class TestLocationMapDetails:
    """Verify location map has correct details per PRD §1.4."""

    def test_comp_panel_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-C01")
        assert loc.device_id == "pune-comp-mfm384"
        assert loc.access_level == AccessLevel.PANEL_DOOR

    def test_comp_bearing_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-C02")
        assert loc.device_id == "pune-comp-vib01"
        assert loc.access_level == AccessLevel.OPEN

    def test_comp_gauge_port(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-C03")
        assert loc.device_id == "pune-comp-wika01"
        assert "gauge port" in loc.description.lower()

    def test_comp_switchboard(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-C04")
        assert loc.device_id == "pune-comp-gas01"

    def test_isbm_panel_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-I01")
        assert loc.device_id == "pune-isbm-mfm384"
        assert loc.access_level == AccessLevel.PANEL_DOOR

    def test_isbm_barrel_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-I02")
        assert loc.device_id == "pune-isbm-therm01"
        assert "barrel" in loc.description.lower() or "hot-runner" in loc.description.lower()

    def test_isbm_stroke_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-I03")
        assert loc.device_id == "pune-isbm-stroke01"

    def test_ambient_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-F01")
        assert loc.device_id == "pune-floor-ambient01"

    def test_gateway_location(self, profile: Layer0Profile):
        loc = profile.get_location("LOC-F03")
        assert "RUT956" in loc.description

    def test_all_locations_have_safety_notes(self, profile: Layer0Profile):
        for loc in profile.locations:
            assert loc.safety_notes, f"{loc.point_id} missing safety_notes"

    def test_all_locations_have_cable_routes(self, profile: Layer0Profile):
        for loc in profile.locations:
            assert loc.cable_route_notes, f"{loc.point_id} missing cable_route_notes"


# ── TestSiteWalkthrough ──────────────────────────────────────────────────────


class TestSiteWalkthrough:

    def test_item_count(self, walkthrough: SiteWalkthrough):
        assert walkthrough.item_count == 20

    def test_initial_all_pending(self, walkthrough: SiteWalkthrough):
        assert walkthrough.pending_count == 20
        assert walkthrough.confirmed_count == 0

    def test_not_all_confirmed_initially(self, walkthrough: SiteWalkthrough):
        assert walkthrough.all_confirmed is False

    def test_confirm_item(self, walkthrough: SiteWalkthrough):
        item = walkthrough.confirm_item("WT-01", "Compressor is Atlas Copco GA37")
        assert item.status == ConfirmationStatus.CONFIRMED
        assert "Atlas Copco" in item.finding

    def test_flag_revision(self, walkthrough: SiteWalkthrough):
        item = walkthrough.flag_revision("WT-09", "ISBM has split sub-panels")
        assert item.status == ConfirmationStatus.NEEDS_REVISION
        assert "split" in item.finding

    def test_unknown_item_raises(self, walkthrough: SiteWalkthrough):
        with pytest.raises(KeyError):
            walkthrough.get_item("WT-UNKNOWN")

    def test_items_by_node(self, walkthrough: SiteWalkthrough):
        comp_items = walkthrough.get_items_by_node("compressor-01")
        assert len(comp_items) >= 7  # 7 comp-specific + site-wide

    def test_items_by_status(self, walkthrough: SiteWalkthrough):
        pending = walkthrough.get_items_by_status(ConfirmationStatus.PENDING)
        assert len(pending) == 20

        walkthrough.confirm_item("WT-01")
        pending = walkthrough.get_items_by_status(ConfirmationStatus.PENDING)
        confirmed = walkthrough.get_items_by_status(ConfirmationStatus.CONFIRMED)
        assert len(confirmed) == 1
        assert len(pending) == 19

    def test_all_confirmed_after_marking(self, walkthrough: SiteWalkthrough):
        for item in walkthrough.items:
            walkthrough.confirm_item(item.item_id)
        assert walkthrough.all_confirmed is True

    def test_print_checklist(self, walkthrough: SiteWalkthrough):
        md = walkthrough.print_checklist()
        assert "# OI-74 Site Walkthrough Checklist" in md
        assert "WT-01" in md
        assert "WT-20" in md

    def test_checklist_shows_confirmed(self, walkthrough: SiteWalkthrough):
        walkthrough.confirm_item("WT-01", "Confirmed")
        md = walkthrough.print_checklist()
        assert "[x] **WT-01**" in md

    def test_to_dict(self, walkthrough: SiteWalkthrough):
        d = walkthrough.to_dict()
        assert d["item_count"] == 20
        assert d["all_confirmed"] is False
        assert len(d["items"]) == 20


# ── TestWalkthroughItems ─────────────────────────────────────────────────────


class TestWalkthroughItems:
    """Verify walkthrough covers all PRD §9 Phase 0 items."""

    def test_has_compressor_nameplate(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-01")
        assert "make/model" in item.check.lower()

    def test_has_isbm_nameplate(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-08")
        assert "make/model" in item.check.lower()

    def test_has_single_feed_check(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-09")
        assert "single connection" in item.check.lower()

    def test_has_contracted_demand(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-14")
        assert "demand" in item.check.lower() or "kVA" in item.check

    def test_has_safety_signoff(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-19")
        assert "safety" in item.check.lower()

    def test_has_gauge_port_check(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-06")
        assert "gauge port" in item.check.lower()

    def test_has_bearing_mount_check(self, walkthrough: SiteWalkthrough):
        item = walkthrough.get_item("WT-05")
        assert "bearing" in item.check.lower() or "vibration" in item.check.lower()


# ── TestReportGeneration ─────────────────────────────────────────────────────


class TestReportGeneration:

    def test_generate_report(self):
        report = generate_walkthrough_report()
        assert report["report"] == "OI-74 Site Walkthrough + Layer 0 Profile"
        assert "acceptance_criteria" in report
        assert "summary" in report
        assert "layer0_profile" in report
        assert "walkthrough" in report

    def test_acceptance_criteria(self):
        report = generate_walkthrough_report()
        ac = report["acceptance_criteria"]
        assert ac["location_map_for_both_nodes"] is True
        assert ac["layer_0_profile_draft_complete"] is True

    def test_summary(self):
        report = generate_walkthrough_report()
        s = report["summary"]
        assert s["machines"] == 2
        assert s["locations"] == 10
        assert s["walkthrough_items"] == 20
        assert s["zones_covered"] >= 3

    def test_json_serializable(self):
        report = generate_walkthrough_report()
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["report"] == "OI-74 Site Walkthrough + Layer 0 Profile"
        assert len(json_str) > 2000
