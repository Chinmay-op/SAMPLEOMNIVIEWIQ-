"""
Tests for gas_overheat rule — S1 "fire forecast"
==================================================

Mirrors the test patterns from test_action_cards.py (OI-69):
all self-contained, no DB/MQTT needed.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from omniview.rules.gas_overheat import (
    GAS_CRITICAL_PPM,
    GAS_CRITICAL_PARTICLE_IDX,
    GAS_CRITICAL_RISE_C_PER_MIN,
    GAS_SUSTAINED_DURATION_S,
    GAS_STALE_TIMEOUT_S,
    GAS_WARNING_PPM,
    GAS_WARNING_PARTICLE_IDX,
    GAS_WARNING_TEMP_C,
    GAS_WATCH_RISE_C_PER_MIN,
    GAS_WATCH_TEMP_C,
    GasOverheatDetector,
    GasOverheatEvent,
)
from omniview.rules.action_cards import ActionCardGenerator, CARD_TEMPLATES


# ── helpers ──────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


def _make_sample(
    *,
    gas_ppm: float = 1.0,
    particles: float = 3.0,
    panel_temp: float = 35.0,
    rise_rate: float = 0.1,
    aqi: int = 0,
    device_id: str = "pune-comp-gas01",
    timestamp: datetime | None = None,
    severity: str = "NORMAL",
) -> dict:
    """Build a gas sample dict matching gas_schema.json shape."""
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
            "ambient_humidity_pct": 50.0,
            "air_quality_index": aqi,
            "alert_severity_level": severity,
        },
    }


def _make_sustained_samples(
    *,
    count: int,
    interval_s: float = 60.0,
    start: datetime | None = None,
    **kwargs,
) -> list[dict]:
    """Generate ``count`` samples spaced ``interval_s`` apart."""
    t = start or datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)
    samples = []
    for i in range(count):
        ts = t + timedelta(seconds=i * interval_s)
        samples.append(_make_sample(timestamp=ts, **kwargs))
    return samples


# ── GasOverheatEvent tests ───────────────────────────────────────────────


class TestGasOverheatEvent:
    """Event dataclass."""

    def test_event_creation(self):
        ev = GasOverheatEvent(
            device_id="test-01",
            timestamp=datetime.now(IST),
        )
        assert ev.event_type == "gas_overheat"
        assert ev.severity == "WARNING"
        assert ev.synthetic is True

    def test_event_immutable(self):
        ev = GasOverheatEvent(
            device_id="test-01",
            timestamp=datetime.now(IST),
        )
        with pytest.raises(AttributeError):
            ev.severity = "CRITICAL"  # type: ignore[misc]

    def test_event_to_dict(self):
        ts = datetime(2026, 9, 15, 10, 30, 0, tzinfo=IST)
        ev = GasOverheatEvent(
            device_id="test-01",
            timestamp=ts,
            severity="CRITICAL",
            gas_concentration_ppm=35.0,
            tier="CRITICAL",
        )
        d = ev.to_dict()
        assert d["device_id"] == "test-01"
        assert d["severity"] == "CRITICAL"
        assert d["event_type"] == "gas_overheat"
        assert isinstance(d["timestamp"], str)
        assert d["gas_concentration_ppm"] == 35.0

    def test_event_payload_has_all_fields(self):
        ev = GasOverheatEvent(
            device_id="test-01",
            timestamp=datetime.now(IST),
            severity="CRITICAL",
            gas_concentration_ppm=30.0,
            micro_particle_index=50.0,
            internal_panel_temp_c=72.0,
            rate_of_thermal_rise_c_per_min=4.2,
            air_quality_index=7,
            condition_duration_s=0.0,
            tier="CRITICAL",
            threshold_refs={"tier": "CRITICAL", "placeholder": True},
        )
        d = ev.to_dict()
        required = [
            "device_id", "timestamp", "event_type", "severity",
            "gas_concentration_ppm", "micro_particle_index",
            "internal_panel_temp_c", "rate_of_thermal_rise_c_per_min",
            "air_quality_index", "condition_duration_s", "tier",
            "threshold_refs", "synthetic",
        ]
        for key in required:
            assert key in d, f"Missing field: {key}"


# ── Detector: normal readings ────────────────────────────────────────────


class TestNormalReadings:
    """Normal baseline → no event."""

    def test_normal_reading_no_event(self):
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample())
        assert ev is None

    def test_low_temp_low_gas_no_event(self):
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample(
            gas_ppm=5.0, particles=8.0, panel_temp=40.0, rise_rate=0.5,
        ))
        assert ev is None


# ── Detector: CRITICAL (fire precursor) ──────────────────────────────────


class TestCriticalFirePrecursor:
    """CRITICAL fires immediately — no sustained gate."""

    def test_high_rise_and_gas_fires_immediately(self):
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample(
            gas_ppm=GAS_CRITICAL_PPM + 5,
            particles=10.0,
            panel_temp=70.0,
            rise_rate=GAS_CRITICAL_RISE_C_PER_MIN + 1,
        ))
        assert ev is not None
        assert ev.severity == "CRITICAL"
        assert ev.tier == "CRITICAL"
        assert ev.condition_duration_s == 0.0

    def test_high_rise_and_particles_fires_immediately(self):
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample(
            gas_ppm=5.0,
            particles=GAS_CRITICAL_PARTICLE_IDX + 10,
            panel_temp=70.0,
            rise_rate=GAS_CRITICAL_RISE_C_PER_MIN + 0.5,
        ))
        assert ev is not None
        assert ev.severity == "CRITICAL"

    def test_high_rise_but_low_gas_and_particles_no_critical(self):
        """Rise alone without gas/particles doesn't trigger CRITICAL."""
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample(
            gas_ppm=5.0,
            particles=5.0,
            panel_temp=70.0,
            rise_rate=GAS_CRITICAL_RISE_C_PER_MIN + 1,
        ))
        # May trigger WARNING (panel_temp >= 65) but not CRITICAL
        # First sample won't fire WARNING either (needs sustained gate)
        # So no event on the first sample at all
        assert ev is None or ev.severity != "CRITICAL"


