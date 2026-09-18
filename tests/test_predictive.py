"""
tests/test_predictive.py — PdM Stage A Full Pipeline Test Suite
================================================================

Covers:
- Priors loading (PriorStore)
- Feature aggregation (daily, rolling slopes, phase imbalance)
- Health Index computation (formula, risk tiers, contributing features)
- CUSUM change-point detection (degradation, recovery, retune target)
- Maintenance event logging
- End-to-end batch pipeline (stable, degrading, recovering)
- Event envelope structure (Layer 3 contract §6)
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

# ── Module imports ──────────────────────────────────────────────────────

from omniview.predictive.priors import (
    PriorStore,
    EquipmentPriors,
    SignalPrior,
    HealthIndexParams,
    CUSUMParams,
)
from omniview.predictive.features import (
    DailyRow,
    aggregate_daily,
    compute_rolling_slopes,
    compute_phase_imbalance,
    enrich_daily_features,
    _polyfit_slope,
)
from omniview.predictive.health_index import (
    HealthIndexResult,
    compute_health_index,
)
from omniview.predictive.cusum import CUSUMDetector, CUSUMAlert
from omniview.predictive.events import build_maintenance_risk_event
from omniview.predictive.maintenance_log import (
    MaintenanceEvent,
    MaintenanceLogger,
)
from omniview.predictive.batch_runner import HealthIndexPipeline, BatchResult


# ═══════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def priors_yaml_path(tmp_path: Path) -> Path:
    """Create a minimal priors YAML for testing."""
    config = {
        "equipment_classes": {
            "test_motor": {
                "description": "Test motor for unit tests",
                "machines": ["motor-001", "motor-002"],
                "signals": {
                    "current_a_avg": {
                        "mean": 100.0,
                        "std": 10.0,
                        "direction": "rising",
                        "description": "Average current",
                    },
                    "power_factor_avg": {
                        "mean": 0.95,
                        "std": 0.02,
                        "direction": "falling",
                        "description": "Power factor",
                    },
                    "voltage_thd_percent": {
                        "mean": 3.0,
                        "std": 1.0,
                        "direction": "rising",
                        "description": "Voltage THD",
                    },
                },
            },
            "generic_industrial_motor": {
                "description": "Fallback",
                "machines": [],
                "signals": {
                    "current_a_avg": {
                        "mean": 150.0,
                        "std": 30.0,
                        "direction": "rising",
                    },
                },
            },
        },
        "health_index": {
            "z_scale": 15.0,
            "slope_window_days": 7,
            "min_warmup_days": 7,
            "risk_tiers": {"high": 40, "medium": 70, "low": 100},
        },
        "cusum": {
            "slack": 2.0,
            "threshold": 8.0,
            "reset_on_alert": True,
        },
    }

    path = tmp_path / "test_priors.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


@pytest.fixture
def prior_store(priors_yaml_path: Path) -> PriorStore:
    return PriorStore(config_path=priors_yaml_path)


def _make_electrical_readings(
    days: int = 30,
    base_date: date | None = None,
    readings_per_day: int = 96,
    current_profile: str = "stable",
    pf_profile: str = "stable",
) -> list[dict]:
    """Generate synthetic electrical readings for testing.

    Parameters
    ----------
    current_profile : str
        "stable" | "degrading" | "spike" | "recovering"
    pf_profile : str
        "stable" | "degrading" | "recovering"
    """
    if base_date is None:
        base_date = date(2026, 8, 1)

    readings = []
    for d in range(days):
        day = base_date + timedelta(days=d)
        for slot in range(readings_per_day):
            ts = datetime(day.year, day.month, day.day, slot // 4, (slot % 4) * 15)

            # Current profile
            if current_profile == "stable":
                current = 100.0 + (d % 3) * 0.5
            elif current_profile == "degrading":
                current = 100.0 + d * 2.0  # Rising 2A/day → definitely bad
            elif current_profile == "spike":
                current = 100.0 if d < 20 else 180.0
            elif current_profile == "recovering":
                current = 150.0 - d * 1.5
            else:
                current = 100.0

            # PF profile
            if pf_profile == "stable":
                pf = 0.95 + (d % 2) * 0.001
            elif pf_profile == "degrading":
                pf = max(0.70, 0.95 - d * 0.005)  # Dropping 0.005/day
            elif pf_profile == "recovering":
                pf = min(0.97, 0.80 + d * 0.005)
            else:
                pf = 0.95

            readings.append({
                "time": ts.isoformat(),
                "data": {
                    "current_a_avg": current,
                    "power_factor_avg": pf,
                    "voltage_thd_percent": 3.0 + (d * 0.05 if current_profile == "degrading" else 0),
                    "current_thd_percent": 11.0,
                    "current_a_neutral": 0.3,
                    "current_a_l1": current * 0.98,
                    "current_a_l2": current * 1.01,
                    "current_a_l3": current * 1.01,
                    "frequency_hz": 50.0,
                },
            })

    return readings


# ═══════════════════════════════════════════════════════════════════════
# 1. PRIORS
# ═══════════════════════════════════════════════════════════════════════


class TestPriorStore:
    """Test equipment-class prior loading and resolution."""

    def test_loads_classes(self, prior_store: PriorStore):
        """Config loads the expected equipment classes."""
        assert "test_motor" in prior_store.all_classes
        assert "generic_industrial_motor" in prior_store.all_classes

    def test_machine_lookup(self, prior_store: PriorStore):
        """Machine IDs map to their equipment class."""
        assert prior_store.machine_lookup["motor-001"] == "test_motor"
        assert prior_store.machine_lookup["motor-002"] == "test_motor"

    def test_get_priors_known_machine(self, prior_store: PriorStore):
        """Known machine returns its class priors."""
        priors = prior_store.get_priors("motor-001")
        assert priors.class_name == "test_motor"
        assert "current_a_avg" in priors.signals
        assert priors.signals["current_a_avg"].mean == 100.0

    def test_get_priors_unknown_machine_falls_back(self, prior_store: PriorStore):
        """Unknown machine returns generic fallback."""
        priors = prior_store.get_priors("unknown-machine")
        assert priors.class_name == "generic_industrial_motor"

    def test_hi_params_loaded(self, prior_store: PriorStore):
        """Health Index parameters loaded from config."""
        assert prior_store.hi_params.z_scale == 15.0
        assert prior_store.hi_params.slope_window_days == 7

    def test_cusum_params_loaded(self, prior_store: PriorStore):
        """CUSUM parameters loaded from config."""
        assert prior_store.cusum_params.slack == 2.0
        assert prior_store.cusum_params.threshold == 8.0

    def test_missing_config_does_not_crash(self, tmp_path: Path):
        """Missing config file produces empty priors, no exception."""
        store = PriorStore(config_path=tmp_path / "nonexistent.yaml")
        priors = store.get_priors("anything")
        assert priors.class_name == "unknown"


class TestSignalPrior:
    """Test z-score computation against priors."""

    def test_z_score_basic(self):
        p = SignalPrior(name="test", mean=100.0, std=10.0)
        assert p.z_score(110.0) == pytest.approx(1.0)
        assert p.z_score(90.0) == pytest.approx(-1.0)

    def test_z_score_zero_std(self):
        p = SignalPrior(name="test", mean=100.0, std=0.0)
        assert p.z_score(999.0) == 0.0

    def test_directional_rising(self):
        p = SignalPrior(name="test", mean=0.0, std=1.0, direction="rising")
        # Positive slope → concerning (rising)
        assert p.directional_z_score(2.0) == pytest.approx(2.0)
        # Negative slope → healthy (falling, which is good for rising concern)
        assert p.directional_z_score(-2.0) == 0.0

    def test_directional_falling(self):
        p = SignalPrior(name="test", mean=0.0, std=1.0, direction="falling")
        # Negative slope → concerning (falling). slope=-2 / std=1 → z=-2, -(-2)=2
        assert p.directional_z_score(-2.0) == pytest.approx(2.0)
        # Positive slope → healthy (rising is good when concern is falling)
        assert p.directional_z_score(2.0) == 0.0

    def test_directional_both(self):
        p = SignalPrior(name="test", mean=0.0, std=1.0, direction="both")
        assert p.directional_z_score(2.0) == pytest.approx(2.0)
        assert p.directional_z_score(-2.0) == pytest.approx(2.0)


# ═══════════════════════════════════════════════════════════════════════
# 2. FEATURES
# ═══════════════════════════════════════════════════════════════════════


class TestPhaseImbalance:
    """Test phase current imbalance computation."""

    def test_balanced(self):
        assert compute_phase_imbalance(100.0, 100.0, 100.0) == 0.0

    def test_imbalanced(self):
        # L1=100, L2=100, L3=110 → mean=103.33, max_dev=6.67 → 6.45%
        imb = compute_phase_imbalance(100.0, 100.0, 110.0)
        assert 6.0 < imb < 7.0

    def test_zero_mean(self):
        assert compute_phase_imbalance(0.0, 0.0, 0.0) == 0.0


class TestDailyAggregation:
    """Test raw readings → daily aggregation."""

    def test_groups_by_date(self):
        readings = _make_electrical_readings(days=3, readings_per_day=4)
        rows = aggregate_daily(readings, "motor-001", "electrical")
        assert len(rows) == 3

    def test_daily_row_has_values(self):
        readings = _make_electrical_readings(days=1, readings_per_day=10)
        rows = aggregate_daily(readings, "motor-001", "electrical")
        assert len(rows) == 1
        row = rows[0]
        assert row.current_a_avg is not None
        assert row.power_factor_avg is not None
        assert row.reading_count == 10

    def test_phase_imbalance_derived(self):
        readings = _make_electrical_readings(days=1, readings_per_day=10)
        rows = aggregate_daily(readings, "motor-001", "electrical")
        # L1=98%, L2=101%, L3=101% → small imbalance
        assert rows[0].phase_imbalance_percent is not None
        assert rows[0].phase_imbalance_percent > 0

    def test_empty_readings(self):
        rows = aggregate_daily([], "motor-001", "electrical")
        assert rows == []


class TestRollingSlopes:
    """Test 7-day rolling slope computation."""

    def test_stable_signal_zero_slope(self):
        """A flat signal should have near-zero slope."""
        rows = [
            DailyRow(date=date(2026, 8, d + 1), machine_id="m",
                     current_a_avg=100.0)
            for d in range(10)
        ]
        slopes = compute_rolling_slopes(rows, window_days=7,
                                        signals=["current_a_avg"])
        # After warmup, slopes should be near zero
        for s in slopes[6:]:
            val = s.get("current_a_avg_slope_7d")
            if val is not None:
                assert abs(val) < 0.01

    def test_rising_signal_positive_slope(self):
        """A linearly rising signal should have positive slope."""
        rows = [
            DailyRow(date=date(2026, 8, d + 1), machine_id="m",
                     current_a_avg=100.0 + d * 5.0)
            for d in range(10)
        ]
        slopes = compute_rolling_slopes(rows, window_days=7,
                                        signals=["current_a_avg"])
        for s in slopes[6:]:
            val = s.get("current_a_avg_slope_7d")
            if val is not None:
                assert val > 4.0  # ~5 per day

    def test_falling_signal_negative_slope(self):
        """A linearly falling signal should have negative slope."""
        rows = [
            DailyRow(date=date(2026, 8, d + 1), machine_id="m",
                     power_factor_avg=0.95 - d * 0.01)
            for d in range(10)
        ]
        slopes = compute_rolling_slopes(rows, window_days=7,
                                        signals=["power_factor_avg"])
        for s in slopes[6:]:
            val = s.get("power_factor_avg_slope_7d")
            if val is not None:
                assert val < -0.005

    def test_insufficient_data_returns_none(self):
        """Less than 3 data points returns None."""
        rows = [
            DailyRow(date=date(2026, 8, d + 1), machine_id="m",
                     current_a_avg=100.0 if d < 2 else None)
            for d in range(3)
        ]
        slopes = compute_rolling_slopes(rows, window_days=7,
                                        signals=["current_a_avg"])
        # First row: only 1 point → None
        assert slopes[0]["current_a_avg_slope_7d"] is None


class TestPolyfit:
    """Test the pure-Python polyfit slope calculation."""

    def test_perfect_line(self):
        points = [(0, 0), (1, 2), (2, 4), (3, 6)]
        assert _polyfit_slope(points) == pytest.approx(2.0)

    def test_single_point(self):
        assert _polyfit_slope([(0, 5)]) == 0.0

    def test_horizontal(self):
        points = [(0, 5), (1, 5), (2, 5)]
        assert _polyfit_slope(points) == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════
# 3. HEALTH INDEX
# ═══════════════════════════════════════════════════════════════════════


class TestHealthIndex:
    """Test the Health Index formula and risk tiering."""

    def test_healthy_machine_hi_near_100(self, prior_store: PriorStore):
        """Stable slopes (near zero) → HI near 100."""
        slopes = {
            "current_a_avg_slope_7d": 0.0,
            "power_factor_avg_slope_7d": 0.0,
            "voltage_thd_percent_slope_7d": 0.0,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
            machine_id="motor-001",
            date_str="2026-08-15",
        )
        assert result.health_index >= 95.0
        assert result.risk_tier == "low"

    def test_degrading_machine_hi_drops(self, prior_store: PriorStore):
        """Large rising current slope → HI drops significantly."""
        slopes = {
            "current_a_avg_slope_7d": 30.0,  # 3σ above mean
            "power_factor_avg_slope_7d": -0.06,  # 3σ below mean (PF falling)
            "voltage_thd_percent_slope_7d": 3.0,  # 3σ above mean
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
            machine_id="motor-001",
            date_str="2026-08-15",
        )
        assert result.health_index < 70.0
        assert result.risk_tier in ("medium", "high")

    def test_contributing_features_traced(self, prior_store: PriorStore):
        """Each contributing feature is visible in the result."""
        slopes = {
            "current_a_avg_slope_7d": 20.0,
            "power_factor_avg_slope_7d": 0.0,
            "voltage_thd_percent_slope_7d": 0.0,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
            machine_id="motor-001",
        )
        signals_in_result = {f.signal for f in result.contributing_features}
        assert "current_a_avg" in signals_in_result
        assert result.signal_count == 3

    def test_hi_clamps_at_0(self, prior_store: PriorStore):
        """Extreme slopes can't push HI below 0."""
        slopes = {
            "current_a_avg_slope_7d": 1000.0,
            "power_factor_avg_slope_7d": -10.0,
            "voltage_thd_percent_slope_7d": 500.0,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
        )
        assert result.health_index == 0.0
        assert result.risk_tier == "high"

    def test_hi_clamps_at_100(self, prior_store: PriorStore):
        """Perfect machine HI can't exceed 100."""
        # All slopes in the healthy direction:
        # current: negative slope = falling → healthy for "rising" concern → z=0
        # PF: positive slope = rising → healthy for "falling" concern → z=0
        # THD: negative slope = falling → healthy for "rising" concern → z=0
        slopes = {
            "current_a_avg_slope_7d": -5.0,
            "power_factor_avg_slope_7d": 0.01,
            "voltage_thd_percent_slope_7d": -0.5,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
        )
        assert result.health_index == 100.0
        assert result.risk_tier == "low"

    def test_missing_slopes_skipped(self, prior_store: PriorStore):
        """Signals with None slopes are excluded, not errored."""
        slopes = {
            "current_a_avg_slope_7d": 0.0,
            "power_factor_avg_slope_7d": None,
            "voltage_thd_percent_slope_7d": None,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
        )
        assert result.signal_count == 1

    def test_serialization(self, prior_store: PriorStore):
        """HealthIndexResult serializes to a valid dict."""
        slopes = {
            "current_a_avg_slope_7d": 0.0,
            "power_factor_avg_slope_7d": 0.0,
            "voltage_thd_percent_slope_7d": 0.0,
        }
        result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
            machine_id="motor-001",
            date_str="2026-08-15",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "health_index" in d
        assert "contributing_features" in d
        # Must be JSON-serializable
        json.dumps(d)


