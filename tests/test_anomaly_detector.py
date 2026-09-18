"""
Tests for the Unified Cross-Family Anomaly Detector.

Proves that the detector correctly identifies spikes, sudden drops,
gradual decreases, and slow drift across different sensor scales
without any sensor-specific configuration.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.edge.anomaly_detector import AnomalyDetector, MetricWindow


# ── Helper ──────────────────────────────────────────────────────────────────

def make_payload(device_id: str, sensor_type: str, data: dict) -> dict:
    """Create a minimal valid bot payload for testing."""
    return {
        "device_id": device_id,
        "timestamp": "2026-09-17T18:00:00Z",
        "sensor_type": sensor_type,
        "schema_version": "1.0",
        "data": data,
    }


# ── Test 1: No false alarms on stable data ──────────────────────────────────

def test_no_alert_on_normal_data():
    """Feed 50 stable pressure readings (~38.0 ± 0.15). Expect zero alerts."""
    import random
    random.seed(42)

    detector = AnomalyDetector()

    total_alerts = []
    for _ in range(50):
        pressure = 38.0 + random.gauss(0, 0.15)
        payload = make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": round(pressure, 2),
        })
        alerts = detector.ingest(payload)
        total_alerts.extend(alerts)

    assert len(total_alerts) == 0, f"Expected 0 alerts on stable data, got {len(total_alerts)}: {total_alerts}"
    print("  OK test_no_alert_on_normal_data")


# ── Test 2: Spike detection ─────────────────────────────────────────────────

def test_spike_detected():
    """Feed 30 stable readings, then inject a massive spike. Expect Z-score alert."""
    import random
    random.seed(42)

    detector = AnomalyDetector()

    # Build up a stable baseline
    for _ in range(30):
        payload = make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": 38.0 + random.gauss(0, 0.1),
        })
        detector.ingest(payload)

    # Inject a massive spike
    spike_payload = make_payload("Festo-SPAU-01", "pressure", {
        "line_pressure_bar": 55.0,  # Way above normal ~38 bar
    })
    alerts = detector.ingest(spike_payload)

    assert len(alerts) > 0, "Expected at least one alert for the spike"
    spike_alerts = [a for a in alerts if a["anomaly_type"] == "spike"]
    assert len(spike_alerts) > 0, f"Expected a 'spike' alert, got: {[a['anomaly_type'] for a in alerts]}"
    assert spike_alerts[0]["metric"] == "Festo-SPAU-01:line_pressure_bar"
    print("  OK test_spike_detected")


# ── Test 3: Sudden drop detection ───────────────────────────────────────────

def test_sudden_drop_detected():
    """Feed 30 stable readings, then inject a sudden drop. Expect Z-score alert."""
    import random
    random.seed(42)

    detector = AnomalyDetector()

    # Build up a stable baseline
    for _ in range(30):
        payload = make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": 38.0 + random.gauss(0, 0.1),
        })
        detector.ingest(payload)

    # Inject a sudden drop (simulating an air leak)
    drop_payload = make_payload("Festo-SPAU-01", "pressure", {
        "line_pressure_bar": 28.0,  # Way below normal ~38 bar
    })
    alerts = detector.ingest(drop_payload)

    assert len(alerts) > 0, "Expected at least one alert for the drop"
    drop_alerts = [a for a in alerts if a["anomaly_type"] == "sudden_drop"]
    assert len(drop_alerts) > 0, f"Expected a 'sudden_drop' alert, got: {[a['anomaly_type'] for a in alerts]}"
    print("  OK test_sudden_drop_detected")


# ── Test 4: Gradual decrease detection ──────────────────────────────────────

def test_gradual_decrease_detected():
    """Feed 60 readings that slowly decrease. Expect slope alert."""
    detector = AnomalyDetector(window_size=30)

    alerts_collected = []
    for i in range(60):
        # Gradual decrease: 38.0 → 30.0 over 60 ticks
        value = 38.0 - (i * 0.133)
        payload = make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": round(value, 2),
        })
        alerts = detector.ingest(payload)
        alerts_collected.extend(alerts)

    slope_alerts = [a for a in alerts_collected if a["anomaly_type"] in ("gradual_decrease", "downward_drift")]
    assert len(slope_alerts) > 0, f"Expected gradual_decrease or downward_drift alerts, got types: {set(a['anomaly_type'] for a in alerts_collected) if alerts_collected else 'none'}"
    print("  OK test_gradual_decrease_detected")


# ── Test 5: CUSUM drift detection ───────────────────────────────────────────

def test_cusum_drift_detected():
    """Feed readings that drift very slowly upward. Z-score should miss it, CUSUM should catch it."""
    import random
    random.seed(42)

    detector = AnomalyDetector(window_size=30, cusum_threshold=3.0)

    # Phase 1: Establish a baseline with 30 stable readings
    for _ in range(30):
        payload = make_payload("Omron-E5CC-01", "thermal", {
            "process_variable_c": 255.0 + random.gauss(0, 0.3),
        })
        detector.ingest(payload)

    # Phase 2: Introduce a small persistent upward bias (1.0 std above mean)
    # Each reading is only slightly above mean — Z-score won't catch individual ones
    alerts_collected = []
    for _ in range(40):
        # Biased upward: mean + 1.2*std consistently
        payload = make_payload("Omron-E5CC-01", "thermal", {
            "process_variable_c": 255.0 + 0.4 + random.gauss(0, 0.1),
        })
        alerts = detector.ingest(payload)
        alerts_collected.extend(alerts)

    cusum_alerts = [a for a in alerts_collected if "drift" in a.get("anomaly_type", "")]
    assert len(cusum_alerts) > 0, f"Expected CUSUM drift alerts, got: {set(a['anomaly_type'] for a in alerts_collected) if alerts_collected else 'none'}"
    print("  OK test_cusum_drift_detected")


# ── Test 6: Cross-sensor isolation ──────────────────────────────────────────

def test_cross_sensor_isolation():
    """Feed normal pressure AND spiking vibration simultaneously.
    Only vibration should trigger — pressure must stay clean."""
    import random
    random.seed(42)

    detector = AnomalyDetector()

    # Build baselines for both sensors
    for _ in range(30):
        detector.ingest(make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": 38.0 + random.gauss(0, 0.1),
        }))
        detector.ingest(make_payload("Banner-QM30VT1-01", "vibration", {
            "z_axis_rms_velocity_mm_s": 1.5 + random.gauss(0, 0.1),
        }))

    # Now: normal pressure, spiking vibration
    alerts_pressure = detector.ingest(make_payload("Festo-SPAU-01", "pressure", {
        "line_pressure_bar": 38.1,  # Normal
    }))
    alerts_vibration = detector.ingest(make_payload("Banner-QM30VT1-01", "vibration", {
        "z_axis_rms_velocity_mm_s": 8.0,  # Massive spike!
    }))

    assert len(alerts_pressure) == 0, f"Pressure should not alert, got: {alerts_pressure}"
    assert len(alerts_vibration) > 0, f"Vibration should alert on the spike"
    assert alerts_vibration[0]["sensor_type"] == "vibration"
    print("  OK test_cross_sensor_isolation")


# ── Test 7: Self-calibration across scales ──────────────────────────────────

def test_self_calibration():
    """Feed temperature (~255°C) and pressure (~38 bar) through the SAME detector.
    Both must work correctly without any sensor-specific configuration."""
    import random
    random.seed(42)

    detector = AnomalyDetector()

    # Build baselines for both
    for _ in range(30):
        detector.ingest(make_payload("Omron-E5CC-01", "thermal", {
            "process_variable_c": 255.0 + random.gauss(0, 0.3),
        }))
        detector.ingest(make_payload("Festo-SPAU-01", "pressure", {
            "line_pressure_bar": 38.0 + random.gauss(0, 0.1),
        }))

    # Spike both sensors simultaneously
    thermal_alerts = detector.ingest(make_payload("Omron-E5CC-01", "thermal", {
        "process_variable_c": 280.0,  # +25°C spike on a 255 baseline
    }))
    pressure_alerts = detector.ingest(make_payload("Festo-SPAU-01", "pressure", {
        "line_pressure_bar": 28.0,  # -10 bar drop on a 38 baseline
    }))

    assert len(thermal_alerts) > 0, "Thermal spike should be detected"
    assert len(pressure_alerts) > 0, "Pressure drop should be detected"

    thermal_types = [a["anomaly_type"] for a in thermal_alerts]
    pressure_types = [a["anomaly_type"] for a in pressure_alerts]

    assert "spike" in thermal_types, f"Expected thermal 'spike', got {thermal_types}"
    assert "sudden_drop" in pressure_types, f"Expected pressure 'sudden_drop', got {pressure_types}"

    print("  OK test_self_calibration")


# ── Runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running Unified Anomaly Detector tests...")
    test_no_alert_on_normal_data()
    test_spike_detected()
    test_sudden_drop_detected()
    test_gradual_decrease_detected()
    test_cusum_drift_detected()
    test_cross_sensor_isolation()
    test_self_calibration()
    print("\nAll 7 anomaly detector tests passed!")
