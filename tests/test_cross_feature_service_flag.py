"""
tests/test_cross_feature_service_flag.py — Integration & Unit Tests for OI-154
=============================================================================

Validates the Cross-Feature Maintenance Service Flag Attachment:
- LLD Section 3 line 85 and Section 5 line 101.
- Acceptance Criteria 1: Expose get_machine_service_status(machine_id) in predictive_maintenance.py.
- Acceptance Criteria 2: Returns True if machine has an active high-risk tier event or scheduled maintenance log window.
- Acceptance Criteria 3: Feature 3 96-slot demand aggregator checks this flag and excludes machine's labeled share.
- Acceptance Criteria 4: Feature 4 waste_schedule composer verifies the flag before flagging lazy-idle waste.
- Acceptance Criteria 5: Integration test verifying maintenance state suppresses false waste alerts.
"""

from __future__ import annotations

import datetime
from datetime import date, timezone
from pathlib import Path
import pytest

from omniview.rules.predictive_maintenance import (
    MachineServiceRegistry,
    get_machine_service_status,
    set_machine_service_status,
    clear_machine_service_registry,
    predict_maintenance_risk,
    HealthIndexResult,
)
from omniview.predictive.maintenance_log import (
    MaintenanceLogger,
    MaintenanceEvent,
)
from omniview.rules.demand_slots import (
    NUM_SLOTS_PER_DAY,
    MachineRecord,
    SlotDemand,
    DayAheadDemandPlan,
    aggregate_96_slot_demand,
    generate_baseline_campus_slots,
    format_slot_time,
)
from omniview.rules.lazy_idle import (
    LazyIdleDetector,
    LazyIdleEvent,
    evaluate_lazy_idle,
)
from omniview.rules.waste_schedule import (
    WasteSchedule,
    compose_waste_schedule,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure service registry is clean before and after each test."""
    clear_machine_service_registry()
    yield
    clear_machine_service_registry()


# ═════════════════════════════════════════════════════════════════════════
# 1. get_machine_service_status (Acceptance Criteria 1 & 2)
# ═════════════════════════════════════════════════════════════════════════


class TestMachineServiceStatus:
    """Tests for get_machine_service_status and registry state resolution."""

    def test_default_healthy_machine_returns_false(self):
        """Unseen, unflagged machine returns False."""
        assert get_machine_service_status("unknown-machine-99") is False

    def test_high_risk_tier_hi_result_returns_true(self):
        """High-risk tier (or HI < 40) flags machine as under service/maintenance."""
        critical_hi = HealthIndexResult(
            machine_id="isbm-cell-01",
            date="2026-08-20",
            health_index=34.5,
            risk_tier="high",
            confidence_stage="stage_a_unsupervised",
        )
        # Passing hi_result directly
        assert get_machine_service_status("isbm-cell-01", hi_result=critical_hi) is True

        # Recording in registry
        MachineServiceRegistry.get_instance().record_hi(critical_hi)
        assert get_machine_service_status("isbm-cell-01") is True

    def test_medium_and_low_risk_tier_returns_false(self):
        """Medium (HI=55) and Low (HI=92) risk tiers do not flag machine as down for service."""
        med_hi = HealthIndexResult(
            machine_id="comp-01",
            date="2026-08-20",
            health_index=55.0,
            risk_tier="medium",
        )
        low_hi = HealthIndexResult(
            machine_id="comp-02",
            date="2026-08-20",
            health_index=92.0,
            risk_tier="low",
        )
        assert get_machine_service_status("comp-01", hi_result=med_hi) is False
        assert get_machine_service_status("comp-02", hi_result=low_hi) is False

    def test_manual_override_status(self):
        """Manual set_machine_service_status explicitly controls status."""
        machine_id = "blower-05"
        assert get_machine_service_status(machine_id) is False

        set_machine_service_status(machine_id, in_maintenance=True)
        assert get_machine_service_status(machine_id) is True

        set_machine_service_status(machine_id, in_maintenance=False)
        assert get_machine_service_status(machine_id) is False

    def test_maintenance_logger_event_returns_true(self, tmp_path):
        """Active entry in MaintenanceLogger returns True for matching machine and date."""
        log_file = tmp_path / "test_maintenance.jsonl"
        logger_inst = MaintenanceLogger(log_path=log_file)

        today_str = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
        event = MaintenanceEvent(
            machine_id="isbm-main-feed",
            event_date=today_str,
            event_type="repair",
            triggered_by="system_alert",
            component="bearing",
            downtime_hours=8.0,
        )
        logger_inst.log(event)

        # Machine with logged event for today returns True
        assert get_machine_service_status("isbm-main-feed", log_path=log_file) is True

        # Another machine with no log returns False
        assert get_machine_service_status("other-machine", log_path=log_file) is False

    def test_predict_maintenance_risk_automatically_registers_hi(self):
        """Calling predict_maintenance_risk automatically registers critical machines."""
        hi_high = HealthIndexResult(
            machine_id="ext-motor-01",
            date="2026-08-20",
            health_index=32.0,
            risk_tier="high",
        )
        assert get_machine_service_status("ext-motor-01") is False

        # Generate event
        evt = predict_maintenance_risk(hi_high)
        assert evt["event_type"] == "maintenance_risk"

        # Now automatically flagged in service registry
        assert get_machine_service_status("ext-motor-01") is True


# ═════════════════════════════════════════════════════════════════════════
# 2. Feature 3: 96-Slot Demand Aggregator (Acceptance Criteria 3)
# ═════════════════════════════════════════════════════════════════════════


class TestFeature3DemandAggregator:
    """Tests for 96-slot day-ahead demand plan and machine share exclusion."""

    def test_96_slot_call_returns_96_slots_and_carries_synthetic_true(self):
        """LLD §4 line 89: 96-slot call returns 96 slots and carries synthetic: true."""
        plan = aggregate_96_slot_demand()

        assert isinstance(plan, DayAheadDemandPlan)
        assert len(plan.slots) == NUM_SLOTS_PER_DAY
        assert len(plan.slots) == 96
        assert plan.synthetic is True
        assert plan.slots[0].time_label == "00:00"
        assert plan.slots[1].time_label == "00:15"
        assert plan.slots[95].time_label == "23:45"
        assert plan.total_baseline_kwh > 0.0
        assert plan.total_adjusted_kwh > 0.0

    def test_excludes_labeled_share_for_machine_in_maintenance(self):
        """LLD §4 line 85: Drop machine's labeled share from affected slots."""
        # 96 slots of constant 300 kW
        baseline = [300.0] * 96

        m1 = MachineRecord(
            machine_id="isbm-01",
            labeled_share_kw=80.0,
            name="Main ISBM Production Line",
        )
        m2 = MachineRecord(
            machine_id="comp-01",
            labeled_share_kw=50.0,
            name="High-Pressure Compressor",
        )

        # isbm-01 is flagged for maintenance; comp-01 is healthy
        set_machine_service_status("isbm-01", in_maintenance=True)
        set_machine_service_status("comp-01", in_maintenance=False)

        plan = aggregate_96_slot_demand(
            baseline_slots=baseline,
            machine_records=[m1, m2],
        )

        assert "isbm-01" in plan.machines_down_for_service
        assert "comp-01" not in plan.machines_down_for_service

        for s in plan.slots:
            assert s.baseline_kw == 300.0
            # 300 kW - 80 kW (isbm-01 dropped) = 220 kW
            assert s.adjusted_kw == 220.0
            assert s.excluded_kw == 80.0
            assert "isbm-01" in s.machines_in_maintenance
            assert "comp-01" not in s.machines_in_maintenance

        # Total curtailed energy across 24h = 80 kW * 24h = 1920 kWh
        assert plan.total_curtailed_kwh == pytest.approx(1920.0, rel=1e-2)

    def test_partial_affected_slots_curtailment(self):
        """Curtailed only during scheduled window slots (e.g. shift 2, slots 32..64)."""
        baseline = [200.0] * 96
        scheduled_slots = list(range(32, 64))  # 08:00 to 16:00
        m_partial = MachineRecord(
            machine_id="pump-03",
            labeled_share_kw=40.0,
            affected_slots=scheduled_slots,
        )

        set_machine_service_status("pump-03", in_maintenance=True)

        plan = aggregate_96_slot_demand(
            baseline_slots=baseline,
            machine_records=[m_partial],
        )

        # Before slot 32: untouched
        for s in plan.slots[:32]:
            assert s.adjusted_kw == 200.0
            assert s.excluded_kw == 0.0

        # Slots 32..63: 40 kW deducted (160 kW)
        for s in plan.slots[32:64]:
            assert s.adjusted_kw == 160.0
            assert s.excluded_kw == 40.0
            assert "pump-03" in s.machines_in_maintenance

        # Slots 64..95: untouched
        for s in plan.slots[64:]:
            assert s.adjusted_kw == 200.0
            assert s.excluded_kw == 0.0

    def test_healthy_machines_do_not_alter_baseline(self):
        """When all machines are healthy, adjusted demand equals baseline."""
        baseline = [250.0] * 96
        m = MachineRecord(machine_id="healthy-line", labeled_share_kw=60.0)
        set_machine_service_status("healthy-line", in_maintenance=False)

        plan = aggregate_96_slot_demand(baseline_slots=baseline, machine_records=[m])
        assert len(plan.machines_down_for_service) == 0
        assert plan.total_curtailed_kwh == 0.0
        assert plan.total_adjusted_kwh == plan.total_baseline_kwh


# ═════════════════════════════════════════════════════════════════════════
# 3. Feature 4: Lazy-Idle Suppression (Acceptance Criteria 4 & 5)
# ═════════════════════════════════════════════════════════════════════════


class TestFeature4LazyIdleMaintenanceSuppression:
    """Tests that maintenance state suppresses false lazy-idle waste alerts."""

    def test_lazy_idle_detector_suppresses_alert_when_machine_in_maintenance(self):
        """Machine hot + idle sustained > 15 min DOES NOT alert if in maintenance."""
        detector = LazyIdleDetector(
            temp_threshold_c=25.0,
            current_threshold_a=0.65,
            duration_min=15,
            check_maintenance=True,
        )
        base_time = datetime.datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        machine_id = "isbm-line-01"

        # Mark machine as undergoing maintenance
        set_machine_service_status(machine_id, in_maintenance=True)

        # Tick 1: condition starts at t=0
        r1 = detector.evaluate({
            "device_id": machine_id,
            "timestamp": base_time.isoformat(),
            "data": {"zone_temp_c": 60.0, "current_a": 0.20},  # Hot + Idle
        })
        assert r1 is None

        # Tick 2: 20 minutes later (duration exceeded)
        r2 = detector.evaluate({
            "device_id": machine_id,
            "timestamp": (base_time + datetime.timedelta(minutes=20)).isoformat(),
            "data": {"zone_temp_c": 62.0, "current_a": 0.18},
        })
        # MUST BE SUPPRESSED: technicians are working on machine heaters/pumps
        assert r2 is None

    def test_lazy_idle_detector_fires_alert_when_machine_healthy(self):
        """Machine hot + idle sustained > 15 min FIRES alert if machine is healthy."""
        detector = LazyIdleDetector(
            temp_threshold_c=25.0,
            current_threshold_a=0.65,
            duration_min=15,
            check_maintenance=True,
        )
        base_time = datetime.datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        machine_id = "isbm-line-healthy"

        # Explicitly healthy
        set_machine_service_status(machine_id, in_maintenance=False)

        # Feed 20 minutes of continuous telemetry at 1-min cadence (20 samples)
        event = None
        for i in range(20):
            ts = base_time + datetime.timedelta(minutes=i)
            res = detector.evaluate({
                "device_id": machine_id,
                "timestamp": ts.isoformat(),
                "data": {"zone_temp_c": 56.0, "current_a": 0.22},
            })
            if res is not None:
                event = res

        assert event is not None
        assert isinstance(event, LazyIdleEvent)
        assert event.event_type == "lazy_idle"
        assert event.device_id == machine_id

    def test_evaluate_lazy_idle_standalone_function(self):
        """evaluate_lazy_idle pure function suppresses when in maintenance."""
        sample = {
            "device_id": "isbm-test",
            "timestamp": "2026-08-20T10:00:00+00:00",
            "data": {
                "zone_temp_c": 45.0,
                "current_a": 0.15,
                "duration_min": 25.0,
            },
        }

        # Under maintenance -> None
        set_machine_service_status("isbm-test", in_maintenance=True)
        assert evaluate_lazy_idle(sample) is None

        # Not under maintenance -> LazyIdleEvent
        set_machine_service_status("isbm-test", in_maintenance=False)
        evt = evaluate_lazy_idle(sample)
        assert evt is not None
        assert evt.device_id == "isbm-test"


# ═════════════════════════════════════════════════════════════════════════
# 4. Feature 4: Waste Schedule Composer (Acceptance Criteria 4 & 5)
# ═════════════════════════════════════════════════════════════════════════


class TestFeature4WasteSchedule:
    """Tests for compose_waste_schedule and service flag verification."""

    def test_waste_schedule_excludes_machine_in_maintenance(self):
        """Machine under maintenance: waste_where='none' and waste_identified=False."""
        machine_id = "isbm-scheduled-repair"
        set_machine_service_status(machine_id, in_maintenance=True)

        mock_lazy_events = [
            {"device_id": machine_id, "timestamp": datetime.datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)}
        ]

        schedule = compose_waste_schedule(
            machine_id=machine_id,
            lazy_idle_events=mock_lazy_events,
            stroke_count=120,
        )

        assert isinstance(schedule, WasteSchedule)
        assert schedule.machine_id == machine_id
        assert schedule.waste_where == "none"
        assert schedule.waste_identified is False
        assert schedule.details["maintenance_suppressed"] is True
        assert schedule.synthetic is True

    def test_waste_schedule_flags_lazy_idle_for_healthy_machine(self):
        """Healthy machine with lazy idle events: flags waste_where='lazy_idle'."""
        machine_id = "isbm-unmonitored-idle"
        set_machine_service_status(machine_id, in_maintenance=False)

        mock_event = LazyIdleEvent(
            device_id=machine_id,
            timestamp=datetime.datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc),
            zone_temp_c=50.0,
            current_a=0.3,
            duration_min=22.0,
        )

        schedule = compose_waste_schedule(
            machine_id=machine_id,
            lazy_idle_events=[mock_event],
            stroke_count=450,
        )

        assert schedule.waste_where == "lazy_idle"
        assert schedule.waste_identified is True
        assert schedule.stop_hour == 15
        assert schedule.production_rate == 450.0


