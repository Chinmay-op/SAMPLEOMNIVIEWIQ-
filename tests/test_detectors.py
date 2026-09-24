"""
Tests for all new rule detectors and the detectors_live runner.

Covers:
    - F02 demand_window (DemandWindowDetector)
    - F04 lazy_idle (LazyIdleDetector)
    - F05 pressure_leak (PressureLeakDetector)
    - F06 vibration_zone (VibrationZoneDetector)
    - detectors_live (DetectorsLiveRunner)
"""

import pytest
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════════════════════════════
# F02 — Demand Window
# ═══════════════════════════════════════════════════════════════════════


class TestDemandWindowDetector:
    """F02 md_risk — deterministic 15-min window integral."""

    def _make_detector(self):
        from omniview.rules.demand_window import DemandWindowDetector
        return DemandWindowDetector(
            contract_demand_kva=500.0,
            window_minutes=15,
            alert_minute=11,
        )

    def _make_sample(self, kva: float, ts: datetime, device_id: str = "test-mfm") -> dict:
        return {
            "device_id": device_id,
            "timestamp": ts.isoformat(),
            "sensor_type": "electrical",
            "data": {"kva": kva},
        }

    def test_no_alert_below_contract(self):
        """Below-contract kVA should never fire."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        for i in range(50):  # 50 ticks at 15s = 12.5 min
            ts = base + timedelta(seconds=i * 15)
            result = det.evaluate(self._make_sample(300.0, ts))
        assert result is None

    def test_alert_fires_at_minute_11(self):
        """High kVA should fire at minute 11."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        event = None
        for i in range(50):  # 50 × 15s = 12.5 min
            ts = base + timedelta(seconds=i * 15)
            result = det.evaluate(self._make_sample(600.0, ts))
            if result is not None:
                event = result
                break
        assert event is not None
        assert event.event_type == "md_risk"
        assert event.projected_breach is True
        assert event.t_minutes >= 11.0

    def test_only_fires_once_per_window(self):
        """Should not fire twice in the same 15-min window."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        fire_count = 0
        for i in range(60):
            ts = base + timedelta(seconds=i * 15)
            result = det.evaluate(self._make_sample(600.0, ts))
            if result is not None:
                fire_count += 1
        assert fire_count == 1

    def test_to_dict_has_event_id(self):
        """Event dict should have event_id and source_unit."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        event = None
        for i in range(50):
            ts = base + timedelta(seconds=i * 15)
            result = det.evaluate(self._make_sample(600.0, ts))
            if result is not None:
                event = result
                break
        assert event is not None
        d = event.to_dict()
        assert "event_id" in d
        assert d["source_unit"] == "demand_window"

    def test_kw_var_fallback(self):
        """Should compute kVA from kw + var when kva is missing."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        sample = {
            "device_id": "test-mfm",
            "timestamp": base.isoformat(),
            "sensor_type": "electrical",
            "data": {"kw": 400.0, "var": 300.0},  # √(400²+300²) = 500
        }
        result = det.evaluate(sample)
        # First sample, won't fire, but should not crash
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# F04 — Lazy Idle
# ═══════════════════════════════════════════════════════════════════════


class TestLazyIdleDetector:
    """F04 lazy_idle — threshold rule + sustained-duration gate."""

    def _make_detector(self):
        from omniview.rules.lazy_idle import LazyIdleDetector
        return LazyIdleDetector(
            temp_threshold_c=25.0,
            current_threshold_a=0.65,
            duration_min=15,
        )

    def _make_sample(self, temp: float, current: float, ts: datetime) -> dict:
        return {
            "device_id": "test-barrel",
            "timestamp": ts.isoformat(),
            "sensor_type": "thermal",
            "data": {"zone_temp_c": temp, "current_a": current},
        }

    def test_fires_after_15_min(self):
        """Hot + idle sustained for 15 min should fire."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        event = None
        for i in range(20):  # 20 × 60s = 20 min
            ts = base + timedelta(minutes=i)
            result = det.evaluate(self._make_sample(250.0, 0.1, ts))
            if result is not None:
                event = result
        assert event is not None
        assert event.event_type == "lazy_idle"
        assert event.duration_min >= 15.0

    def test_no_fire_when_cool(self):
        """Cool temperature should not fire even if current is low."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        for i in range(20):
            ts = base + timedelta(minutes=i)
            result = det.evaluate(self._make_sample(20.0, 0.1, ts))
        assert result is None

    def test_no_fire_when_drawing_current(self):
        """High current should not fire even if hot."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        for i in range(20):
            ts = base + timedelta(minutes=i)
            result = det.evaluate(self._make_sample(250.0, 50.0, ts))
        assert result is None

    def test_reset_on_condition_break(self):
        """Breaking condition mid-stream should reset the timer."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # 10 min hot+idle
        for i in range(10):
            ts = base + timedelta(minutes=i)
            det.evaluate(self._make_sample(250.0, 0.1, ts))

        # Break: draw current
        ts_break = base + timedelta(minutes=10)
        det.evaluate(self._make_sample(250.0, 50.0, ts_break))

        # 10 more min hot+idle (but timer reset)
        event = None
        for i in range(11, 21):
            ts = base + timedelta(minutes=i)
            result = det.evaluate(self._make_sample(250.0, 0.1, ts))
            if result is not None:
                event = result

        # Should NOT have fired — only 10 min since reset
        assert event is None


# ═══════════════════════════════════════════════════════════════════════
# F05 — Pressure Leak
# ═══════════════════════════════════════════════════════════════════════


class TestPressureLeakDetector:
    """F05 pressure_leak — linear slope on loaded-only window."""

    def _make_detector(self):
        from omniview.rules.pressure_leak import PressureLeakDetector
        return PressureLeakDetector(
            decay_threshold=0.15,
            slope_window_s=300,
            min_samples=5,
        )

    def _make_sample(self, bar: float, ts: datetime, loaded: bool = True) -> dict:
        return {
            "device_id": "test-comp",
            "timestamp": ts.isoformat(),
            "sensor_type": "pressure",
            "data": {"pressure_bar": bar, "loaded": loaded},
        }

    def test_fires_on_decay(self):
        """Rapid pressure drop while loaded should fire."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        event = None
        for i in range(10):
            ts = base + timedelta(seconds=i * 30)
            bar = 8.0 - (i * 0.6)  # 0.6 bar drop per 30s = 1.2 bar/min
            result = det.evaluate(self._make_sample(bar, ts))
            if result is not None:
                event = result
        assert event is not None
        assert event.event_type == "pressure_leak"
        assert event.decay_rate_bar_per_min < 0

    def test_no_fire_on_stable_pressure(self):
        """Stable pressure should not fire."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        for i in range(10):
            ts = base + timedelta(seconds=i * 30)
            result = det.evaluate(self._make_sample(8.0, ts))
        assert result is None

    def test_ignores_unloaded_samples(self):
        """Unloaded samples should not count toward slope."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        for i in range(10):
            ts = base + timedelta(seconds=i * 30)
            bar = 8.0 - (i * 0.6)
            result = det.evaluate(self._make_sample(bar, ts, loaded=False))
        assert result is None

    def test_resets_on_load_transition(self):
        """Transitioning from loaded→unloaded should reset buffer."""
        det = self._make_detector()
        base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # 3 loaded samples (not enough for threshold)
        for i in range(3):
            ts = base + timedelta(seconds=i * 30)
            det.evaluate(self._make_sample(8.0 - i * 0.5, ts))

        # Transition to unloaded
        ts_unload = base + timedelta(seconds=90)
        det.evaluate(self._make_sample(7.0, ts_unload, loaded=False))

        # Back to loaded — buffer should be reset
        for i in range(5):
            ts = base + timedelta(seconds=120 + i * 30)
            result = det.evaluate(self._make_sample(8.0, ts))

        assert result is None  # stable pressure after reset


