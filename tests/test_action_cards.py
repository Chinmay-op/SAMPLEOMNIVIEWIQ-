"""
Tests for omniview.rules.action_cards — OI-69
================================================

Unit tests for the ActionCard dataclass and ActionCardGenerator.
All tests are self-contained — no database or MQTT required.

Run::

    pytest tests/test_action_cards.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from omniview.rules.action_cards import (
    ActionCard,
    ActionCardGenerator,
    CARD_TEMPLATES,
    _generate_card_id,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ═════════════════════════════════════════════════════════════════════════
# ActionCard dataclass
# ═════════════════════════════════════════════════════════════════════════


class TestActionCardDataclass:
    """Test ActionCard creation, immutability, and serialization."""

    def test_create_minimal_card(self):
        """ActionCard can be created with required fields only."""
        card = ActionCard(
            card_id="abc123",
            timestamp=datetime.now(IST),
            event_type="test_event",
            severity="INFO",
            title="Test Card",
            summary="This is a test.",
            recommended_action="Do something.",
        )
        assert card.card_id == "abc123"
        assert card.severity == "INFO"
        assert card.do_not == ""  # default
        assert card.target_role == "plant_manager"  # default

    def test_card_is_frozen(self):
        """ActionCard is immutable (frozen dataclass)."""
        card = ActionCard(
            card_id="abc123",
            timestamp=datetime.now(IST),
            event_type="test",
            severity="INFO",
            title="Test",
            summary="Test",
            recommended_action="Test",
        )
        with pytest.raises(AttributeError):
            card.severity = "CRITICAL"  # type: ignore[misc]

    def test_to_dict_serialization(self):
        """to_dict() produces JSON-safe dict with string timestamp."""
        ts = datetime(2026, 8, 20, 10, 30, 0, tzinfo=IST)
        card = ActionCard(
            card_id="abc123",
            timestamp=ts,
            event_type="test",
            severity="WARNING",
            title="Test Card",
            summary="Summary",
            recommended_action="Action",
            rupee_impact="₹1,000",
        )
        d = card.to_dict()
        assert d["card_id"] == "abc123"
        assert isinstance(d["timestamp"], str)
        assert "2026-08-20" in d["timestamp"]
        assert d["rupee_impact"] == "₹1,000"

    def test_default_sensor_readings_empty_dict(self):
        """sensor_readings defaults to empty dict, not shared mutable."""
        card1 = ActionCard(
            card_id="a",
            timestamp=datetime.now(IST),
            event_type="t",
            severity="INFO",
            title="T",
            summary="S",
            recommended_action="A",
        )
        card2 = ActionCard(
            card_id="b",
            timestamp=datetime.now(IST),
            event_type="t",
            severity="INFO",
            title="T",
            summary="S",
            recommended_action="A",
        )
        assert card1.sensor_readings == {}
        assert card2.sensor_readings == {}
        # Frozen, so we can't mutate — this is correct behavior


# ═════════════════════════════════════════════════════════════════════════
# Card ID generation
# ═════════════════════════════════════════════════════════════════════════


class TestCardIdGeneration:
    """Test deterministic card ID generation."""

    def test_deterministic(self):
        """Same inputs produce same card ID."""
        ts = datetime(2026, 8, 20, 10, 0, 0, tzinfo=IST)
        id1 = _generate_card_id("md_nearmiss", "device-01", ts)
        id2 = _generate_card_id("md_nearmiss", "device-01", ts)
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        """Different inputs produce different card IDs."""
        ts = datetime(2026, 8, 20, 10, 0, 0, tzinfo=IST)
        id1 = _generate_card_id("md_nearmiss", "device-01", ts)
        id2 = _generate_card_id("lazy_idle", "device-01", ts)
        id3 = _generate_card_id("md_nearmiss", "device-02", ts)
        assert id1 != id2
        assert id1 != id3


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — MD Near-Miss
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardMdNearmiss:
    """Test MD near-miss action card generation."""

    def setup_method(self):
        self.gen = ActionCardGenerator()
        self.event = {
            "event_type": "md_nearmiss",
            "device_id": "pune-comp-mfm384",
            "timestamp": "2026-08-20T10:30:00+05:30",
            "kva": 478.5,
            "md_proximity_percent": 95.7,
            "contract_kva": 500.0,
        }

    def test_generates_card(self):
        """MD near-miss event produces a valid ActionCard."""
        card = self.gen.generate_card(self.event)
        assert isinstance(card, ActionCard)
        assert card.event_type == "md_nearmiss"
        assert card.severity == "CRITICAL"

    def test_correct_target_role(self):
        """MD near-miss cards target the plant manager."""
        card = self.gen.generate_card(self.event)
        assert card.target_role == "plant_manager"

    def test_rupee_impact_present(self):
        """MD near-miss card includes ₹ penalty calculation."""
        card = self.gen.generate_card(self.event)
        assert "₹" in card.rupee_impact
        assert "penalty" in card.rupee_impact.lower()

    def test_urgency_window(self):
        """MD near-miss card has urgency window referencing billing."""
        card = self.gen.generate_card(self.event)
        assert "min" in card.urgency_window.lower()

    def test_do_not_warns_against_shutdown(self):
        """MD near-miss anti-action warns against compressor shutdown."""
        card = self.gen.generate_card(self.event)
        assert "shut down" in card.do_not.lower() or "shutdown" in card.do_not.lower()


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — Lazy Idle
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardLazyIdle:
    """Test lazy-idle action card generation."""

    def setup_method(self):
        self.gen = ActionCardGenerator()
        self.event = {
            "event_type": "lazy_idle",
            "device_id": "pune-isbm-mfm384",
            "timestamp": "2026-08-20T14:15:00+05:30",
            "current_a_avg": 5.2,
            "barrel_temp_c": 248.0,
            "active_power_kw_total": 3.1,
        }

    def test_generates_card(self):
        """Lazy-idle event produces a valid ActionCard."""
        card = self.gen.generate_card(self.event)
        assert isinstance(card, ActionCard)
        assert card.event_type == "lazy_idle"
        assert card.severity == "WARNING"

    def test_correct_target_role(self):
        """Lazy-idle cards target the maintenance engineer."""
        card = self.gen.generate_card(self.event)
        assert card.target_role == "maintenance_engineer"

    def test_anti_action_warns_thermal_shock(self):
        """Lazy-idle anti-action warns about thermal shock."""
        card = self.gen.generate_card(self.event)
        assert "thermal" in card.do_not.lower() or "barrel" in card.do_not.lower()

    def test_rupee_impact_energy_waste(self):
        """Lazy-idle card quantifies energy waste in ₹."""
        card = self.gen.generate_card(self.event)
        assert "₹" in card.rupee_impact
        assert "kwh" in card.rupee_impact.lower() or "kWh" in card.rupee_impact


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — Leak Proxy
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardLeakProxy:
    """Test pressure-decay leak proxy action card generation."""

    def setup_method(self):
        self.gen = ActionCardGenerator()
        self.event = {
            "event_type": "leak_proxy",
            "device_id": "pune-comp-wika01",
            "timestamp": "2026-08-20T16:05:00+05:30",
            "pressure_bar": 25.3,
            "decay_rate_bar_per_min": 0.8,
        }

    def test_generates_card(self):
        """Leak proxy event produces a valid ActionCard."""
        card = self.gen.generate_card(self.event)
        assert isinstance(card, ActionCard)
        assert card.event_type == "leak_proxy"
        assert card.severity == "WARNING"

    def test_pressure_info_in_summary(self):
        """Leak proxy card includes pressure decay rate in summary."""
        card = self.gen.generate_card(self.event)
        assert "bar" in card.summary.lower()
        assert "decay" in card.summary.lower() or "0.8" in card.summary

    def test_anti_action_warns_against_setpoint_increase(self):
        """Leak proxy anti-action warns against masking with higher setpoint."""
        card = self.gen.generate_card(self.event)
        assert "setpoint" in card.do_not.lower() or "increase" in card.do_not.lower()


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — Critical Vibration
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardCriticalVibration:
    """Test critical vibration action card generation."""

    def setup_method(self):
        self.gen = ActionCardGenerator()
        self.event = {
            "event_type": "critical_vibration",
            "device_id": "pune-comp-vib01",
            "timestamp": "2026-08-20T11:00:00+05:30",
            "z_rms": 22.5,
            "iso_zone": "ZONE_D",
        }

    def test_generates_critical_card(self):
        """Critical vibration produces a CRITICAL ActionCard."""
        card = self.gen.generate_card(self.event)
        assert isinstance(card, ActionCard)
        assert card.severity == "CRITICAL"

    def test_recommends_staggered_deceleration(self):
        """Critical vibration recommends staggered decel, not hard stop."""
        card = self.gen.generate_card(self.event)
        assert "stagger" in card.recommended_action.lower() or "deceleration" in card.recommended_action.lower()

    def test_anti_action_warns_hard_stop(self):
        """Critical vibration anti-action warns against hard stop."""
        card = self.gen.generate_card(self.event)
        assert "hard" in card.do_not.lower() or "immediately" in card.do_not.lower()


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — Maintenance Risk (PdM)
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardMaintenanceRisk:
    """Test PdM maintenance risk action card generation."""

    def setup_method(self):
        self.gen = ActionCardGenerator()
        self.event = {
            "event_type": "maintenance_risk",
            "device_id": "pune-comp-vib01",
            "timestamp": "2026-08-20T09:00:00+05:30",
            "hi_score": 45,
            "equipment_name": "Air Compressor",
            "estimated_days_to_failure": 10,
        }

    def test_generates_warning_card(self):
        """Maintenance risk produces a WARNING ActionCard."""
        card = self.gen.generate_card(self.event)
        assert isinstance(card, ActionCard)
        assert card.severity == "WARNING"

    def test_target_maintenance_engineer(self):
        """Maintenance risk targets the maintenance engineer."""
        card = self.gen.generate_card(self.event)
        assert card.target_role == "maintenance_engineer"

    def test_includes_hi_score(self):
        """Maintenance risk card references HI score."""
        card = self.gen.generate_card(self.event)
        assert "45" in card.summary or "45/100" in card.summary


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — Unknown event
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardUnknown:
    """Test behavior with unknown/unrecognised event types."""

    def setup_method(self):
        self.gen = ActionCardGenerator()

    def test_unknown_event_returns_generic_card(self):
        """Unknown event type produces a generic INFO card, not an error."""
        card = self.gen.generate_card({
            "event_type": "alien_invasion",
            "device_id": "ufo-01",
        })
        assert isinstance(card, ActionCard)
        assert card.severity == "INFO"
        assert "alien_invasion" in card.summary or "Alien Invasion" in card.title

    def test_missing_event_type_falls_back(self):
        """Missing event_type and scenario_label produces generic card."""
        card = self.gen.generate_card({"device_id": "test-01"})
        assert isinstance(card, ActionCard)
        assert card.event_type == "unknown"


# ═════════════════════════════════════════════════════════════════════════
# ActionCardGenerator — scenario_label compatibility
# ═════════════════════════════════════════════════════════════════════════


class TestScenarioLabelCompat:
    """Test that scenario_label (from OI-55 seed) works as event source."""

    def setup_method(self):
        self.gen = ActionCardGenerator()

    def test_scenario_label_maps_to_event_type(self):
        """scenario_label is accepted as alternative to event_type."""
        card = self.gen.generate_card({
            "scenario_label": "md_nearmiss",
            "device_id": "pune-comp-mfm384",
            "kva": 475,
        })
        assert card.event_type == "md_nearmiss"
        assert card.severity == "CRITICAL"

    def test_event_type_takes_precedence(self):
        """If both event_type and scenario_label given, event_type wins."""
        card = self.gen.generate_card({
            "event_type": "lazy_idle",
            "scenario_label": "md_nearmiss",
            "device_id": "test-01",
        })
        assert card.event_type == "lazy_idle"


# ═════════════════════════════════════════════════════════════════════════
# generate_cards_from_alerts — batch processing
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateCardsFromAlerts:
    """Test batch card generation and deduplication."""

    def setup_method(self):
        self.gen = ActionCardGenerator()

    def test_batch_generation(self):
        """Batch processing generates one card per alert."""
        alerts = [
            {"event_type": "md_nearmiss", "device_id": "d1", "timestamp": "2026-08-20T10:00:00+05:30"},
            {"event_type": "lazy_idle", "device_id": "d2", "timestamp": "2026-08-20T14:00:00+05:30"},
        ]
        cards = self.gen.generate_cards_from_alerts(alerts)
        assert len(cards) == 2
        assert cards[0].event_type == "md_nearmiss"
        assert cards[1].event_type == "lazy_idle"

    def test_deduplication(self):
        """Duplicate alerts (same event+device+timestamp) are deduplicated."""
        alert = {"event_type": "md_nearmiss", "device_id": "d1", "timestamp": "2026-08-20T10:00:00+05:30"}
        cards = self.gen.generate_cards_from_alerts([alert, alert, alert])
        assert len(cards) == 1

    def test_empty_input(self):
        """Empty alert list returns empty card list."""
        cards = self.gen.generate_cards_from_alerts([])
        assert cards == []

    def test_malformed_alert_skipped(self):
        """Malformed alerts are skipped, not crash-causing."""
        alerts = [
            {"event_type": "md_nearmiss", "device_id": "d1", "timestamp": "2026-08-20T10:00:00+05:30"},
            None,  # type: ignore[list-item]  # intentionally bad
        ]
        # Should not crash, may skip the None
        cards = self.gen.generate_cards_from_alerts(alerts)
        assert len(cards) >= 1


# ═════════════════════════════════════════════════════════════════════════
# Template coverage
# ═════════════════════════════════════════════════════════════════════════


class TestTemplateCoverage:
    """Verify all expected templates are registered."""

    def test_all_templates_registered(self):
        """CARD_TEMPLATES has entries for all registered event types."""
        expected = {
            "md_nearmiss",
            "lazy_idle",
            "leak_proxy",
            "critical_vibration",
            "maintenance_risk",
            "gas_overheat",
            "energy_wastage",
            "predictive_maintenance",
            "cooling_malfunction",
        }
        assert set(CARD_TEMPLATES.keys()) == expected

    def test_all_templates_callable(self):
        """Every template is a callable."""
        for name, fn in CARD_TEMPLATES.items():
            assert callable(fn), f"Template {name} is not callable"

    def test_all_templates_return_required_fields(self):
        """Every template returns a dict with required card fields."""
        required = {"severity", "title", "summary", "recommended_action"}
        for name, fn in CARD_TEMPLATES.items():
            result = fn({"device_id": "test", "kva": 400})
            for key in required:
                assert key in result, f"Template {name} missing field {key}"


# ═════════════════════════════════════════════════════════════════════════
# OI-153: Action Card Templates for Feature 2 Events
# ═════════════════════════════════════════════════════════════════════════


class TestFeature2ActionCardTemplates:
    """Acceptance criteria tests for OI-153 Feature 2 Action Cards."""

    def setup_method(self):
        self.gen = ActionCardGenerator()

    def test_maintenance_risk_card_required_fields_and_no_actuation(self):
        """Verify maintenance_risk card matches OI-153 AC and contains no actuation commands."""
        event = {
            "event_type": "maintenance_risk",
            "device_id": "pune-comp-vib01",
            "timestamp": "2026-08-20T10:00:00+05:30",
            "payload": {
                "health_index": 42.5,
                "risk_tier": "high",
                "contributing_features": {
                    "z_rms_velocity_mm_sec": {
                        "slope_7d": 0.0821,
                        "z_score": 2.45,
                        "direction": "up",
                    }
                },
            },
        }

        card = self.gen.generate_card(event)

        # 1. Exact Title per OI-153 AC
        assert card.title == "🛠️ Maintenance Risk — Equipment Health Index Degraded"

        # 2. Summary reports HI score, risk tier, and primary drifting feature
        assert "42" in card.summary or "43" in card.summary
        assert "high" in card.summary.lower()
        assert "z_rms_velocity_mm_sec" in card.summary or "7-day slope" in card.summary

        # 3. Recommended Action matches inspection task
        assert "Schedule bearing lubrication and shaft alignment check at shift end" in card.recommended_action

        # 4. Do Not contains safety guardrail against mid-cycle emergency stop
        assert "Do NOT trigger emergency stop mid-cycle unless vibration exceeds ISO Zone D trip threshold" in card.do_not

        # 5. Role and Severity
        assert card.target_role == "maintenance_engineer"
        assert card.severity in ("WARNING", "CRITICAL")

        # 6. Verify all required card fields are populated
        required_fields = [
            "card_id", "timestamp", "event_type", "severity", "title",
            "summary", "recommended_action", "do_not", "rupee_impact",
            "urgency_window", "target_role", "device_id",
        ]
        for field in required_fields:
            val = getattr(card, field)
            assert val is not None and str(val).strip() != "", f"Field {field} is empty or None"

        # 7. Strictly HITL / advisory: verify NO automated actuation commands
        forbidden_actuations = [
            "trip breaker",
            "open breaker",
            "remote trip",
            "emergency stop immediately",
            "scada override",
            "automated shutdown",
        ]
        for phrase in forbidden_actuations:
            assert phrase not in card.recommended_action.lower(), f"Actuation command found: {phrase}"

    def test_cooling_malfunction_card_required_fields_and_no_actuation(self):
        """Verify cooling_malfunction card matches OI-153 AC and contains no actuation commands."""
        event = {
            "event_type": "cooling_malfunction",
            "device_id": "pune-isbm-01",
            "active_power_kw": 68.4,
            "cooling_temp_c": 36.5,
            "timestamp": "2026-08-20T11:30:00+05:30",
        }

        card = self.gen.generate_card(event)

        # 1. Exact Title per OI-153 AC
        assert card.title == "❄️ Cooling Malfunction — Thermal/Energy Mismatch Detected"

        # 2. Summary explains active electrical work alongside cold coolant/barrel stream
        assert "active electrical work" in card.summary.lower()
        assert "cold coolant/barrel stream" in card.summary.lower()
        assert "68.4" in card.summary
        assert "36.5" in card.summary

        # 3. Recommended Action per OI-153 AC
        assert "Inspect chiller circulation pump, inlet valves, and temperature probe wiring." in card.recommended_action

        # 4. Do Not per OI-153 AC
        assert "Do NOT restart machine under load until coolant circulation is verified." in card.do_not
        assert "do not stop the machine" in card.do_not.lower()

        # 5. Role and Severity
        assert card.target_role == "maintenance_engineer"
        assert card.severity == "WARNING"

        # 6. Verify all required card fields are populated
        required_fields = [
            "card_id", "timestamp", "event_type", "severity", "title",
            "summary", "recommended_action", "do_not", "rupee_impact",
            "urgency_window", "target_role", "device_id",
        ]
        for field in required_fields:
            val = getattr(card, field)
            assert val is not None and str(val).strip() != "", f"Field {field} is empty or None"

        # 7. Strictly HITL / advisory: verify NO automated actuation commands
        forbidden_actuations = [
            "trip breaker",
            "open breaker",
            "remote trip",
            "emergency stop",
            "scada override",
            "automated shutdown",
        ]
        for phrase in forbidden_actuations:
            assert phrase not in card.recommended_action.lower(), f"Actuation command found: {phrase}"

    def test_maintenance_risk_from_layer3_build_event(self):
        """Integration with build_maintenance_risk_event produces compliant action card."""
        from omniview.rules.predictive_maintenance import (
            ContributingFeature,
            HealthIndexResult,
            build_maintenance_risk_event,
        )

        hi_res = HealthIndexResult(
            machine_id="compressor-01",
            health_index=38.0,
            risk_tier="high",
            confidence_stage="calibrated",
            avg_z=2.8,
            signal_count=5,
            gap_flagged=False,
            contributing_features=[
                ContributingFeature(
                    signal="vibration_rms_velocity",
                    slope_value=0.0821,
                    z_score=2.85,
                    direction="up",
                    prior_mean=0.01,
                    prior_std=0.025,
                )
            ],
            date="2026-08-20",
        )

        layer3_event = build_maintenance_risk_event(hi_res, device_id="pune-comp-01")
        card = self.gen.generate_card(layer3_event)

        assert card.title == "🛠️ Maintenance Risk — Equipment Health Index Degraded"
        assert "38" in card.summary
        assert "high" in card.summary.lower()
        assert "vibration_rms_velocity" in card.summary
        assert "Schedule bearing lubrication and shaft alignment check at shift end" in card.recommended_action
        assert "Do NOT trigger emergency stop mid-cycle unless vibration exceeds ISO Zone D trip threshold" in card.do_not
        assert "open breaker" not in card.recommended_action.lower()

    def test_cooling_malfunction_from_rule_evaluator(self):
        """Integration with evaluate_cooling_malfunction produces compliant action card."""
        from omniview.rules.cooling_malfunction import evaluate_cooling_malfunction

        event = evaluate_cooling_malfunction(
            first=72.0,
            second=35.0,
            device_id="ISBM-01",
        )
        assert event is not None

        card = self.gen.generate_card(event.to_dict())
        assert card.title == "❄️ Cooling Malfunction — Thermal/Energy Mismatch Detected"
        assert "72.0" in card.summary
        assert "35.0" in card.summary
        assert "Inspect chiller circulation pump, inlet valves, and temperature probe wiring." in card.recommended_action
        assert "Do NOT restart machine under load until coolant circulation is verified." in card.do_not
        assert "trip breaker" not in card.recommended_action.lower()