# ═════════════════════════════════════════════════════════════════════════
# 5. Full End-to-End Cross-Feature Integration Flow
# ═════════════════════════════════════════════════════════════════════════


class TestCrossFeatureEndToEndFlow:
    """Full end-to-end integration test connecting Feature 2 -> Feature 3 -> Feature 4."""

    def test_full_pipeline_flow(self):
        """Simulates machine degradation:
        1. Feature 2 Health Index drops to critical tier.
        2. Feature 2 emits maintenance_risk event and sets service flag.
        3. Feature 3 96-slot day-ahead plan drops machine load share.
        4. Feature 4 suppresses false lazy-idle waste alerts during servicing.
        5. Machine recovery restores full capacity and resumes waste monitoring.
        """
        machine_id = "isbm-main-line"
        rated_share_kw = 75.0

        # Step 1 & 2: Feature 2 evaluates degrading machine
        critical_hi = HealthIndexResult(
            machine_id=machine_id,
            date="2026-08-20",
            health_index=31.2,
            risk_tier="high",
            confidence_stage="stage_a_unsupervised",
            avg_z=5.73,
        )
        event = predict_maintenance_risk(critical_hi)
        assert event["severity"] == "critical"

        # Check service status is now automatically True
        assert get_machine_service_status(machine_id) is True

        # Step 3: Feature 3 aggregates 96-slot demand
        baseline_slots = [400.0] * 96
        machine_rec = MachineRecord(machine_id=machine_id, labeled_share_kw=rated_share_kw)

        demand_plan = aggregate_96_slot_demand(
            baseline_slots=baseline_slots,
            machine_records=[machine_rec],
        )

        assert machine_id in demand_plan.machines_down_for_service
        # Demand reduced by 75 kW across all 96 slots
        for s in demand_plan.slots:
            assert s.adjusted_kw == 325.0
            assert s.excluded_kw == 75.0

        # Step 4: Feature 4 Lazy-Idle Detector processes idle reading
        detector = LazyIdleDetector(duration_min=15, check_maintenance=True)
        base_time = datetime.datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

        # Condition hot + idle for 20 minutes while in maintenance
        idle_result = None
        for i in range(20):
            res = detector.evaluate({
                "device_id": machine_id,
                "timestamp": (base_time + datetime.timedelta(minutes=i)).isoformat(),
                "data": {"zone_temp_c": 70.0, "current_a": 0.1},
            })
            if res is not None:
                idle_result = res
        # Must be suppressed!
        assert idle_result is None

        # Step 5: Feature 4 Waste Schedule composer
        schedule = compose_waste_schedule(
            machine_id=machine_id,
            demand_plan=demand_plan,
            lazy_idle_events=[idle_result] if idle_result else [],
        )
        assert schedule.waste_where == "none"
        assert schedule.waste_identified is False
        assert schedule.details["maintenance_suppressed"] is True

        # Step 6: Technicians finish repairs -> Machine restored to service
        set_machine_service_status(machine_id, in_maintenance=False)
        assert get_machine_service_status(machine_id) is False

        # Feature 3 restores machine capacity
        restored_plan = aggregate_96_slot_demand(
            baseline_slots=baseline_slots,
            machine_records=[machine_rec],
        )
        assert machine_id not in restored_plan.machines_down_for_service
        assert restored_plan.slots[0].adjusted_kw == 400.0

        # Feature 4 resumes normal alert monitoring
        detector.reset()
        active_idle_event = None
        for i in range(20):
            res = detector.evaluate({
                "device_id": machine_id,
                "timestamp": (base_time + datetime.timedelta(minutes=i)).isoformat(),
                "data": {"zone_temp_c": 70.0, "current_a": 0.1},
            })
            if res is not None:
                active_idle_event = res

        assert active_idle_event is not None
        assert active_idle_event.event_type == "lazy_idle"