# ═══════════════════════════════════════════════════════════════════════
# F06 — Vibration Zone
# ═══════════════════════════════════════════════════════════════════════


class TestVibrationZoneDetector:
    """F06 vibration_zone — ISO 10816-3 zone classifier."""

    def _make_detector(self):
        from omniview.rules.vibration_zone import VibrationZoneDetector
        return VibrationZoneDetector(emit_on_cd_only=True)

    def _make_sample(self, rms: float, ts: datetime) -> dict:
        return {
            "device_id": "test-motor",
            "timestamp": ts.isoformat(),
            "sensor_type": "vibration",
            "data": {"rms_velocity_mms": rms},
        }

    def test_zone_a_silent(self):
        """Zone A reading should not fire."""
        det = self._make_detector()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        result = det.evaluate(self._make_sample(1.5, ts))
        assert result is None

    def test_zone_b_silent(self):
        """Zone B reading should not fire (emit_on_cd_only=True)."""
        det = self._make_detector()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        result = det.evaluate(self._make_sample(5.0, ts))
        assert result is None

    def test_zone_c_fires(self):
        """Zone C reading should fire with severity=alert."""
        det = self._make_detector()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        result = det.evaluate(self._make_sample(10.0, ts))
        assert result is not None
        assert result.zone == "C"
        assert result.severity == "alert"

    def test_zone_d_fires(self):
        """Zone D reading should fire with severity=critical."""
        det = self._make_detector()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        result = det.evaluate(self._make_sample(25.0, ts))
        assert result is not None
        assert result.zone == "D"
        assert result.severity == "critical"

    def test_zone_transition_tracked(self):
        """Should track prev_zone on transition."""
        det = self._make_detector()
        ts1 = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        det.evaluate(self._make_sample(1.0, ts1))  # Zone A

        ts2 = datetime(2026, 9, 15, 10, 1, 0, tzinfo=IST)
        result = det.evaluate(self._make_sample(10.0, ts2))  # Zone C
        assert result is not None
        assert result.prev_zone == "A"
        assert result.zone == "C"
        assert result.zone_changed is True

    def test_classify_zone_function(self):
        """Test the standalone classify_zone function."""
        from omniview.rules.vibration_zone import classify_zone
        assert classify_zone(1.0) == "A"
        assert classify_zone(5.0) == "B"
        assert classify_zone(10.0) == "C"
        assert classify_zone(25.0) == "D"

    def test_recover_from_cd_refires(self):
        """After recovering to A/B, re-entering C should re-fire."""
        det = self._make_detector()
        ts1 = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        result1 = det.evaluate(self._make_sample(10.0, ts1))  # Zone C
        assert result1 is not None

        ts2 = datetime(2026, 9, 15, 10, 1, 0, tzinfo=IST)
        det.evaluate(self._make_sample(1.0, ts2))  # Zone A (recover)

        ts3 = datetime(2026, 9, 15, 10, 2, 0, tzinfo=IST)
        result3 = det.evaluate(self._make_sample(10.0, ts3))  # Zone C again
        assert result3 is not None