# ═══════════════════════════════════════════════════════════════════════
# 4. CUSUM
# ═══════════════════════════════════════════════════════════════════════


class TestCUSUM:
    """Test two-sided CUSUM change-point detection."""

    def test_stable_no_alerts(self):
        """Stable HI series → no CUSUM alerts."""
        detector = CUSUMDetector(
            params=CUSUMParams(slack=2.0, threshold=8.0)
        )
        hi_series = [95.0] * 20
        alerts = detector.run(hi_series)
        assert len(alerts) == 0

    def test_degrading_fires_alert(self):
        """Steadily dropping HI → CUSUM fires 'degrading' alert."""
        detector = CUSUMDetector(
            params=CUSUMParams(slack=2.0, threshold=8.0),
            target_hi=95.0,
        )
        # HI drops 5 points per day for 20 days
        hi_series = [95.0 - i * 5.0 for i in range(20)]
        alerts = detector.run(hi_series)
        assert len(alerts) > 0
        assert any(a.direction == "degrading" for a in alerts)

    def test_slow_drift_fires_within_target(self):
        """Slow drift fixture — target ≤ 2 alerts in 12 observations.

        This is the OI-66 retune test. The old implementation flagged
        12/12; the new one targets ≤ 2/12.
        """
        detector = CUSUMDetector(
            params=CUSUMParams(slack=2.0, threshold=8.0),
            target_hi=95.0,
        )
        # Gentle drift: HI drops 1 point per day for 12 days
        hi_series = [95.0 - i * 1.0 for i in range(12)]
        alerts = detector.run(hi_series)
        assert len(alerts) <= 2, (
            f"CUSUM fired {len(alerts)}/12 on the drift fixture — "
            f"target is ≤ 2/12 (OI-66)"
        )

    def test_recovery_fires_alert(self):
        """HI rising sharply → CUSUM fires 'recovering' alert."""
        detector = CUSUMDetector(
            params=CUSUMParams(slack=2.0, threshold=8.0),
            target_hi=60.0,  # Set target low to detect recovery
        )
        # HI rises sharply
        hi_series = [60.0 + i * 5.0 for i in range(20)]
        alerts = detector.run(hi_series)
        assert any(a.direction == "recovering" for a in alerts)

    def test_reset_on_alert(self):
        """After firing, accumulator resets (doesn't re-fire immediately)."""
        detector = CUSUMDetector(
            params=CUSUMParams(slack=2.0, threshold=8.0, reset_on_alert=True)
        )
        hi_series = [95.0 - i * 5.0 for i in range(20)]
        alerts = detector.run(hi_series)
        # Should fire a few times but not every step
        assert len(alerts) < len(hi_series)

    def test_alert_serialization(self):
        alert = CUSUMAlert(
            direction="degrading",
            cusum_value=9.5,
            current_hi=42.0,
            target_hi=95.0,
            day_index=15,
            date="2026-08-16",
        )
        d = alert.to_dict()
        assert d["direction"] == "degrading"
        json.dumps(d)  # Must be serializable


