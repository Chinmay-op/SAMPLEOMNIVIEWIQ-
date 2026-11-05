"""
tests/test_cooling_malfunction.py — Tests for Cooling Malfunction Rule & Action Card
====================================================================================

Covers:
- Epic OI-135 / Task OI-145
- Spec: Docs/DS/LLD_Four_Core_Features.md §3 (lines 57, 63–65)
- Pure comparison evaluation (`evaluate_cooling_malfunction`)
- Synthetic pairs of rows
- Wire-adapted vs raw telemetry keys
- Streaming detector protocol (`CoolingMalfunctionDetector`)
- Action card generation (`ActionCardGenerator`)
"""

from __future__ import annotations

import datetime
from datetime import timezone
import pytest

from omniview.rules.cooling_malfunction import (
    COOLING_IS_PLACEHOLDER,
    CoolingMalfunctionDetector,
    CoolingMalfunctionEvent,
    evaluate_cooling_malfunction,
)
from omniview.rules.action_cards import ActionCardGenerator, ActionCard


# ═════════════════════════════════════════════════════════════════════════
# 1. Pure Comparison Evaluator
# ═════════════════════════════════════════════════════════════════════════


class TestEvaluateCoolingMalfunction:
    """Tests for evaluate_cooling_malfunction pure function."""

    def test_placeholder_flag(self):
        """Spec requires thresholds to be explicitly labeled as placeholder."""
        assert COOLING_IS_PLACEHOLDER is True

    def test_direct_numeric_breach(self):
        """High power (65 kW > 50 kW) and low temp (45 °C < 100 °C) triggers event."""
        event = evaluate_cooling_malfunction(
            first=65.0,
            second=45.0,
            device_id="ISBM-01",
        )
        assert event is not None
        assert isinstance(event, CoolingMalfunctionEvent)
        assert event.event_type == "cooling_malfunction"
        assert event.device_id == "ISBM-01"
        assert event.severity == "warning"
        assert event.active_power_kw == 65.0
        assert event.cooling_temp_c == 45.0
        assert event.stop_machine is False
        assert event.action_suggestion == "service_or_inspect"
        assert event.details["is_placeholder_threshold"] is True

    def test_no_alert_when_temp_is_normal(self):
        """High power (70 kW) with normal barrel temp (250 °C) is healthy operation."""
        event = evaluate_cooling_malfunction(
            first=70.0,
            second=250.0,
            device_id="ISBM-01",
        )
        assert event is None

    def test_no_alert_when_power_is_low(self):
        """Low power (15 kW) with low temp (40 °C) is machine off/idle — no malfunction."""
        event = evaluate_cooling_malfunction(
            first=15.0,
            second=40.0,
            device_id="ISBM-01",
        )
        assert event is None

    def test_no_alert_when_both_normal(self):
        """Normal power (30 kW) and normal temp (220 °C) — no malfunction."""
        event = evaluate_cooling_malfunction(
            first=30.0,
            second=220.0,
            device_id="ISBM-01",
        )
        assert event is None

    def test_synthetic_pair_of_rows(self):
        """LLD §3 line 65: Pair of rows (electrical + thermal) triggers event."""
        electrical_row = {
            "device_id": "ISBM-LINE-1",
            "timestamp": "2026-08-20T10:15:00+00:00",
            "data": {
                "active_power_kw_total": 72.4,
                "current_a_avg": 220.0,
            },
        }
        cooling_row = {
            "device_id": "ISBM-LINE-1",
            "timestamp": "2026-08-20T10:15:00+00:00",
            "data": {
                "present_value_pv_c": 60.5,
            },
        }

        event = evaluate_cooling_malfunction(electrical_row, cooling_row)
        assert event is not None
        assert event.device_id == "ISBM-LINE-1"
        assert event.active_power_kw == 72.4
        assert event.cooling_temp_c == 60.5
        assert event.stop_machine is False

    def test_wire_adapted_field_names(self):
        """Handles adapted short names (kw and zone_temp_c)."""
        electrical_sample = {
            "device_id": "MFM-01",
            "data": {"kw": 58.0},
        }
        cooling_sample = {
            "device_id": "MFM-01",
            "data": {"zone_temp_c": 50.0},
        }

        event = evaluate_cooling_malfunction(electrical_sample, cooling_sample)
        assert event is not None
        assert event.active_power_kw == 58.0
        assert event.cooling_temp_c == 50.0

    def test_single_composite_row(self):
        """Handles single row containing both power and temperature."""
        composite_sample = {
            "device_id": "ISBM-COMBO",
            "data": {
                "active_power_kw": 80.0,
                "cooling_temp_c": 35.0,
            },
        }
        event = evaluate_cooling_malfunction(composite_sample)
        assert event is not None
        assert event.device_id == "ISBM-COMBO"
        assert event.active_power_kw == 80.0
        assert event.cooling_temp_c == 35.0

    def test_custom_thresholds(self):
        """User can specify custom power and temperature thresholds."""
        # Custom: power threshold 40 kW, temp threshold 80 °C
        event = evaluate_cooling_malfunction(
            first=45.0,
            second=75.0,
            power_threshold_kw=40.0,
            temp_threshold_c=80.0,
        )
        assert event is not None
        assert event.power_threshold_kw == 40.0
        assert event.temp_threshold_c == 80.0

    def test_missing_or_corrupt_data(self):
        """Gracefully returns None on None or corrupt data."""
        assert evaluate_cooling_malfunction(None, None) is None
        assert evaluate_cooling_malfunction({}, {}) is None
        assert evaluate_cooling_malfunction({"data": {"invalid": "text"}}, 50.0) is None


