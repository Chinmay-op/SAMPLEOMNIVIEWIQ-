"""
Tests for OI-75 — Safety / Access Sign-Off + Install Window
==============================================================

Self-contained unit tests. No DB, no MQTT, no external deps.
"""

from __future__ import annotations

import json

import pytest

from omniview.edge.safety_signoff import (
    HazardAssessment,
    HazardCategory,
    InstallWindow,
    PPERequirement,
    RiskLevel,
    SafetySignOff,
    SignOffStatus,
    WindowStatus,
    generate_safety_report,
)


@pytest.fixture
def signoff() -> SafetySignOff:
    return SafetySignOff()


# ── TestHazardAssessment ─────────────────────────────────────────────────────


class TestHazardAssessment:

    def test_create_hazard(self):
        h = HazardAssessment(
            hazard_id="T1", location_point_id="L1", location_name="Test",
            node_id="n", hazard_category=HazardCategory.ELECTRICAL,
            description="D", risk_before_controls=RiskLevel.HIGH,
            controls=["c1"], ppe_required=["gloves"],
            risk_after_controls=RiskLevel.LOW,
            zero_downtime_impact="No impact",
        )
        assert h.hazard_id == "T1"
        assert h.risk_after_controls == RiskLevel.LOW

    def test_to_dict(self):
        h = HazardAssessment(
            hazard_id="T1", location_point_id="L1", location_name="Test",
            node_id="n", hazard_category=HazardCategory.THERMAL,
            description="D", risk_before_controls=RiskLevel.HIGH,
            controls=[], ppe_required=[],
            risk_after_controls=RiskLevel.LOW,
            zero_downtime_impact="None",
        )
        d = h.to_dict()
        assert d["hazard_category"] == "thermal"
        assert d["risk_after_controls"] == "low"


# ── TestInstallWindow ────────────────────────────────────────────────────────


class TestInstallWindow:

    def test_create_window(self):
        w = InstallWindow(
            window_id="W1", node_id="n", description="Test",
            proposed_day="Day 1", proposed_shift="Day",
            duration_minutes=60,
        )
        assert w.requires_production_stop is False
        assert w.status == WindowStatus.PROPOSED

    def test_production_stop_raises(self):
        with pytest.raises(ValueError, match="zero production stoppage"):
            InstallWindow(
                window_id="BAD", node_id="n", description="Bad",
                proposed_day="D", proposed_shift="S",
                duration_minutes=60,
                requires_production_stop=True,
            )

    def test_to_dict(self):
        w = InstallWindow(
            window_id="W1", node_id="n", description="D",
            proposed_day="D1", proposed_shift="S1",
            duration_minutes=45,
        )
        d = w.to_dict()
        assert d["requires_production_stop"] is False
        assert d["status"] == "proposed"


# ── TestSafetySignOff ────────────────────────────────────────────────────────


class TestSafetySignOff:

    def test_hazard_count(self, signoff: SafetySignOff):
        assert signoff.hazard_count == 8

    def test_ppe_count(self, signoff: SafetySignOff):
        assert signoff.ppe_count == 5

    def test_window_count(self, signoff: SafetySignOff):
        assert signoff.window_count == 3

    def test_initial_status_draft(self, signoff: SafetySignOff):
        assert signoff.status == SignOffStatus.DRAFT
        assert signoff.is_approved is False

    def test_all_risks_low(self, signoff: SafetySignOff):
        assert signoff.all_risks_low is True

    def test_zero_production_stoppage(self, signoff: SafetySignOff):
        assert signoff.zero_production_stoppage is True

    def test_total_install_duration(self, signoff: SafetySignOff):
        assert signoff.total_install_duration_minutes == 190  # 85 + 75 + 30

    def test_zero_downtime_constraints(self, signoff: SafetySignOff):
        assert len(signoff.zero_downtime_constraints) == 8


# ── TestHazardDetails ────────────────────────────────────────────────────────


class TestHazardDetails:

    def test_electrical_hazards_exist(self, signoff: SafetySignOff):
        elec = [h for h in signoff.hazards if h.hazard_category == HazardCategory.ELECTRICAL]
        assert len(elec) == 2  # Compressor panel + ISBM panel

    def test_thermal_hazard_exists(self, signoff: SafetySignOff):
        thermal = [h for h in signoff.hazards if h.hazard_category == HazardCategory.THERMAL]
        assert len(thermal) == 1  # ISBM barrel

    def test_pressure_hazard_exists(self, signoff: SafetySignOff):
        pressure = [h for h in signoff.hazards if h.hazard_category == HazardCategory.PRESSURE]
        assert len(pressure) == 1

    def test_mechanical_hazards_exist(self, signoff: SafetySignOff):
        mech = [h for h in signoff.hazards if h.hazard_category == HazardCategory.MECHANICAL]
        assert len(mech) == 2  # Bearing + ejection

    def test_compressor_hazards(self, signoff: SafetySignOff):
        comp = signoff.get_hazards_for_node("compressor-01")
        assert len(comp) == 5

    def test_isbm_hazards(self, signoff: SafetySignOff):
        isbm = signoff.get_hazards_for_node("isbm-01")
        assert len(isbm) == 3

    def test_all_hazards_have_controls(self, signoff: SafetySignOff):
        for h in signoff.hazards:
            assert len(h.controls) > 0, f"{h.hazard_id} has no controls"

    def test_all_hazards_have_ppe(self, signoff: SafetySignOff):
        for h in signoff.hazards:
            assert len(h.ppe_required) > 0, f"{h.hazard_id} has no PPE"

    def test_all_hazards_document_downtime_impact(self, signoff: SafetySignOff):
        for h in signoff.hazards:
            assert "No impact" in h.zero_downtime_impact, (
                f"{h.hazard_id} should confirm zero downtime impact"
            )

    def test_lookup_hazard(self, signoff: SafetySignOff):
        h = signoff.get_hazard("HAZ-01")
        assert h.hazard_category == HazardCategory.ELECTRICAL

    def test_unknown_hazard_raises(self, signoff: SafetySignOff):
        with pytest.raises(KeyError):
            signoff.get_hazard("HAZ-UNKNOWN")