# ── Detector: WARNING (sustained gate) ───────────────────────────────────


class TestWarningSustainedGate:
    """WARNING requires sustained duration before firing."""

    def test_warning_not_on_first_sample(self):
        """First overheat sample starts timer, doesn't fire."""
        det = GasOverheatDetector()
        ev = det.evaluate(_make_sample(
            panel_temp=GAS_WARNING_TEMP_C + 5,
        ))
        assert ev is None

    def test_warning_fires_after_sustained_duration(self):
        det = GasOverheatDetector()
        # Generate enough samples to exceed sustained gate
        samples = _make_sustained_samples(
            count=5,
            interval_s=60.0,
            panel_temp=GAS_WARNING_TEMP_C + 5,
            rise_rate=0.5,
        )
        events = [det.evaluate(s) for s in samples]
        # First sample starts timer → None
        assert events[0] is None
        # Some subsequent sample should fire (after 120s)
        fired = [e for e in events if e is not None]
        assert len(fired) >= 1
        assert fired[0].severity == "WARNING"
        assert fired[0].condition_duration_s >= GAS_SUSTAINED_DURATION_S

    def test_warning_gas_particle_combo(self):
        det = GasOverheatDetector()
        samples = _make_sustained_samples(
            count=4,
            interval_s=60.0,
            gas_ppm=GAS_WARNING_PPM + 5,
            particles=GAS_WARNING_PARTICLE_IDX + 10,
            panel_temp=40.0,
        )
        events = [det.evaluate(s) for s in samples]
        fired = [e for e in events if e is not None]
        assert len(fired) >= 1
        assert fired[0].severity == "WARNING"

    def test_warning_resets_on_normal(self):
        """Condition breaking mid-sustain resets the timer."""
        det = GasOverheatDetector()
        t = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # 1st overheat sample — starts timer
        det.evaluate(_make_sample(
            panel_temp=GAS_WARNING_TEMP_C + 5,
            timestamp=t,
        ))
        # 2nd normal sample at +60s — breaks condition
        det.evaluate(_make_sample(
            panel_temp=35.0,
            timestamp=t + timedelta(seconds=60),
        ))
        # 3rd overheat sample at +120s — should restart timer, not fire
        ev = det.evaluate(_make_sample(
            panel_temp=GAS_WARNING_TEMP_C + 5,
            timestamp=t + timedelta(seconds=120),
        ))
        assert ev is None  # timer restarted, not yet sustained


# ── Detector: INFO / watch ───────────────────────────────────────────────