# ═════════════════════════════════════════════════════════════════════════
# 2. Stateful Streaming Detector
# ═════════════════════════════════════════════════════════════════════════


class TestCoolingMalfunctionDetector:
    """Tests for CoolingMalfunctionDetector implementing the Detector protocol."""

    def test_streaming_cross_family_flow(self):
        """Detector consumes electrical reading, then thermal reading, and emits."""
        detector = CoolingMalfunctionDetector(
            power_threshold_kw=50.0,
            temp_threshold_c=100.0,
            cooldown_seconds=60.0,
        )
        base_time = datetime.datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)

        # 1. Electrical reading arrives first -> cached, returns None
        elec_sample = {
            "device_id": "ISBM-01",
            "timestamp": base_time.isoformat(),
            "sensor_type": "electrical",
            "data": {"active_power_kw_total": 62.0},
        }
        result_elec = detector.evaluate(elec_sample)
        assert result_elec is None

        # 2. Thermal reading arrives 10 seconds later -> triggers event
        thermal_sample = {
            "device_id": "ISBM-01",
            "timestamp": (base_time + datetime.timedelta(seconds=10)).isoformat(),
            "sensor_type": "thermal",
            "data": {"present_value_pv_c": 50.0},
        }
        result_thermal = detector.evaluate(thermal_sample)
        assert result_thermal is not None
        assert isinstance(result_thermal, CoolingMalfunctionEvent)
        assert result_thermal.active_power_kw == 62.0
        assert result_thermal.cooling_temp_c == 50.0

    def test_temporal_cache_expiry(self):
        """Stale reading (> 300s old) should not trigger event with a new reading."""
        detector = CoolingMalfunctionDetector(
            power_threshold_kw=50.0,
            temp_threshold_c=100.0,
            cache_window_seconds=120.0,  # 2 minute window
        )
        base_time = datetime.datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)

        # Electrical reading at t=0
        detector.evaluate({
            "device_id": "ISBM-01",
            "timestamp": base_time.isoformat(),
            "data": {"kw": 65.0},
        })

        # Thermal reading at t=10 minutes (600s >> 120s)
        late_thermal = {
            "device_id": "ISBM-01",
            "timestamp": (base_time + datetime.timedelta(minutes=10)).isoformat(),
            "data": {"cooling_temp_c": 40.0},
        }
        event = detector.evaluate(late_thermal)
        assert event is None

    def test_alert_cooldown_suppression(self):
        """Cooldown window suppresses repeated alerts for the same condition."""
        detector = CoolingMalfunctionDetector(
            power_threshold_kw=50.0,
            temp_threshold_c=100.0,
            cooldown_seconds=300.0,
        )
        base_time = datetime.datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)

        # First alert fires
        e1 = detector.evaluate({
            "device_id": "ISBM-01",
            "timestamp": base_time.isoformat(),
            "data": {"kw": 60.0, "cooling_temp_c": 40.0},
        })
        assert e1 is not None

        # Reading 30 seconds later (within 300s cooldown) -> suppressed
        e2 = detector.evaluate({
            "device_id": "ISBM-01",
            "timestamp": (base_time + datetime.timedelta(seconds=30)).isoformat(),
            "data": {"kw": 62.0, "cooling_temp_c": 42.0},
        })
        assert e2 is None

        # Reading 350 seconds later (after cooldown) -> fires again
        e3 = detector.evaluate({
            "device_id": "ISBM-01",
            "timestamp": (base_time + datetime.timedelta(seconds=350)).isoformat(),
            "data": {"kw": 63.0, "cooling_temp_c": 41.0},
        })
        assert e3 is not None

    def test_reset(self):
        """reset() clears device cache."""
        detector = CoolingMalfunctionDetector()
        detector.evaluate({
            "device_id": "ISBM-01",
            "data": {"kw": 70.0},
        })
        assert len(detector._state) == 1
        detector.reset()
        assert len(detector._state) == 0


# ═════════════════════════════════════════════════════════════════════════
# 3. Action Card Generation
# ═════════════════════════════════════════════════════════════════════════


class TestActionCardCoolingMalfunction:
    """Tests for ActionCardGenerator integration with cooling_malfunction events."""

    def test_card_generation_from_dict(self):
        """Generates card with 'service or inspect' and 'do NOT stop the machine'."""
        gen = ActionCardGenerator()

        event_payload = {
            "event_type": "cooling_malfunction",
            "device_id": "pune-isbm-01",
            "active_power_kw": 64.5,
            "cooling_temp_c": 52.0,
            "timestamp": "2026-08-20T11:00:00+05:30",
        }

        card = gen.generate_card(event_payload)

        assert isinstance(card, ActionCard)
        assert card.event_type == "cooling_malfunction"
        assert card.severity == "WARNING"
        assert "Cooling Malfunction" in card.title
        assert "❄️" in card.title or "🧊" in card.title

        # Check spec requirements: says service or inspect, does NOT stop machine
        assert "service or inspect" in card.recommended_action.lower()
        assert "do not stop the machine" in card.do_not.lower()
        assert card.target_role == "maintenance_engineer"
        assert "₹" in card.rupee_impact

    def test_card_generation_from_event_dataclass(self):
        """Generate card directly from CoolingMalfunctionEvent.to_dict()."""
        event = evaluate_cooling_malfunction(
            first=66.0,
            second=48.0,
            device_id="ISBM-02",
        )
        assert event is not None

        gen = ActionCardGenerator()
        card = gen.generate_card(event.to_dict())

        assert card.event_type == "cooling_malfunction"
        assert card.device_id == "ISBM-02"
        assert "service or inspect" in card.recommended_action.lower()
        assert "do not stop the machine" in card.do_not.lower()