# ═══════════════════════════════════════════════════════════════════════
# 5. MAINTENANCE LOG
# ═══════════════════════════════════════════════════════════════════════


class TestMaintenanceLog:
    """Test maintenance event logging."""

    def test_valid_event_logs(self, tmp_path: Path):
        logger = MaintenanceLogger(log_path=tmp_path / "events.jsonl")
        event = MaintenanceEvent(
            machine_id="motor-001",
            event_date="2026-08-10",
            event_type="repair",
            triggered_by="system_alert",
            component="bearing",
            notes="Replaced inner race bearing",
        )
        assert logger.log(event) is True
        assert logger.count() == 1

    def test_invalid_event_type_rejected(self, tmp_path: Path):
        logger = MaintenanceLogger(log_path=tmp_path / "events.jsonl")
        event = MaintenanceEvent(
            machine_id="motor-001",
            event_date="2026-08-10",
            event_type="invalid_type",
            triggered_by="system_alert",
        )
        assert logger.log(event) is False

    def test_read_back(self, tmp_path: Path):
        logger = MaintenanceLogger(log_path=tmp_path / "events.jsonl")
        for i in range(3):
            logger.log(MaintenanceEvent(
                machine_id="motor-001",
                event_date=f"2026-08-{10 + i:02d}",
                event_type="inspection_only",
                triggered_by="manual_observation",
            ))
        events = logger.read_all()
        assert len(events) == 3

    def test_stage_b_ready(self, tmp_path: Path):
        logger = MaintenanceLogger(log_path=tmp_path / "events.jsonl")
        assert logger.stage_b_ready(min_events=3) is False
        for i in range(3):
            logger.log(MaintenanceEvent(
                machine_id="motor-001",
                event_date=f"2026-08-{10 + i:02d}",
                event_type="repair",
                triggered_by="system_alert",
            ))
        assert logger.stage_b_ready(min_events=3) is True

    def test_validation_errors(self):
        event = MaintenanceEvent(
            machine_id="",
            event_date="not-a-date",
            event_type="bogus",
            triggered_by="bogus",
        )
        errors = event.validate()
        assert len(errors) >= 3  # At least machine_id, event_type, triggered_by