class TestWatchTier:
    """INFO watch tier for elevated temp + rise."""

    def test_watch_fires_after_sustained(self):
        det = GasOverheatDetector()
        samples = _make_sustained_samples(
            count=4,
            interval_s=60.0,
            panel_temp=GAS_WATCH_TEMP_C + 2,
            rise_rate=GAS_WATCH_RISE_C_PER_MIN + 0.5,
            gas_ppm=2.0,
            particles=5.0,
        )
        events = [det.evaluate(s) for s in samples]
        fired = [e for e in events if e is not None]
        assert len(fired) >= 1
        assert fired[0].severity == "INFO"


# ── Detector: benign glitch filtering ────────────────────────────────────


class TestBenignGlitchFilter:
    """Single 1000 ppm spike without thermal rise → no event."""

    def test_spike_without_thermal_rise_no_event(self):
        det = GasOverheatDetector()
        # 1000 ppm spike but normal temp and zero rise
        ev = det.evaluate(_make_sample(
            gas_ppm=1000.0,
            particles=3.0,
            panel_temp=35.0,
            rise_rate=0.0,
        ))
        assert ev is None


# ── Detector: multi-device independence ──────────────────────────────────


class TestMultiDevice:
    """Two devices tracked independently."""

    def test_independent_tracking(self):
        det = GasOverheatDetector()
        t = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # Device A: CRITICAL — fires immediately
        ev_a = det.evaluate(_make_sample(
            device_id="device-A",
            gas_ppm=30.0,
            particles=50.0,
            rise_rate=4.0,
            panel_temp=72.0,
            timestamp=t,
        ))
        # Device B: normal — no event
        ev_b = det.evaluate(_make_sample(
            device_id="device-B",
            gas_ppm=1.0,
            particles=3.0,
            panel_temp=35.0,
            timestamp=t,
        ))
        assert ev_a is not None
        assert ev_a.device_id == "device-A"
        assert ev_b is None


# ── Detector: stale stream reset ─────────────────────────────────────────


class TestStaleStreamReset:
    """No readings for > 5 min → detector resets state."""

    def test_stale_gap_resets_timer(self):
        det = GasOverheatDetector()
        t = datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST)

        # Start overheat condition
        det.evaluate(_make_sample(
            panel_temp=GAS_WARNING_TEMP_C + 5,
            timestamp=t,
        ))
        # Gap of > STALE_TIMEOUT (5 min) — next sample at +10 min
        ev = det.evaluate(_make_sample(
            panel_temp=GAS_WARNING_TEMP_C + 5,
            timestamp=t + timedelta(seconds=GAS_STALE_TIMEOUT_S + 60),
        ))
        # Should have reset — this is a new "first sample", no event
        assert ev is None


# ── Action card integration ──────────────────────────────────────────────


class TestActionCardIntegration:
    """gas_overheat event → valid ActionCard."""

    def test_template_registered(self):
        assert "gas_overheat" in CARD_TEMPLATES

    def test_critical_card_generation(self):
        gen = ActionCardGenerator()
        card = gen.generate_card({
            "event_type": "gas_overheat",
            "device_id": "pune-comp-gas01",
            "timestamp": "2026-09-15T10:30:00+05:30",
            "gas_concentration_ppm": 35.0,
            "micro_particle_index": 55.0,
            "internal_panel_temp_c": 72.0,
            "rate_of_thermal_rise_c_per_min": 4.2,
            "tier": "CRITICAL",
        })
        assert card.severity == "CRITICAL"
        assert "FIRE PRECURSOR" in card.title
        assert "arc flash" in card.do_not.lower()
        assert card.target_role == "plant_manager"
        assert card.physical_rationale  # not empty

    def test_warning_card_generation(self):
        gen = ActionCardGenerator()
        card = gen.generate_card({
            "event_type": "gas_overheat",
            "device_id": "pune-comp-gas01",
            "timestamp": "2026-09-15T10:30:00+05:30",
            "internal_panel_temp_c": 68.0,
            "gas_concentration_ppm": 8.0,
            "micro_particle_index": 12.0,
            "rate_of_thermal_rise_c_per_min": 0.5,
            "tier": "WARNING_TEMP",
        })
        assert card.severity == "WARNING"
        assert "Overheat" in card.title
        assert "thermal imaging" in card.recommended_action.lower()

    def test_card_has_rupee_impact(self):
        gen = ActionCardGenerator()
        card = gen.generate_card({
            "event_type": "gas_overheat",
            "device_id": "pune-comp-gas01",
            "timestamp": "2026-09-15T10:30:00+05:30",
            "tier": "CRITICAL",
        })
        assert "₹" in card.rupee_impact
