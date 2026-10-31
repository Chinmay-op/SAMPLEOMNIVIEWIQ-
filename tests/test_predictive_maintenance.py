"""
tests/test_predictive_maintenance.py — Tests for LLD Predictive Maintenance Facade
===================================================================================

Validates:
- DEMO_PRIORS structure and asset-agnostic definitions
- run_stage_a_pipeline invocation and BatchResult output
- predict_maintenance_risk via LLD signature (HealthIndexResult)
- predict_maintenance_risk via PRD §6 signature (machine_id, latest_row)
- Event envelope compliance with Layer 3 contract
"""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest

from omniview.rules.predictive_maintenance import (
    run_stage_a_pipeline,
    predict_maintenance_risk,
    evaluate_cooling_malfunction,
    CoolingMalfunctionEvent,
    DEMO_PRIORS,
    BatchResult,
    HealthIndexResult,
    PriorStore,
    compute_health_index,
)


def _generate_synthetic_electrical_readings(days: int = 15, current_drift: float = 0.0) -> list[dict]:
    """Generate minimal daily electrical readings for testing."""
    readings = []
    base_time = datetime.datetime(2026, 8, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)

    for d in range(days):
        day_time = base_time + datetime.timedelta(days=d)
        current = 205.0 + (d * current_drift)
        readings.append({
            "timestamp": day_time.isoformat(),
            "time": day_time.isoformat(),
            "data": {
                "current_a_avg": current,
                "current_a_l1": current,
                "current_a_l2": current,
                "current_a_l3": current,
                "voltage_thd_percent": 2.5,
                "current_thd_percent": 11.0,
                "power_factor_avg": 0.95,
                "current_a_neutral": 0.3,
                "frequency_hz": 50.0,
            },
        })
    return readings


# ── Tests for DEMO_PRIORS ───────────────────────────────────────────────────


def test_demo_priors_structure():
    """Verify DEMO_PRIORS is present, labeled, and contains core signal priors."""
    assert isinstance(DEMO_PRIORS, dict)
    assert len(DEMO_PRIORS) >= 8

    core_signals = [
        "current_a_avg",
        "voltage_thd_percent",
        "current_thd_percent",
        "power_factor_avg",
        "phase_imbalance_percent",
        "z_rms_velocity_mm_sec",
    ]
    for sig in core_signals:
        assert sig in DEMO_PRIORS
        prior = DEMO_PRIORS[sig]
        assert "mean" in prior
        assert "std" in prior
        assert "direction" in prior
        assert prior["std"] > 0


# ── Tests for run_stage_a_pipeline ──────────────────────────────────────────


def test_run_stage_a_pipeline_empty():
    """Running pipeline with empty readings returns clean BatchResult without error."""
    result = run_stage_a_pipeline(readings=[], machine_id="test-machine")
    assert isinstance(result, BatchResult)
    assert result.machine_id == "test-machine"
    assert len(result.daily_rows) == 0


def test_run_stage_a_pipeline_synthetic_batch():
    """Running pipeline over synthetic readings computes daily rows, slopes, and HI."""
    readings = _generate_synthetic_electrical_readings(days=14, current_drift=0.1)
    result = run_stage_a_pipeline(
        readings=readings,
        machine_id="isbm-main-feed",
        synthetic=True,
    )

    assert isinstance(result, BatchResult)
    assert result.machine_id == "isbm-main-feed"
    assert len(result.daily_rows) == 14
    assert len(result.slopes) == 14
    # HI series begins after 7-day warmup (14 - 7 + 1 = 8 observations)
    assert len(result.hi_series) == 8

    latest = result.latest_hi
    assert latest is not None
    assert 0.0 <= latest.health_index <= 100.0
    assert latest.risk_tier in ("low", "medium", "high")


# ── Tests for predict_maintenance_risk ──────────────────────────────────────


def test_predict_maintenance_risk_lld_contract():
    """Verify LLD signature: predict_maintenance_risk(hi_result, ...)."""
    hi = HealthIndexResult(
        machine_id="isbm-main-feed",
        date="2026-08-15",
        health_index=35.0,
        risk_tier="high",
        confidence_stage="stage_a_unsupervised",
        avg_z=5.41,
        signal_count=5,
    )

    event = predict_maintenance_risk(hi_result=hi, synthetic=True)

    assert isinstance(event, dict)
    assert event["event_type"] == "maintenance_risk"
    assert event["machine_id"] == "isbm-main-feed"
    assert event["severity"] == "critical"
    assert event["synthetic"] is True
    assert event["confidence_stage"] == "stage_a_unsupervised"

    payload = event["payload"]
    assert payload["health_index"] == 35.0
    assert payload["risk_tier"] == "high"


def test_predict_maintenance_risk_prd_contract():
    """Verify PRD §6 signature: predict_maintenance_risk(machine_id, latest_row, ...)."""
    latest_row = {
        "date": "2026-08-15",
        "current_a_avg_slope_7d": 15.0,  # high drift
        "power_factor_avg_slope_7d": -0.05,
    }

    event = predict_maintenance_risk(
        hi_result="isbm-main-feed",
        latest_row=latest_row,
        synthetic=True,
    )

    assert isinstance(event, dict)
    assert event["event_type"] == "maintenance_risk"
    assert event["machine_id"] == "isbm-main-feed"
    assert event["synthetic"] is True
    assert "payload" in event
    assert "health_index" in event["payload"]


# ── Tests for cooling_malfunction (OI-145 / LLD §3 line 65) ─────────────────


def test_cooling_malfunction_synthetic_pair_of_rows():
    """LLD §3 line 65: emit cooling_malfunction on a synthetic pair of rows."""
    electrical_row = {
        "device_id": "isbm-main-feed",
        "timestamp": "2026-08-15T12:00:00+00:00",
        "data": {
            "active_power_kw_total": 68.5,  # High electrical energy (> 50 kW threshold)
            "current_a_avg": 210.0,
        },
    }
    cooling_row = {
        "device_id": "isbm-main-feed",
        "timestamp": "2026-08-15T12:00:00+00:00",
        "data": {
            "present_value_pv_c": 55.0,  # Low barrel/cooling temp (< 100 °C threshold)
        },
    }

    event = evaluate_cooling_malfunction(electrical_row, cooling_row)

    assert event is not None
    assert isinstance(event, CoolingMalfunctionEvent)
    assert event.event_type == "cooling_malfunction"
    assert event.device_id == "isbm-main-feed"
    assert event.severity == "warning"
    assert event.active_power_kw == 68.5
    assert event.cooling_temp_c == 55.0
    assert event.stop_machine is False
    assert event.action_suggestion == "service_or_inspect"

    event_dict = event.to_dict()
    assert event_dict["event_type"] == "cooling_malfunction"
    assert "event_id" in event_dict
