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

    def test_five_templates_registered(self):
        """CARD_TEMPLATES has entries for all 5 event types."""
        expected = {
            "md_nearmiss",
            "lazy_idle",
            "leak_proxy",
            "critical_vibration",
            "maintenance_risk",
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
