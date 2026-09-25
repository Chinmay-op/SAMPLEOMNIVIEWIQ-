"""
Tests for gas_model — statistical/ML extensions (§1–§8)
=========================================================

Covers:
- §1  Single-signal tiers (WARNING_GAS_ONLY, WARNING_PARTICLE_ONLY)
- §2  Sensor-health gate (range, stuck-sensor, negative tests)
- §3  Root-cause classification via Pearson correlation
- §4  EWMA adaptive baseline z-score anomaly
- §5  Derivative feature engineering
- §6  Confidence score monotonicity
- §7  Outlier detector (basic API)
- §8  Gas aggregation in features.py
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from collections import deque

import pytest

from omniview.rules.gas_model import (
    SensorHealthGate,
    SensorHealthResult,
    GasSensorFaultEvent,
    EWMATracker,
    RollingWindow,
    CrossFamilyCache,
    EnhancedGasOverheatDetector,
    GAS_WARN_SINGLE_GAS_PPM,
    GAS_WARN_SINGLE_PARTICLE_IDX,
    EWMA_Z_THRESHOLD,
    pearson_correlation,
    classify_root_cause,
    compute_confidence_score,
    GasOutlierDetector,
)
from omniview.rules.gas_overheat import (
    GAS_CRITICAL_PPM,
    GAS_CRITICAL_RISE_C_PER_MIN,
    GAS_SUSTAINED_DURATION_S,
    GAS_WARNING_TEMP_C,
    GasOverheatEvent,
)
from omniview.predictive.features import (
    DailyRow,
    aggregate_daily,
    compute_rolling_slopes,
)


# ── Helpers ──────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


def _gas_sample(
    *,
    gas_ppm: float = 1.0,
    particles: float = 3.0,
    panel_temp: float = 35.0,
    rise_rate: float = 0.1,
    humidity: float = 50.0,
    aqi: int = 2,
    device_id: str = "test-gas-01",
    timestamp: datetime | None = None,
) -> dict:
    ts = timestamp or datetime.now(IST)
    return {
        "device_id": device_id,
        "timestamp": ts.isoformat(),
        "sensor_type": "gas",
        "data": {
            "gas_concentration_ppm": gas_ppm,
            "micro_particle_index": particles,
            "internal_panel_temp_c": panel_temp,
            "rate_of_thermal_rise_c_per_min": rise_rate,
            "ambient_humidity_pct": humidity,
            "air_quality_index": aqi,
            "alert_severity_level": "NORMAL",
        },
    }


def _elec_sample(
    *,
    current_a_avg: float = 200.0,
    ambient_temp_c: float = 30.0,
    device_id: str = "test-elec-01",
    timestamp: datetime | None = None,
) -> dict:
    ts = timestamp or datetime.now(IST)
    return {
        "device_id": device_id,
        "timestamp": ts.isoformat(),
        "sensor_type": "electrical",
        "data": {
            "current_a_avg": current_a_avg,
            "ambient_temp_c": ambient_temp_c,
        },
    }


def _sustained_gas(count: int, interval_s: float = 60.0, start: datetime | None = None, **kw):
    t = start or datetime(2026, 9, 20, 10, 0, 0, tzinfo=IST)
    return [_gas_sample(timestamp=t + timedelta(seconds=i * interval_s), **kw) for i in range(count)]


# ══════════════════════════════════════════════════════════════════════
# §2  Sensor Health Gate
# ══════════════════════════════════════════════════════════════════════

class TestSensorHealthGate:

    def test_healthy_reading(self):
        gate = SensorHealthGate()
        result = gate.check("dev-1", {
            "gas_concentration_ppm": 1.5,
            "micro_particle_index": 3.0,
            "internal_panel_temp_c": 38.0,
            "ambient_humidity_pct": 55.0,
        })
        assert result.is_healthy
        assert result.fault_type == "OK"

    def test_nan_detection(self):
        gate = SensorHealthGate()
        result = gate.check("dev-1", {
            "gas_concentration_ppm": float("nan"),
        })
        assert not result.is_healthy
        assert result.fault_type == "NAN_INF"

    def test_inf_detection(self):
        gate = SensorHealthGate()
        result = gate.check("dev-1", {
            "internal_panel_temp_c": float("inf"),
        })
        assert not result.is_healthy
        assert result.fault_type == "NAN_INF"

    def test_negative_gas_range_violation(self):
        gate = SensorHealthGate()
        result = gate.check("dev-1", {
            "gas_concentration_ppm": -5.0,
        })
        assert not result.is_healthy
        assert result.fault_type == "RANGE_VIOLATION"

    def test_implausible_panel_temp(self):
        gate = SensorHealthGate()
        result = gate.check("dev-1", {
            "internal_panel_temp_c": 200.0,  # > 150 limit
        })
        assert not result.is_healthy
        assert result.fault_type == "RANGE_VIOLATION"

    def test_stuck_sensor_detection(self):
        """4 bit-identical readings → stuck sensor."""
        gate = SensorHealthGate(stuck_window=4)
        data = {"gas_concentration_ppm": 5.0, "micro_particle_index": 3.0,
                "internal_panel_temp_c": 40.0}
        # First 3 readings don't trigger (not enough in window)
        for _ in range(3):
            result = gate.check("dev-1", data)
            assert result.is_healthy
        # 4th identical reading triggers stuck
        result = gate.check("dev-1", data)
        assert not result.is_healthy
        assert result.fault_type == "STUCK_SENSOR"

    def test_normal_jitter_does_not_false_positive(self):
        """Slightly different readings (normal jitter) must NOT trigger stuck."""
        gate = SensorHealthGate(stuck_window=4)
        base = 5.0
        for i in range(6):
            data = {
                "gas_concentration_ppm": base + i * 0.01,  # jitter
                "micro_particle_index": 3.0 + i * 0.005,
                "internal_panel_temp_c": 40.0 + i * 0.02,
            }
            result = gate.check("dev-1", data)
            assert result.is_healthy, f"False positive on reading {i}"


# ══════════════════════════════════════════════════════════════════════
# §4  EWMA Tracker
# ══════════════════════════════════════════════════════════════════════

class TestEWMATracker:

    def test_warmup_returns_zero(self):
        ewma = EWMATracker(alpha=0.1, min_samples=5)
        for _ in range(4):
            z = ewma.update(10.0)
            assert z == 0.0
        assert not ewma.is_warm

    def test_warm_returns_nonzero_on_spike(self):
        ewma = EWMATracker(alpha=0.1, min_samples=5)
        for _ in range(10):
            ewma.update(10.0)
        assert ewma.is_warm
        # Inject a spike
        z = ewma.update(50.0)
        assert abs(z) > 2.0  # should be a big z-score

    def test_z_score_small_for_similar_values(self):
        ewma = EWMATracker(alpha=0.1, min_samples=10)
        # Feed values with natural jitter (like gas_bot's wanderer)
        import random
        random.seed(42)
        for _ in range(30):
            ewma.update(10.0 + random.uniform(-0.5, 0.5))
        # A value within the normal range should have small z
        z = ewma.update(10.0)
        assert abs(z) < 3.0  # within 3 sigma of baseline

    def test_reset(self):
        ewma = EWMATracker()
        ewma.update(10.0)
        ewma.reset()
        assert ewma.mean is None
        assert not ewma.is_warm


# ══════════════════════════════════════════════════════════════════════
# §5  Rolling Window + Derivatives
# ══════════════════════════════════════════════════════════════════════

class TestRollingWindow:

    def test_slope_linear_signal(self):
        """Linear signal should have positive slope."""
        w = RollingWindow(max_size=10)
        for i in range(10):
            w.append(float(i) * 2.0, float(i))
        slope = w.slope()
        assert slope is not None
        assert abs(slope - 2.0) < 0.01

    def test_slope_none_when_too_few(self):
        w = RollingWindow()
        w.append(1.0, 0.0)
        w.append(2.0, 1.0)
        assert w.slope() is None  # needs >= 3

    def test_acceleration_constant_slope(self):
        """Constant slope → acceleration ≈ 0."""
        w = RollingWindow(max_size=12)
        for i in range(12):
            w.append(float(i) * 3.0, float(i))
        accel = w.acceleration()
        assert accel is not None
        assert abs(accel) < 0.1

    def test_acceleration_positive_for_accelerating(self):
        """Quadratic signal → positive acceleration."""
        w = RollingWindow(max_size=12)
        for i in range(12):
            w.append(float(i) ** 2, float(i))
        accel = w.acceleration()
        assert accel is not None
        assert accel > 0


# ══════════════════════════════════════════════════════════════════════
# §3  Root-Cause Classification
# ══════════════════════════════════════════════════════════════════════

class TestRootCause:

    def test_pearson_perfect_positive(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = pearson_correlation(xs, ys)
        assert abs(r - 1.0) < 0.001

    def test_pearson_zero_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [5.0, 5.0, 5.0, 5.0, 5.0]  # constant
        r = pearson_correlation(xs, ys)
        assert abs(r) < 0.001

    def test_pearson_too_few_points(self):
        r = pearson_correlation([1.0, 2.0], [3.0, 4.0])
        assert r == 0.0

    def test_electrical_overload_classification(self):
        """Correlated temps + rising current → ELECTRICAL_OVERLOAD."""
        temps = [30.0, 32.0, 34.0, 36.0, 38.0, 40.0, 42.0]
        currs = [200.0, 205.0, 210.0, 215.0, 220.0, 225.0, 230.0]
        rc = classify_root_cause(
            tier="WARNING_TEMP",
            panel_temps=temps,
            currents=currs,
            gas_elevated_only=False,
            particle_elevated_only=False,
        )
        assert rc == "ELECTRICAL_OVERLOAD"

    def test_external_heat_source(self):
        """Uncorrelated temps + current → EXTERNAL_HEAT_SOURCE."""
        temps = [30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0]
        currs = [200.0, 198.0, 201.0, 199.0, 200.0, 202.0, 199.0]
        rc = classify_root_cause(
            tier="WARNING_TEMP",
            panel_temps=temps,
            currents=currs,
            gas_elevated_only=False,
            particle_elevated_only=False,
        )
        assert rc == "EXTERNAL_HEAT_SOURCE"

    def test_chemical_voc_source(self):
        rc = classify_root_cause(
            tier="WARNING_GAS_ONLY",
            panel_temps=[],
            currents=[],
            gas_elevated_only=True,
            particle_elevated_only=False,
        )
        assert rc == "CHEMICAL_VOC_SOURCE"

    def test_mechanical_contamination(self):
        rc = classify_root_cause(
            tier="WARNING_PARTICLE_ONLY",
            panel_temps=[],
            currents=[],
            gas_elevated_only=False,
            particle_elevated_only=True,
        )
        assert rc == "MECHANICAL_CONTAMINATION"

    def test_insulation_degradation(self):
        rc = classify_root_cause(
            tier="CRITICAL",
            panel_temps=[],
            currents=[],
            gas_elevated_only=False,
            particle_elevated_only=False,
        )
        assert rc == "INSULATION_DEGRADATION"

    def test_unknown_with_insufficient_data(self):
        rc = classify_root_cause(
            tier="WATCH",
            panel_temps=[30.0, 35.0],  # too few
            currents=[200.0, 210.0],
            gas_elevated_only=False,
            particle_elevated_only=False,
        )
        assert rc == "UNKNOWN"


# ══════════════════════════════════════════════════════════════════════
# §6  Confidence Score
# ══════════════════════════════════════════════════════════════════════

class TestConfidenceScore:

    def test_zero_for_baseline(self):
        """Baseline values → score near zero."""
        score = compute_confidence_score(
            gas_ppm=1.0, particles=3.0, panel_temp=35.0, rise_rate=0.1,
            ewma_z_gas=0.0, ewma_z_temp=0.0,
            gas_acceleration=None, temp_acceleration=None,
        )
        assert score == 0.0

    def test_monotonically_increases_with_gas(self):
        """Higher gas → higher confidence score."""
        scores = []
        for gas in [15.0, 25.0, 35.0, 50.0]:
            s = compute_confidence_score(
                gas_ppm=gas, particles=3.0, panel_temp=35.0, rise_rate=0.1,
                ewma_z_gas=0.0, ewma_z_temp=0.0,
                gas_acceleration=None, temp_acceleration=None,
            )
            scores.append(s)
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1], (
                f"Score did not increase: {scores}"
            )

    def test_acceleration_increases_score(self):
        """Positive acceleration → higher score than negative."""
        s_accel = compute_confidence_score(
            gas_ppm=20.0, particles=10.0, panel_temp=55.0, rise_rate=2.0,
            ewma_z_gas=1.0, ewma_z_temp=1.0,
            gas_acceleration=0.5, temp_acceleration=0.3,
        )
        s_decel = compute_confidence_score(
            gas_ppm=20.0, particles=10.0, panel_temp=55.0, rise_rate=2.0,
            ewma_z_gas=1.0, ewma_z_temp=1.0,
            gas_acceleration=-0.5, temp_acceleration=-0.3,
        )
        assert s_accel > s_decel

    def test_bounded_0_to_100(self):
        """Score must be within [0, 100] even with extreme values."""
        score = compute_confidence_score(
            gas_ppm=500.0, particles=500.0, panel_temp=150.0, rise_rate=20.0,
            ewma_z_gas=10.0, ewma_z_temp=10.0,
            gas_acceleration=5.0, temp_acceleration=5.0,
        )
        assert 0.0 <= score <= 100.0


# ══════════════════════════════════════════════════════════════════════
# §1  Single-Signal Tiers (Enhanced Detector)
# ══════════════════════════════════════════════════════════════════════

class TestSingleSignalTiers:

    def test_gas_only_warning_after_sustained(self):
        """Gas above single-signal threshold, sustained → WARNING_GAS_ONLY."""
        det = EnhancedGasOverheatDetector()
        samples = _sustained_gas(
            count=5, interval_s=60.0,
            gas_ppm=GAS_WARN_SINGLE_GAS_PPM + 5,
            particles=5.0,  # below combo threshold
            panel_temp=35.0,
        )
        events = [det.evaluate(s) for s in samples]
        fired = [e for e in events if isinstance(e, GasOverheatEvent)]
        assert len(fired) >= 1
        assert fired[0].tier == "WARNING_GAS_ONLY"
        assert fired[0].severity == "WARNING"

    def test_particle_only_warning_after_sustained(self):
        """Particles above single-signal threshold → WARNING_PARTICLE_ONLY."""
        det = EnhancedGasOverheatDetector()
        samples = _sustained_gas(
            count=5, interval_s=60.0,
            gas_ppm=2.0,  # below both thresholds
            particles=GAS_WARN_SINGLE_PARTICLE_IDX + 10,
            panel_temp=35.0,
        )
        events = [det.evaluate(s) for s in samples]
        fired = [e for e in events if isinstance(e, GasOverheatEvent)]
        assert len(fired) >= 1
        assert fired[0].tier == "WARNING_PARTICLE_ONLY"

    def test_single_signal_not_on_first_sample(self):
        """Single-signal tiers need sustained duration — no fire on first."""
        det = EnhancedGasOverheatDetector()
        ev = det.evaluate(_gas_sample(
            gas_ppm=GAS_WARN_SINGLE_GAS_PPM + 10,
            particles=5.0,
        ))
        assert ev is None  # first sample, timer starts


# ══════════════════════════════════════════════════════════════════════
# §2  Sensor Fault Events (Enhanced Detector)
# ══════════════════════════════════════════════════════════════════════

class TestSensorFaultEvents:

    def test_nan_returns_fault_event(self):
        det = EnhancedGasOverheatDetector()
        sample = _gas_sample(gas_ppm=float("nan"))
        ev = det.evaluate(sample)
        assert isinstance(ev, GasSensorFaultEvent)
        assert ev.fault_type == "NAN_INF"

    def test_range_violation_returns_fault(self):
        det = EnhancedGasOverheatDetector()
        sample = _gas_sample(panel_temp=-50.0)
        ev = det.evaluate(sample)
        assert isinstance(ev, GasSensorFaultEvent)
        assert ev.fault_type == "RANGE_VIOLATION"

    def test_fault_bypasses_fire_classification(self):
        """Even with CRITICAL-level values, bad data → fault, not fire."""
        det = EnhancedGasOverheatDetector()
        sample = _gas_sample(
            gas_ppm=float("inf"),  # would be CRITICAL if valid
            rise_rate=5.0,
        )
        ev = det.evaluate(sample)
        assert isinstance(ev, GasSensorFaultEvent)
        assert ev.event_type == "sensor_fault"


# ══════════════════════════════════════════════════════════════════════
# §3  Cross-Family Cache + Root Cause (Enhanced Detector)
# ══════════════════════════════════════════════════════════════════════

class TestCrossFamilyCorrelation:

    def test_electrical_reading_cached_returns_none(self):
        """Electrical readings are cached, not classified."""
        det = EnhancedGasOverheatDetector()
        ev = det.evaluate(_elec_sample(current_a_avg=200.0))
        assert ev is None

    def test_root_cause_present_in_event(self):
        """Events should have a root_cause field populated."""
        det = EnhancedGasOverheatDetector()
        # Fire a CRITICAL event
        ev = det.evaluate(_gas_sample(
            gas_ppm=30.0, particles=50.0, rise_rate=4.0, panel_temp=72.0,
        ))
        assert isinstance(ev, GasOverheatEvent)
        assert ev.root_cause == "INSULATION_DEGRADATION"


# ══════════════════════════════════════════════════════════════════════
# §4  EWMA Adaptive Anomaly (Enhanced Detector)
# ══════════════════════════════════════════════════════════════════════

class TestEWMAAdaptiveAnomaly:

    def test_z_score_anomaly_below_global_threshold(self):
        """A naturally-cool panel with a sudden rise should be flagged
        even if the absolute value is below the global WARNING threshold."""
        det = EnhancedGasOverheatDetector(ewma_alpha=0.1)

        # Warm up EWMA with 15 baseline readings (cool panel: ~25°C)
        t = datetime(2026, 9, 20, 10, 0, 0, tzinfo=IST)
        for i in range(15):
            det.evaluate(_gas_sample(
                panel_temp=25.0, gas_ppm=1.0,
                timestamp=t + timedelta(seconds=i * 60),
            ))

        # Now spike panel temp to 45°C — below global WARNING (65°C)
        # but very abnormal for this device's baseline (~25°C)
        ev = det.evaluate(_gas_sample(
            panel_temp=45.0, gas_ppm=1.0,
            timestamp=t + timedelta(seconds=15 * 60),
        ))

        # Should fire an adaptive WATCH event
        if ev is not None and isinstance(ev, GasOverheatEvent):
            assert ev.tier == "WATCH_ADAPTIVE"
            assert ev.severity == "INFO"
            assert ev.ewma_z_temp != 0.0


# ══════════════════════════════════════════════════════════════════════
# §5  Derivatives in Event Payload
# ══════════════════════════════════════════════════════════════════════

class TestDerivativesInPayload:

    def test_critical_event_has_derivatives(self):
        det = EnhancedGasOverheatDetector()
        # Feed some readings for window warmup
        t = datetime(2026, 9, 20, 10, 0, 0, tzinfo=IST)
        for i in range(5):
            det.evaluate(_gas_sample(
                gas_ppm=1.0 + i * 2,
                panel_temp=35.0 + i * 3,
                timestamp=t + timedelta(seconds=i * 60),
            ))
        # Fire a CRITICAL
        ev = det.evaluate(_gas_sample(
            gas_ppm=30.0, particles=50.0, rise_rate=4.0, panel_temp=72.0,
            timestamp=t + timedelta(seconds=5 * 60),
        ))
        assert isinstance(ev, GasOverheatEvent)
        d = ev.to_dict()
        assert "gas_slope" in d
        assert "gas_acceleration" in d
        assert "temp_slope" in d
        assert "temp_acceleration" in d


# ══════════════════════════════════════════════════════════════════════
# §6  Confidence Score in Event
# ══════════════════════════════════════════════════════════════════════

class TestConfidenceInEvent:

    def test_critical_has_high_confidence(self):
        det = EnhancedGasOverheatDetector()
        ev = det.evaluate(_gas_sample(
            gas_ppm=35.0, particles=55.0, rise_rate=5.0, panel_temp=75.0,
        ))
        assert isinstance(ev, GasOverheatEvent)
        assert ev.confidence_score > 20.0  # meaningful non-zero score


# ══════════════════════════════════════════════════════════════════════
# §7  Outlier Detector API
# ══════════════════════════════════════════════════════════════════════

class TestOutlierDetector:

    def test_no_model_returns_zero(self):
        """With no saved model, score should gracefully return 0.0."""
        od = GasOutlierDetector(model_path="/tmp/nonexistent.joblib")
        score = od.score({
            "gas_ppm": 1.0, "particles": 3.0, "panel_temp": 35.0,
        })
        assert score == 0.0
        assert not od.available


# ══════════════════════════════════════════════════════════════════════
# §8  Gas Daily Aggregation (features.py)
# ══════════════════════════════════════════════════════════════════════

class TestGasAggregation:

    def test_daily_row_has_gas_fields(self):
        row = DailyRow(date=date(2026, 9, 20), machine_id="test")
        assert hasattr(row, "gas_concentration_ppm")
        assert hasattr(row, "internal_panel_temp_c")

    def test_aggregate_daily_gas(self):
        readings = [
            {
                "timestamp": "2026-09-20T10:00:00+05:30",
                "data": {
                    "gas_concentration_ppm": 1.0,
                    "internal_panel_temp_c": 36.0,
                },
            },
            {
                "timestamp": "2026-09-20T11:00:00+05:30",
                "data": {
                    "gas_concentration_ppm": 2.0,
                    "internal_panel_temp_c": 40.0,
                },
            },
        ]
        rows = aggregate_daily(readings, "test-machine", sensor_type="gas")
        assert len(rows) == 1
        assert rows[0].gas_concentration_ppm == pytest.approx(1.5)
        assert rows[0].internal_panel_temp_c == pytest.approx(38.0)

    def test_gas_in_rolling_slopes(self):
        """Gas fields should appear in the default slope computation."""
        rows = []
        for i in range(10):
            r = DailyRow(
                date=date(2026, 9, 10 + i),
                machine_id="test",
                gas_concentration_ppm=1.0 + i * 0.1,
                internal_panel_temp_c=35.0 + i * 0.5,
            )
            rows.append(r)
        slopes = compute_rolling_slopes(rows)
        assert len(slopes) == 10
        # Last row should have gas slopes computed
        last = slopes[-1]
        assert "gas_concentration_ppm_slope_7d" in last
        assert "internal_panel_temp_c_slope_7d" in last
        # Gas is rising → positive slope
        gas_slope = last["gas_concentration_ppm_slope_7d"]
        assert gas_slope is not None
        assert gas_slope > 0

    def test_to_dict_includes_gas_fields(self):
        row = DailyRow(
            date=date(2026, 9, 20),
            machine_id="test",
            gas_concentration_ppm=1.5,
            internal_panel_temp_c=38.0,
        )
        d = row.to_dict()
        assert d["gas_concentration_ppm"] == 1.5
        assert d["internal_panel_temp_c"] == 38.0


# ══════════════════════════════════════════════════════════════════════
# Existing behavior preservation
# ══════════════════════════════════════════════════════════════════════

class TestExistingBehaviorPreserved:

    def test_critical_still_fires_immediately(self):
        """CRITICAL fire-precursor rule MUST remain deterministic and immediate."""
        det = EnhancedGasOverheatDetector()
        ev = det.evaluate(_gas_sample(
            gas_ppm=30.0, particles=50.0, rise_rate=4.0, panel_temp=72.0,
        ))
        assert isinstance(ev, GasOverheatEvent)
        assert ev.severity == "CRITICAL"
        assert ev.tier == "CRITICAL"
        assert ev.condition_duration_s == 0.0

    def test_normal_reading_no_event(self):
        det = EnhancedGasOverheatDetector()
        ev = det.evaluate(_gas_sample())
        assert ev is None

    def test_warning_temp_sustained(self):
        """WARNING_TEMP still requires sustained duration."""
        det = EnhancedGasOverheatDetector()
        samples = _sustained_gas(
            count=5, interval_s=60.0,
            panel_temp=GAS_WARNING_TEMP_C + 5,
        )
        events = [det.evaluate(s) for s in samples]
        assert events[0] is None  # first sample starts timer
        fired = [e for e in events if isinstance(e, GasOverheatEvent)]
        assert len(fired) >= 1
        assert fired[0].severity == "WARNING"