# ── TestPPERequirements ──────────────────────────────────────────────────────


class TestPPERequirements:

    def test_has_insulated_gloves(self, signoff: SafetySignOff):
        p = signoff.get_ppe_item("PPE-01")
        assert "Insulated" in p.item

    def test_has_arc_flash_ppe(self, signoff: SafetySignOff):
        p = signoff.get_ppe_item("PPE-02")
        assert "Arc Flash" in p.item

    def test_has_safety_glasses(self, signoff: SafetySignOff):
        p = signoff.get_ppe_item("PPE-03")
        assert "Safety Glasses" in p.item

    def test_has_hearing_protection(self, signoff: SafetySignOff):
        p = signoff.get_ppe_item("PPE-04")
        assert "Hearing" in p.item

    def test_has_heat_resistant_gloves(self, signoff: SafetySignOff):
        p = signoff.get_ppe_item("PPE-05")
        assert "Heat" in p.item

    def test_unknown_ppe_raises(self, signoff: SafetySignOff):
        with pytest.raises(KeyError):
            signoff.get_ppe_item("PPE-UNKNOWN")


# ── TestInstallWindows ───────────────────────────────────────────────────────


class TestInstallWindows:

    def test_compressor_window(self, signoff: SafetySignOff):
        w = signoff.get_window("WIN-01")
        assert w.node_id == "compressor-01"
        assert w.duration_minutes == 85

    def test_isbm_window(self, signoff: SafetySignOff):
        w = signoff.get_window("WIN-02")
        assert w.node_id == "isbm-01"
        assert w.duration_minutes == 75

    def test_floor_window(self, signoff: SafetySignOff):
        w = signoff.get_window("WIN-03")
        assert w.node_id == "floor"
        assert w.safety_officer_required is False

    def test_no_window_requires_production_stop(self, signoff: SafetySignOff):
        for w in signoff.windows:
            assert w.requires_production_stop is False

    def test_confirm_window(self, signoff: SafetySignOff):
        w = signoff.confirm_window("WIN-01")
        assert w.status == WindowStatus.CONFIRMED

    def test_all_windows_confirmed(self, signoff: SafetySignOff):
        assert signoff.all_windows_confirmed is False
        for w in signoff.windows:
            signoff.confirm_window(w.window_id)
        assert signoff.all_windows_confirmed is True

    def test_unknown_window_raises(self, signoff: SafetySignOff):
        with pytest.raises(KeyError):
            signoff.get_window("WIN-UNKNOWN")


# ── TestApprovalLifecycle ────────────────────────────────────────────────────


class TestApprovalLifecycle:

    def test_approve(self, signoff: SafetySignOff):
        signoff.approve("Mr. Safety Officer", "All checks passed")
        assert signoff.is_approved is True
        assert signoff.status == SignOffStatus.APPROVED
        assert signoff.sign_off_date is not None

    def test_reject(self, signoff: SafetySignOff):
        signoff.reject("Mr. Safety Officer", "Need more controls")
        assert signoff.status == SignOffStatus.REJECTED
        assert signoff.is_approved is False


# ── TestPrintable ────────────────────────────────────────────────────────────


class TestPrintable:

    def test_print_document(self, signoff: SafetySignOff):
        md = signoff.print_document()
        assert "# OI-75 Safety / Access Sign-Off Document" in md
        assert "Zero Production Stoppage Constraints" in md
        assert "Hazard Assessments" in md
        assert "PPE Requirements" in md
        assert "Install Windows" in md

    def test_contains_all_hazards(self, signoff: SafetySignOff):
        md = signoff.print_document()
        for h in signoff.hazards:
            assert h.hazard_id in md

    def test_contains_all_windows(self, signoff: SafetySignOff):
        md = signoff.print_document()
        for w in signoff.windows:
            assert w.window_id in md


# ── TestSerialization ────────────────────────────────────────────────────────


class TestSerialization:

    def test_to_dict(self, signoff: SafetySignOff):
        d = signoff.to_dict()
        assert d["hazard_count"] == 8
        assert d["zero_production_stoppage"] is True
        assert d["all_risks_low"] is True

    def test_json_serializable(self, signoff: SafetySignOff):
        d = signoff.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["document"] == "OI-75 Safety / Access Sign-Off"
        assert len(json_str) > 2000


# ── TestReportGeneration ─────────────────────────────────────────────────────


class TestReportGeneration:

    def test_generate_report(self):
        report = generate_safety_report()
        assert report["report"] == "OI-75 Safety / Access Sign-Off Report"

    def test_acceptance_criteria(self):
        report = generate_safety_report()
        ac = report["acceptance_criteria"]
        assert ac["written_sign_off_captured"] is True
        assert ac["install_window_scheduled"] is True
        assert ac["zero_production_stoppage_documented"] is True

    def test_summary(self):
        report = generate_safety_report()
        s = report["summary"]
        assert s["hazards_assessed"] == 8
        assert s["all_risks_reduced_to_low"] is True
        assert s["zero_production_stoppage"] is True
        assert s["zero_downtime_constraints"] == 8

    def test_json_serializable(self):
        report = generate_safety_report()
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["report"] == "OI-75 Safety / Access Sign-Off Report"
