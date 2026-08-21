"""
Tests for OI-76 — Non-Invasive Install Procedure
===================================================

Self-contained unit tests. No DB, no MQTT, no external deps.
Verifies:
  - Install procedure structure and constraints
  - Compressor and ISBM node plans
  - Zero-downtime guarantee
  - Install verifier logic
  - Report generation
  - Step lifecycle (mark completed / verified)
  - Pre-install checklist
"""

from __future__ import annotations

import json

import pytest

from omniview.edge.install_procedure import (
    FullVerificationResult,
    InstallMethod,
    InstallProcedure,
    InstallStatus,
    InstallStep,
    InstallVerifier,
    NodeInstallPlan,
    SafetyCategory,
    VerificationResult,
    generate_install_report,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def procedure() -> InstallProcedure:
    """Fresh install procedure."""
    return InstallProcedure()


@pytest.fixture
def approved_procedure() -> InstallProcedure:
    """Procedure with safety and BOM approvals."""
    return InstallProcedure(safety_approved=True, bom_confirmed=True)


@pytest.fixture
def verifier(procedure: InstallProcedure) -> InstallVerifier:
    """Verifier with default procedure."""
    return InstallVerifier(procedure)


# ── TestInstallStep ──────────────────────────────────────────────────────────


class TestInstallStep:
    """Tests for individual install step data class."""

    def test_create_valid_step(self):
        step = InstallStep(
            step_id="TEST-01",
            description="Test step",
            method=InstallMethod.SNAP_ON_CT,
            safety_category=SafetyCategory.LOW_RISK,
            sensor_type="electrical",
            device_id="test-device",
            hardware="Test Hardware",
            location="Test location",
            duration_minutes=10,
        )
        assert step.step_id == "TEST-01"
        assert step.requires_power_off is False
        assert step.status == InstallStatus.NOT_STARTED

    def test_power_off_raises_error(self):
        """Non-invasive constraint: no step may require power off."""
        with pytest.raises(ValueError, match="non-invasive install constraint"):
            InstallStep(
                step_id="BAD-01",
                description="Bad step",
                method=InstallMethod.SNAP_ON_CT,
                safety_category=SafetyCategory.HIGH_RISK,
                sensor_type="electrical",
                device_id="bad-device",
                hardware="Bad Hardware",
                location="Bad location",
                duration_minutes=10,
                requires_power_off=True,
            )

    def test_to_dict_complete(self):
        step = InstallStep(
            step_id="TEST-01",
            description="Test",
            method=InstallMethod.MAGNETIC_MOUNT,
            safety_category=SafetyCategory.LOW_RISK,
            sensor_type="vibration",
            device_id="test-vib",
            hardware="Test Vib",
            location="Test",
            duration_minutes=5,
            ppe_required=["safety glasses"],
            verification_check="Check reading",
        )
        d = step.to_dict()
        assert d["step_id"] == "TEST-01"
        assert d["method"] == "magnetic_mount"
        assert d["safety_category"] == "low_risk"
        assert d["requires_power_off"] is False
        assert d["ppe_required"] == ["safety glasses"]
        assert d["status"] == "not_started"

    def test_all_install_methods_are_non_invasive(self):
        """Every InstallMethod must be a non-invasive technique."""
        non_invasive_methods = {
            "snap_on_ct", "panel_door_mount", "magnetic_mount",
            "gauge_port_tap", "surface_mount", "wall_mount", "proximity_mount",
        }
        for method in InstallMethod:
            assert method.value in non_invasive_methods, (
                f"InstallMethod {method.value} is not recognized as non-invasive"
            )


# ── TestNodeInstallPlan ──────────────────────────────────────────────────────


class TestNodeInstallPlan:
    """Tests for node-level install plan."""

    def test_compressor_plan_has_steps(self, procedure: InstallProcedure):
        plan = procedure.compressor_plan
        assert len(plan.steps) >= 5
        assert plan.node_id == "compressor-01"

    def test_isbm_plan_has_steps(self, procedure: InstallProcedure):
        plan = procedure.isbm_plan
        assert len(plan.steps) >= 4
        assert plan.node_id == "isbm-01"

    def test_total_duration_positive(self, procedure: InstallProcedure):
        for plan in procedure.node_plans:
            assert plan.total_duration_minutes > 0

    def test_no_power_off_on_any_node(self, procedure: InstallProcedure):
        """Acceptance criterion: zero production stoppage."""
        for plan in procedure.node_plans:
            assert not plan.requires_any_power_off

    def test_initially_not_completed(self, procedure: InstallProcedure):
        for plan in procedure.node_plans:
            assert not plan.all_steps_completed

    def test_safety_flags(self, approved_procedure: InstallProcedure):
        for plan in approved_procedure.node_plans:
            assert plan.safety_approved is True
            assert plan.bom_confirmed is True

    def test_to_dict_keys(self, procedure: InstallProcedure):
        d = procedure.compressor_plan.to_dict()
        assert "node_id" in d
        assert "steps" in d
        assert "total_duration_minutes" in d
        assert "requires_any_power_off" in d
        assert d["requires_any_power_off"] is False


# ── TestInstallProcedure ─────────────────────────────────────────────────────


class TestInstallProcedure:
    """Tests for the master install procedure."""

    def test_two_nodes(self, procedure: InstallProcedure):
        assert len(procedure.node_plans) == 2

    def test_node_ids(self, procedure: InstallProcedure):
        ids = {p.node_id for p in procedure.node_plans}
        assert ids == {"compressor-01", "isbm-01"}

    def test_total_step_count(self, procedure: InstallProcedure):
        assert procedure.total_step_count >= 10  # 7 comp + 5 isbm = 12

    def test_total_duration(self, procedure: InstallProcedure):
        # Should be well under a day for non-invasive install
        assert 30 <= procedure.total_duration_minutes <= 480

    def test_zero_downtime_property(self, procedure: InstallProcedure):
        assert procedure.zero_downtime is True

    def test_not_yet_instrumented(self, procedure: InstallProcedure):
        assert procedure.all_nodes_instrumented is False

    def test_get_all_steps_returns_flat_list(self, procedure: InstallProcedure):
        all_steps = procedure.get_all_steps()
        assert isinstance(all_steps, list)
        assert all(isinstance(s, InstallStep) for s in all_steps)
        assert len(all_steps) == procedure.total_step_count

    def test_pre_install_checklist(self, procedure: InstallProcedure):
        checks = procedure.get_pre_install_checklist()
        assert len(checks) >= 8
        # Must reference OI-73 (BOM) and OI-75 (safety)
        jira_refs = {c["jira"] for c in checks}
        assert "OI-73" in jira_refs
        assert "OI-75" in jira_refs

    def test_to_dict_json_serializable(self, procedure: InstallProcedure):
        d = procedure.to_dict()
        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert len(json_str) > 100
        parsed = json.loads(json_str)
        assert parsed["zero_downtime"] is True


# ── TestStepLifecycle ────────────────────────────────────────────────────────


class TestStepLifecycle:
    """Tests for marking steps completed and verified."""

    def test_mark_step_completed(self, procedure: InstallProcedure):
        step = procedure.mark_step_completed("COMP-01")
        assert step.status == InstallStatus.COMPLETED

    def test_mark_step_verified(self, procedure: InstallProcedure):
        step = procedure.mark_step_verified("COMP-01")
        assert step.status == InstallStatus.VERIFIED

    def test_mark_unknown_step_raises(self, procedure: InstallProcedure):
        with pytest.raises(KeyError, match="UNKNOWN"):
            procedure.mark_step_completed("UNKNOWN-99")

    def test_all_completed_after_marking(self, procedure: InstallProcedure):
        for step in procedure.get_all_steps():
            procedure.mark_step_completed(step.step_id)
        assert procedure.all_nodes_instrumented is True

    def test_get_steps_by_status(self, procedure: InstallProcedure):
        # Initially all not started
        not_started = procedure.get_steps_by_status(InstallStatus.NOT_STARTED)
        assert len(not_started) == procedure.total_step_count

        # Mark one
        procedure.mark_step_completed("COMP-01")
        not_started = procedure.get_steps_by_status(InstallStatus.NOT_STARTED)
        completed = procedure.get_steps_by_status(InstallStatus.COMPLETED)
        assert len(completed) == 1
        assert len(not_started) == procedure.total_step_count - 1


# ── TestInstallVerifier ──────────────────────────────────────────────────────


class TestInstallVerifier:
    """Tests for the install verification logic."""

    def test_verify_compressor_passes(self, verifier: InstallVerifier):
        result = verifier.verify_node("compressor-01")
        assert result.passed is True
        assert result.node_id == "compressor-01"

    def test_verify_isbm_passes(self, verifier: InstallVerifier):
        result = verifier.verify_node("isbm-01")
        assert result.passed is True
        assert result.node_id == "isbm-01"

    def test_verify_all_passes(self, verifier: InstallVerifier):
        result = verifier.verify_all()
        assert result.all_passed is True
        assert result.zero_downtime_confirmed is True
        assert len(result.node_results) == 2

    def test_expected_devices_compressor(self, verifier: InstallVerifier):
        expected = verifier.EXPECTED_DEVICES["compressor-01"]
        assert "pune-comp-mfm384" in expected
        assert "pune-comp-vib01" in expected
        assert "pune-comp-wika01" in expected

    def test_expected_devices_isbm(self, verifier: InstallVerifier):
        expected = verifier.EXPECTED_DEVICES["isbm-01"]
        assert "pune-isbm-mfm384" in expected
        assert "pune-isbm-therm01" in expected
        assert "pune-isbm-stroke01" in expected

    def test_expected_sensor_types_compressor(self, verifier: InstallVerifier):
        types = verifier.EXPECTED_SENSOR_TYPES["compressor-01"]
        assert "electrical" in types
        assert "vibration" in types
        assert "pressure" in types

    def test_expected_sensor_types_isbm(self, verifier: InstallVerifier):
        types = verifier.EXPECTED_SENSOR_TYPES["isbm-01"]
        assert "electrical" in types
        assert "thermal" in types
        assert "stroke" in types

    def test_verification_result_serializable(self, verifier: InstallVerifier):
        result = verifier.verify_all()
        d = result.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["all_passed"] is True
        assert parsed["zero_downtime_confirmed"] is True

    def test_each_check_has_passed_key(self, verifier: InstallVerifier):
        result = verifier.verify_node("compressor-01")
        for check in result.checks:
            assert "passed" in check
            assert "check" in check


# ── TestInstallChecklist ─────────────────────────────────────────────────────


class TestInstallChecklist:
    """Tests for the printable checklist output."""

    def test_checklist_markdown(self, procedure: InstallProcedure):
        md = procedure.print_checklist()
        assert "# OI-76 Non-Invasive Install Checklist" in md
        assert "Pre-Install Prerequisites" in md
        assert "COMP-01" in md
        assert "ISBM-01" in md

    def test_checklist_contains_all_steps(self, procedure: InstallProcedure):
        md = procedure.print_checklist()
        for step in procedure.get_all_steps():
            assert step.step_id in md

    def test_checklist_shows_completed_steps(self, procedure: InstallProcedure):
        procedure.mark_step_completed("COMP-01")
        md = procedure.print_checklist()
        assert "[x] **COMP-01**" in md

    def test_checklist_includes_ppe(self, procedure: InstallProcedure):
        md = procedure.print_checklist()
        assert "PPE:" in md

    def test_checklist_includes_verification(self, procedure: InstallProcedure):
        md = procedure.print_checklist()
        assert "Verify:" in md


# ── TestReportGeneration ─────────────────────────────────────────────────────


class TestReportGeneration:
    """Tests for the install report generator."""

    def test_generate_report(self):
        report = generate_install_report()
        assert report["report"] == "OI-76 Non-Invasive Install Report"
        assert "acceptance_criteria" in report
        assert "summary" in report
        assert "verification" in report
        assert "procedure" in report

    def test_acceptance_criteria_in_report(self):
        report = generate_install_report()
        ac = report["acceptance_criteria"]
        # Zero downtime is always true (enforced by constructor)
        assert ac["zero_production_stoppage"] is True

    def test_summary_values(self):
        report = generate_install_report()
        summary = report["summary"]
        assert summary["total_nodes"] == 2
        assert summary["total_steps"] >= 9
        assert summary["total_devices"] >= 6
        assert summary["total_duration_minutes"] > 0

    def test_report_json_serializable(self):
        report = generate_install_report()
        json_str = json.dumps(report)
        assert len(json_str) > 500
        parsed = json.loads(json_str)
        assert parsed["report"] == "OI-76 Non-Invasive Install Report"

    def test_verification_in_report(self):
        report = generate_install_report()
        v = report["verification"]
        assert v["all_passed"] is True
        assert v["zero_downtime_confirmed"] is True
        assert len(v["nodes"]) == 2


# ── TestCompressorNodeDetails ────────────────────────────────────────────────


class TestCompressorNodeDetails:
    """Verify compressor-01 install steps match PRD/architecture specs."""

    def test_has_mfm384_meter_step(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        mfm_steps = [s for s in steps if "MFM384" in s.hardware]
        assert len(mfm_steps) >= 1

    def test_has_ct_clamp_step(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        ct_steps = [s for s in steps if s.method == InstallMethod.SNAP_ON_CT]
        assert len(ct_steps) >= 1

    def test_has_vibration_sensor_step(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        vib_steps = [s for s in steps if s.sensor_type == "vibration"]
        assert len(vib_steps) >= 1

    def test_has_pressure_sensor_step(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        prs_steps = [s for s in steps if s.sensor_type == "pressure"]
        assert len(prs_steps) >= 1

    def test_vibration_step_mentions_iso10816(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        vib_step = next(s for s in steps if s.sensor_type == "vibration")
        assert "10816" in vib_step.notes

    def test_pressure_step_uses_gauge_port(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        prs_step = next(s for s in steps if s.sensor_type == "pressure")
        assert prs_step.method == InstallMethod.GAUGE_PORT_TAP

    def test_has_modbus_bus_verification_step(self, procedure: InstallProcedure):
        steps = procedure.compressor_plan.steps
        bus_steps = [s for s in steps if "RS-485" in s.description]
        assert len(bus_steps) >= 1


# ── TestISBMNodeDetails ──────────────────────────────────────────────────────


class TestISBMNodeDetails:
    """Verify isbm-01 install steps match PRD/architecture specs."""

    def test_has_mfm384_meter_step(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        mfm_steps = [s for s in steps if "MFM384" in s.hardware]
        assert len(mfm_steps) >= 1

    def test_has_ct_clamp_step(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        ct_steps = [s for s in steps if s.method == InstallMethod.SNAP_ON_CT]
        assert len(ct_steps) >= 1

    def test_has_thermal_probe_step(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        therm_steps = [s for s in steps if s.sensor_type == "thermal"]
        assert len(therm_steps) >= 1

    def test_has_stroke_counter_step(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        stroke_steps = [s for s in steps if s.sensor_type == "stroke"]
        assert len(stroke_steps) >= 1

    def test_thermal_step_mentions_lazy_idle(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        therm_step = next(s for s in steps if s.sensor_type == "thermal")
        assert "idle" in therm_step.verification_check.lower()

    def test_stroke_uses_proximity_mount(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        stroke_step = next(s for s in steps if s.sensor_type == "stroke")
        assert stroke_step.method == InstallMethod.PROXIMITY_MOUNT

    def test_has_modbus_bus_verification_step(self, procedure: InstallProcedure):
        steps = procedure.isbm_plan.steps
        bus_steps = [s for s in steps if "RS-485" in s.description]
        assert len(bus_steps) >= 1