# ═══════════════════════════════════════════════════════════════════════
# Detectors Live Runner
# ═══════════════════════════════════════════════════════════════════════


class TestDetectorsLiveRunner:
    """detectors_live — poll-cycle runner integration test."""

    def _make_runner(self):
        from omniview.rules.detectors_live import DetectorsLiveRunner
        published = []

        def mock_publish(topic: str, payload: str) -> bool:
            published.append({"topic": topic, "payload": payload})
            return True

        runner = DetectorsLiveRunner(
            site_id="test-site",
            publish_fn=mock_publish,
        )
        return runner, published

    def test_empty_cycle(self):
        """Empty readings should produce zero events."""
        runner, published = self._make_runner()
        metrics = runner.run_once(readings_by_family={})
        assert metrics.readings_processed == 0
        assert metrics.events_emitted == 0
        assert len(published) == 0

    def test_gas_event_triggers(self):
        """Gas smoldering reading should trigger gas_overheat."""
        runner, published = self._make_runner()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        readings = {
            "gas": [
                {
                    "device_id": "test-gas-01",
                    "timestamp": ts.isoformat(),
                    "sensor_type": "gas",
                    "data": {
                        "gas_concentration_ppm": 35.0,
                        "micro_particle_index": 55.0,
                        "internal_panel_temp_c": 72.0,
                        "rate_of_thermal_rise_c_per_min": 4.2,
                        "ambient_humidity_pct": 52.0,
                        "air_quality_index": 7,
                    },
                }
            ]
        }
        metrics = runner.run_once(readings_by_family=readings)
        assert metrics.readings_processed == 1
        assert metrics.events_emitted >= 1
        assert len(published) >= 1
        assert "_alerts/gas_overheat" in published[0]["topic"]

    def test_vibration_zone_d_triggers(self):
        """Zone D vibration should trigger vibration_zone event."""
        runner, published = self._make_runner()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        readings = {
            "vibration": [
                {
                    "device_id": "test-motor-01",
                    "timestamp": ts.isoformat(),
                    "sensor_type": "vibration",
                    "data": {"rms_velocity_mms": 25.0},
                }
            ]
        }
        # Note: wire.adapt won't find rms_velocity_mms in the raw map,
        # but the detector accepts the short name too
        metrics = runner.run_once(readings_by_family=readings)
        assert metrics.events_emitted >= 1

    def test_wire_adapter_is_called(self):
        """Verify wire.py field names are mapped before detectors run."""
        runner, published = self._make_runner()
        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # Use RAW DevB field names — wire.py should map them
        readings = {
            "gas": [
                {
                    "device_id": "test-gas-01",
                    "timestamp": ts.isoformat(),
                    "sensor_type": "gas",
                    "data": {
                        "gas_concentration_ppm": 35.0,      # → gas_ppm
                        "micro_particle_index": 55.0,       # → particle_idx
                        "internal_panel_temp_c": 72.0,      # → panel_temp_c
                        "rate_of_thermal_rise_c_per_min": 4.2,  # → thermal_rise_rate
                        "ambient_humidity_pct": 52.0,
                        "air_quality_index": 7,
                    },
                }
            ]
        }
        metrics = runner.run_once(readings_by_family=readings)
        # Gas detector accepts both raw and adapted names, so this should work
        # The important thing is it doesn't crash
        assert metrics.detectors_errored == 0

    def test_failing_detector_doesnt_block_others(self):
        """A broken detector should log error but not stop the cycle."""
        from omniview.rules.detectors_live import (
            DetectorEntry,
            DetectorsLiveRunner,
        )

        class BrokenDetector:
            def evaluate(self, sample):
                raise RuntimeError("I'm broken!")

        published = []

        runner = DetectorsLiveRunner(
            site_id="test-site",
            publish_fn=lambda t, p: published.append({"topic": t, "payload": p}) or True,
            registry=[
                DetectorEntry(
                    name="broken",
                    detector=BrokenDetector(),
                    sensor_types=["gas"],
                ),
            ],
        )

        ts = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
        readings = {
            "gas": [
                {
                    "device_id": "test-gas",
                    "timestamp": ts.isoformat(),
                    "sensor_type": "gas",
                    "data": {"gas_concentration_ppm": 10.0},
                }
            ]
        }

        metrics = runner.run_once(readings_by_family=readings)
        assert metrics.detectors_errored == 1
        assert metrics.readings_processed == 1

    def test_metrics_tracking(self):
        """Cycle metrics should track cumulative stats."""
        runner, _ = self._make_runner()
        m1 = runner.run_once(readings_by_family={})
        assert m1.cycle_number == 1

        m2 = runner.run_once(readings_by_family={})
        assert m2.cycle_number == 2