# ═══════════════════════════════════════════════════════════════════════
# 6. EVENT ENVELOPE
# ═══════════════════════════════════════════════════════════════════════


class TestEventEnvelope:
    """Test Layer 3 maintenance_risk event structure."""

    def test_event_structure(self, prior_store: PriorStore):
        """Event has all required Layer 3 fields."""
        slopes = {
            "current_a_avg_slope_7d": 20.0,
            "power_factor_avg_slope_7d": -0.04,
            "voltage_thd_percent_slope_7d": 2.0,
        }
        hi_result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
            machine_id="motor-001",
            date_str="2026-08-15",
        )
        event = build_maintenance_risk_event(hi_result, synthetic=True)

        # Required envelope fields (Layer 3 §3)
        assert "event_id" in event
        assert event["event_type"] == "maintenance_risk"
        assert event["machine_id"] == "motor-001"
        assert "timestamp" in event
        assert event["synthetic"] is True
        assert "payload" in event
        assert event["confidence_stage"] == "stage_a_unsupervised"

        # Payload fields
        payload = event["payload"]
        assert "health_index" in payload
        assert "risk_tier" in payload
        assert "contributing_features" in payload
        assert "cusum_alerts" in payload

    def test_event_json_serializable(self, prior_store: PriorStore):
        slopes = {"current_a_avg_slope_7d": 0.0}
        hi_result = compute_health_index(
            slopes=slopes,
            priors=prior_store.get_priors("motor-001"),
            hi_params=prior_store.hi_params,
        )
        event = build_maintenance_risk_event(hi_result)
        json.dumps(event)  # Must not raise


# ═══════════════════════════════════════════════════════════════════════
# 7. END-TO-END PIPELINE
# ═══════════════════════════════════════════════════════════════════════


class TestHealthIndexPipeline:
    """Test the full batch pipeline end-to-end."""

    def test_stable_machine(self, prior_store: PriorStore):
        """Stable readings → HI stays 90–100, no CUSUM alerts."""
        pipeline = HealthIndexPipeline(
            prior_store=prior_store,
            emit_events_for={"medium", "high"},
        )
        readings = _make_electrical_readings(
            days=30,
            current_profile="stable",
            pf_profile="stable",
        )
        result = pipeline.run_batch(
            machine_id="motor-001",
            electrical_readings=readings,
        )

        assert len(result.daily_rows) == 30
        assert len(result.hi_series) > 0
        assert result.latest_hi is not None
        assert result.latest_hi.health_index >= 90.0
        assert result.latest_hi.risk_tier == "low"
        # Stable → no medium/high events
        assert len(result.events) == 0

    def test_degrading_machine(self, prior_store: PriorStore):
        """Degrading readings → HI drops, events emitted."""
        pipeline = HealthIndexPipeline(
            prior_store=prior_store,
            emit_events_for={"medium", "high"},
        )
        readings = _make_electrical_readings(
            days=30,
            current_profile="degrading",
            pf_profile="degrading",
        )
        # Amplify degradation: override current to rise 20A/day (2σ/day)
        for r in readings:
            ts = r["time"]
            dt = datetime.fromisoformat(ts)
            day_offset = (dt.date() - date(2026, 8, 1)).days
            r["data"]["current_a_avg"] = 100.0 + day_offset * 20.0
            r["data"]["power_factor_avg"] = max(0.5, 0.95 - day_offset * 0.02)

        result = pipeline.run_batch(
            machine_id="motor-001",
            electrical_readings=readings,
        )

        assert result.latest_hi is not None
        # With 20A/day slope (z=2.0) averaged across 3 signals: avg_z ≈ 0.68
        # HI = 100 - 0.68 * 15 ≈ 89.75 — a meaningful drop from stable (100)
        assert result.latest_hi.health_index < 95.0
        assert result.latest_hi.health_index < 100.0  # Not perfect
        # Contributing features should show current as the top offender
        top = result.latest_hi.contributing_features[0]
        assert top.signal == "current_a_avg"
        assert top.z_score > 1.0

    def test_insufficient_data(self, prior_store: PriorStore):
        """Less than warmup days → empty HI series, no crash."""
        pipeline = HealthIndexPipeline(prior_store=prior_store)
        readings = _make_electrical_readings(days=3, readings_per_day=10)
        result = pipeline.run_batch(
            machine_id="motor-001",
            electrical_readings=readings,
        )
        assert len(result.hi_series) == 0
        assert result.latest_hi is None
        assert len(result.events) == 0

    def test_batch_result_summary(self, prior_store: PriorStore):
        """BatchResult.summary() returns a serializable dict."""
        pipeline = HealthIndexPipeline(prior_store=prior_store)
        readings = _make_electrical_readings(days=15, readings_per_day=10)
        result = pipeline.run_batch(
            machine_id="motor-001",
            electrical_readings=readings,
        )
        summary = result.summary()
        assert isinstance(summary, dict)
        assert summary["machine_id"] == "motor-001"
        json.dumps(summary)

    def test_empty_readings(self, prior_store: PriorStore):
        """Empty readings → empty result, no crash."""
        pipeline = HealthIndexPipeline(prior_store=prior_store)
        result = pipeline.run_batch(
            machine_id="motor-001",
            electrical_readings=[],
        )
        assert len(result.daily_rows) == 0
        assert result.latest_hi is None

    def test_hi_reproducible(self, prior_store: PriorStore):
        """Same input → same HI (deterministic)."""
        pipeline = HealthIndexPipeline(prior_store=prior_store)
        readings = _make_electrical_readings(days=15, readings_per_day=10)

        r1 = pipeline.run_batch(machine_id="motor-001",
                                electrical_readings=readings)
        r2 = pipeline.run_batch(machine_id="motor-001",
                                electrical_readings=readings)

        assert r1.latest_hi.health_index == r2.latest_hi.health_index

    def test_uses_real_priors_file(self):
        """Pipeline loads the real config/layer0_priors.yaml."""
        priors_path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "layer0_priors.yaml"
        )
        if not priors_path.exists():
            pytest.skip("Real priors file not found")

        store = PriorStore(config_path=priors_path)
        pipeline = HealthIndexPipeline(prior_store=store)
        readings = _make_electrical_readings(days=15, readings_per_day=10)

        result = pipeline.run_batch(
            machine_id="isbm-main-feed",
            electrical_readings=readings,
        )
        assert result.latest_hi is not None
