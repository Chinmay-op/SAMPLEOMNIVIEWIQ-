"""
Tests for OI-71 — Alert Routing Stub
========================================

All tests are self-contained — no TSDB, MQTT, or network required.
Tests cover:
  - Routing table completeness and structure
  - Channel lookup for all severity+role combos
  - LogChannel, EmailChannel, WebhookChannel stub emission
  - AlertRouter.route() dispatch correctness
  - AlertRouter.route_batch() batch processing
  - Feature flag (enabled/disabled)
  - Routing table documentation helper
  - RoutingResult serialization
  - Edge cases (unknown severity, unknown role)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from omniview.dashboard.alert_router import (
    AlertChannel,
    AlertRouter,
    EmailChannel,
    LogChannel,
    RoutingResult,
    RoutingRule,
    ROUTING_TABLE,
    WebhookChannel,
    get_routing_table_markdown,
    lookup_channels,
)
from omniview.rules.action_cards import ActionCard, ActionCardGenerator

IST = timezone(timedelta(hours=5, minutes=30))


# ── Test fixtures ────────────────────────────────────────────────────────


def _make_card(
    event_type: str = "md_nearmiss",
    severity: str = "CRITICAL",
    target_role: str = "plant_manager",
    device_id: str = "pune-comp-mfm384",
    **kwargs,
) -> ActionCard:
    """Create a minimal ActionCard for testing."""
    ts = kwargs.pop("timestamp", datetime(2026, 8, 21, 10, 30, tzinfo=IST))
    return ActionCard(
        card_id=f"test-{event_type}-{device_id}",
        timestamp=ts,
        event_type=event_type,
        severity=severity,
        title=f"Test {event_type}",
        summary=f"Test summary for {event_type}",
        recommended_action="Test action",
        do_not="Test do not",
        rupee_impact="₹1,000",
        urgency_window="~4 min",
        target_role=target_role,
        device_id=device_id,
        sensor_readings={"kva": 478.5},
        physical_rationale="Test rationale",
        source_event={"event_type": event_type},
    )


def _make_card_from_generator(event_type: str) -> ActionCard:
    """Generate a card using the real ActionCardGenerator."""
    gen = ActionCardGenerator()
    events = {
        "md_nearmiss": {
            "event_type": "md_nearmiss",
            "device_id": "pune-comp-mfm384",
            "kva": 478.5,
            "md_proximity_percent": 95.7,
            "timestamp": "2026-08-21T10:30:00+05:30",
        },
        "lazy_idle": {
            "event_type": "lazy_idle",
            "device_id": "pune-isbm-mfm384",
            "current_a_avg": 5.2,
            "barrel_temp_c": 210.0,
            "timestamp": "2026-08-21T11:00:00+05:30",
        },
        "leak_proxy": {
            "event_type": "leak_proxy",
            "device_id": "pune-comp-press01",
            "pressure_bar": 6.2,
            "decay_rate_bar_per_min": 0.15,
            "timestamp": "2026-08-21T11:15:00+05:30",
        },
        "critical_vibration": {
            "event_type": "critical_vibration",
            "device_id": "pune-comp-vib01",
            "z_rms": 22.5,
            "iso_zone": "ZONE_D",
            "timestamp": "2026-08-21T11:30:00+05:30",
        },
        "maintenance_risk": {
            "event_type": "maintenance_risk",
            "device_id": "pune-comp-vib01",
            "hi_score": 45,
            "estimated_days_to_failure": 10,
            "timestamp": "2026-08-21T12:00:00+05:30",
        },
    }
    return gen.generate_card(events[event_type])


# ═══════════════════════════════════════════════════════════════════════
#  Routing Table Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRoutingTable:
    """Verify the routing table structure and completeness."""

    def test_table_is_tuple(self):
        """ROUTING_TABLE should be an immutable tuple of RoutingRule."""
        assert isinstance(ROUTING_TABLE, tuple)
        assert all(isinstance(r, RoutingRule) for r in ROUTING_TABLE)

    def test_table_has_all_three_severities(self):
        """Table must cover CRITICAL, WARNING, INFO."""
        severities = {r.severity for r in ROUTING_TABLE}
        assert "CRITICAL" in severities
        assert "WARNING" in severities
        assert "INFO" in severities

    def test_table_has_all_three_personas(self):
        """Table must cover operator, maintenance_engineer, plant_manager."""
        roles = {r.target_role for r in ROUTING_TABLE}
        assert "operator" in roles
        assert "maintenance_engineer" in roles
        assert "plant_manager" in roles

    def test_every_rule_has_at_least_log(self):
        """Every routing rule must include LOG as a channel (audit trail)."""
        for rule in ROUTING_TABLE:
            assert AlertChannel.LOG in rule.channels, (
                f"Rule ({rule.severity}, {rule.target_role}) missing LOG channel"
            )

    def test_critical_rules_include_webhook(self):
        """CRITICAL rules should include WEBHOOK for push alerts."""
        critical_rules = [r for r in ROUTING_TABLE if r.severity == "CRITICAL"]
        for rule in critical_rules:
            assert AlertChannel.WEBHOOK in rule.channels, (
                f"CRITICAL rule for {rule.target_role} missing WEBHOOK"
            )

    def test_warning_maintenance_includes_email(self):
        """WARNING → maintenance_engineer should include EMAIL."""
        rule = next(
            r for r in ROUTING_TABLE
            if r.severity == "WARNING" and r.target_role == "maintenance_engineer"
        )
        assert AlertChannel.EMAIL in rule.channels

    def test_info_is_log_only(self):
        """INFO rules should be LOG only — no email/webhook spam."""
        info_rules = [r for r in ROUTING_TABLE if r.severity == "INFO"]
        for rule in info_rules:
            assert rule.channels == (AlertChannel.LOG,), (
                f"INFO rule for {rule.target_role} should be LOG only"
            )

    def test_every_rule_has_description(self):
        """Every rule should have a non-empty description for documentation."""
        for rule in ROUTING_TABLE:
            assert rule.description, (
                f"Rule ({rule.severity}, {rule.target_role}) missing description"
            )

    def test_no_duplicate_rules(self):
        """No two rules should have the same (severity, target_role) pair."""
        keys = [(r.severity, r.target_role) for r in ROUTING_TABLE]
        assert len(keys) == len(set(keys)), "Duplicate routing rules found"


# ═══════════════════════════════════════════════════════════════════════
#  Channel Lookup Tests
# ═══════════════════════════════════════════════════════════════════════


class TestLookupChannels:
    """Verify the lookup function returns correct channels."""

    def test_critical_plant_manager(self):
        channels = lookup_channels("CRITICAL", "plant_manager")
        assert AlertChannel.WEBHOOK in channels
        assert AlertChannel.LOG in channels

    def test_warning_maintenance(self):
        channels = lookup_channels("WARNING", "maintenance_engineer")
        assert AlertChannel.EMAIL in channels
        assert AlertChannel.LOG in channels

    def test_warning_operator_log_only(self):
        channels = lookup_channels("WARNING", "operator")
        assert channels == (AlertChannel.LOG,)

    def test_info_any_role_log_only(self):
        for role in ("plant_manager", "maintenance_engineer", "operator"):
            channels = lookup_channels("INFO", role)
            assert channels == (AlertChannel.LOG,), (
                f"INFO/{role} should be LOG only"
            )

    def test_unknown_severity_falls_back_to_log(self):
        channels = lookup_channels("UNKNOWN", "plant_manager")
        assert channels == (AlertChannel.LOG,)

    def test_unknown_role_falls_back_to_log(self):
        channels = lookup_channels("CRITICAL", "unknown_role")
        assert channels == (AlertChannel.LOG,)


# ═══════════════════════════════════════════════════════════════════════
#  LogChannel Tests
# ═══════════════════════════════════════════════════════════════════════


class TestLogChannel:
    """Verify LogChannel emits structured log entries."""

    def test_send_returns_routing_result(self):
        channel = LogChannel()
        card = _make_card()
        result = channel.send(card)

        assert isinstance(result, RoutingResult)
        assert result.channel == AlertChannel.LOG
        assert result.status == "sent"
        assert result.card_id == card.card_id
        assert result.target_role == card.target_role

    def test_critical_logs_at_warning_level(self, caplog):
        channel = LogChannel()
        card = _make_card(severity="CRITICAL")

        with caplog.at_level(logging.WARNING):
            channel.send(card)

        assert any("ALERT ROUTED [LOG]" in r.message for r in caplog.records)

    def test_warning_logs_at_info_level(self, caplog):
        channel = LogChannel()
        card = _make_card(severity="WARNING", event_type="lazy_idle",
                         target_role="maintenance_engineer")

        with caplog.at_level(logging.INFO):
            channel.send(card)

        assert any("ALERT ROUTED [LOG]" in r.message for r in caplog.records)

    def test_log_entry_is_valid_json(self, caplog):
        channel = LogChannel()
        card = _make_card()

        with caplog.at_level(logging.WARNING):
            channel.send(card)

        # Find the log message and extract JSON
        for record in caplog.records:
            if "ALERT ROUTED [LOG]" in record.message:
                json_str = record.message.split("ALERT ROUTED [LOG] ")[1]
                parsed = json.loads(json_str)
                assert parsed["alert_routing"] == "LOG"
                assert parsed["card_id"] == card.card_id
                assert parsed["severity"] == "CRITICAL"
                break
        else:
            pytest.fail("No LOG routing record found")


# ═══════════════════════════════════════════════════════════════════════
#  EmailChannel Tests
# ═══════════════════════════════════════════════════════════════════════


class TestEmailChannel:
    """Verify EmailChannel logs mock email dispatch."""

    def test_send_returns_routing_result(self):
        channel = EmailChannel()
        card = _make_card(
            severity="WARNING",
            event_type="lazy_idle",
            target_role="maintenance_engineer",
        )
        result = channel.send(card)

        assert result.channel == AlertChannel.EMAIL
        assert result.status == "sent"
        assert "maintenance@example.com" in result.detail

    def test_correct_recipient_for_plant_manager(self):
        channel = EmailChannel()
        card = _make_card(target_role="plant_manager")
        result = channel.send(card)
        assert "plant.manager@example.com" in result.detail

    def test_correct_recipient_for_operator(self):
        channel = EmailChannel()
        card = _make_card(target_role="operator")
        result = channel.send(card)
        assert "floor.ops@example.com" in result.detail

    def test_custom_recipient_map(self):
        custom = {"plant_manager": "boss@factory.com"}
        channel = EmailChannel(recipient_map=custom)
        card = _make_card(target_role="plant_manager")
        result = channel.send(card)
        assert "boss@factory.com" in result.detail

    def test_unknown_role_gets_fallback_email(self):
        channel = EmailChannel()
        card = _make_card(target_role="unknown_role")
        result = channel.send(card)
        assert "unknown_role@example.com" in result.detail

    def test_subject_includes_severity(self):
        channel = EmailChannel()
        card = _make_card(severity="CRITICAL")
        result = channel.send(card)
        assert "[CRITICAL]" in result.detail

    def test_email_log_is_valid_json(self, caplog):
        channel = EmailChannel()
        card = _make_card(severity="WARNING", target_role="maintenance_engineer")

        with caplog.at_level(logging.INFO):
            channel.send(card)

        for record in caplog.records:
            if "ALERT ROUTED [EMAIL]" in record.message:
                json_str = record.message.split("ALERT ROUTED [EMAIL] ")[1]
                parsed = json.loads(json_str)
                assert parsed["alert_routing"] == "EMAIL"
                assert "@" in parsed["to"]
                break
        else:
            pytest.fail("No EMAIL routing record found")


# ═══════════════════════════════════════════════════════════════════════
#  WebhookChannel Tests
# ═══════════════════════════════════════════════════════════════════════


class TestWebhookChannel:
    """Verify WebhookChannel logs mock POST."""

    def test_send_returns_routing_result(self):
        channel = WebhookChannel()
        card = _make_card()
        result = channel.send(card)

        assert result.channel == AlertChannel.WEBHOOK
        assert result.status == "sent"
        assert "POST" in result.detail

    def test_default_url(self):
        channel = WebhookChannel()
        card = _make_card()
        result = channel.send(card)
        assert "localhost:9999" in result.detail

    def test_custom_url(self):
        channel = WebhookChannel(url="https://hooks.company.com/alert")
        card = _make_card()
        result = channel.send(card)
        assert "hooks.company.com" in result.detail

    def test_webhook_log_contains_payload(self, caplog):
        channel = WebhookChannel()
        card = _make_card()

        with caplog.at_level(logging.INFO):
            channel.send(card)

        for record in caplog.records:
            if "ALERT ROUTED [WEBHOOK]" in record.message:
                json_str = record.message.split("ALERT ROUTED [WEBHOOK] ")[1]
                parsed = json.loads(json_str)
                assert parsed["alert_routing"] == "WEBHOOK"
                assert parsed["method"] == "POST"
                assert "payload" in parsed
                payload = parsed["payload"]
                assert payload["severity"] == "CRITICAL"
                assert payload["card_id"] == card.card_id
                break
        else:
            pytest.fail("No WEBHOOK routing record found")


# ═══════════════════════════════════════════════════════════════════════
#  AlertRouter Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAlertRouter:
    """Verify the AlertRouter dispatches correctly."""

    def test_route_critical_to_webhook_and_log(self):
        router = AlertRouter()
        card = _make_card(severity="CRITICAL", target_role="plant_manager")
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.WEBHOOK in channels
        assert AlertChannel.LOG in channels
        assert all(r.status == "sent" for r in results)

    def test_route_warning_maintenance_to_email_and_log(self):
        router = AlertRouter()
        card = _make_card(
            severity="WARNING",
            event_type="lazy_idle",
            target_role="maintenance_engineer",
        )
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.EMAIL in channels
        assert AlertChannel.LOG in channels

    def test_route_info_to_log_only(self):
        router = AlertRouter()
        card = _make_card(severity="INFO", target_role="operator")
        results = router.route(card)

        assert len(results) == 1
        assert results[0].channel == AlertChannel.LOG

    def test_disabled_router_returns_empty(self):
        router = AlertRouter(enabled=False)
        card = _make_card()
        results = router.route(card)
        assert results == []

    def test_enabled_property(self):
        router_on = AlertRouter(enabled=True)
        router_off = AlertRouter(enabled=False)
        assert router_on.enabled is True
        assert router_off.enabled is False

    def test_route_with_real_md_nearmiss_card(self):
        """Integration: generate a real card and route it."""
        router = AlertRouter()
        card = _make_card_from_generator("md_nearmiss")
        results = router.route(card)

        # md_nearmiss → CRITICAL → plant_manager → WEBHOOK + LOG
        channels = {r.channel for r in results}
        assert AlertChannel.WEBHOOK in channels
        assert AlertChannel.LOG in channels

    def test_route_with_real_lazy_idle_card(self):
        """Integration: lazy_idle → WARNING → maintenance → EMAIL + LOG."""
        router = AlertRouter()
        card = _make_card_from_generator("lazy_idle")
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.EMAIL in channels
        assert AlertChannel.LOG in channels

    def test_route_with_real_leak_proxy_card(self):
        """Integration: leak_proxy → WARNING → maintenance → EMAIL + LOG."""
        router = AlertRouter()
        card = _make_card_from_generator("leak_proxy")
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.EMAIL in channels
        assert AlertChannel.LOG in channels

    def test_route_with_real_critical_vibration_card(self):
        """Integration: critical_vibration → CRITICAL → plant_manager → WEBHOOK + LOG."""
        router = AlertRouter()
        card = _make_card_from_generator("critical_vibration")
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.WEBHOOK in channels
        assert AlertChannel.LOG in channels

    def test_route_with_real_maintenance_risk_card(self):
        """Integration: maintenance_risk → WARNING → maintenance → EMAIL + LOG."""
        router = AlertRouter()
        card = _make_card_from_generator("maintenance_risk")
        results = router.route(card)

        channels = {r.channel for r in results}
        assert AlertChannel.EMAIL in channels
        assert AlertChannel.LOG in channels

    def test_custom_webhook_url(self):
        router = AlertRouter(webhook_url="https://prod.example.com/hook")
        card = _make_card(severity="CRITICAL", target_role="plant_manager")
        results = router.route(card)

        webhook_results = [r for r in results if r.channel == AlertChannel.WEBHOOK]
        assert len(webhook_results) == 1
        assert "prod.example.com" in webhook_results[0].detail

    def test_custom_email_recipients(self):
        router = AlertRouter(
            email_recipients={"maintenance_engineer": "maint@factory.com"}
        )
        card = _make_card(
            severity="WARNING",
            event_type="lazy_idle",
            target_role="maintenance_engineer",
        )
        results = router.route(card)

        email_results = [r for r in results if r.channel == AlertChannel.EMAIL]
        assert len(email_results) == 1
        assert "maint@factory.com" in email_results[0].detail


# ═══════════════════════════════════════════════════════════════════════
#  Batch Routing Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAlertRouterBatch:
    """Verify batch routing processes multiple cards."""

    def test_batch_routes_all_cards(self):
        router = AlertRouter()
        cards = [
            _make_card(severity="CRITICAL", target_role="plant_manager"),
            _make_card(severity="WARNING", event_type="lazy_idle",
                      target_role="maintenance_engineer", device_id="d2"),
            _make_card(severity="INFO", event_type="info_test",
                      target_role="operator", device_id="d3"),
        ]
        results = router.route_batch(cards)

        # CRITICAL → 2 channels, WARNING → 2 channels, INFO → 1 channel
        assert len(results) == 5

    def test_batch_empty_list(self):
        router = AlertRouter()
        results = router.route_batch([])
        assert results == []

    def test_batch_all_results_have_status(self):
        router = AlertRouter()
        cards = [
            _make_card_from_generator("md_nearmiss"),
            _make_card_from_generator("lazy_idle"),
        ]
        results = router.route_batch(cards)
        assert all(r.status == "sent" for r in results)


# ═══════════════════════════════════════════════════════════════════════
#  RoutingResult Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRoutingResult:
    """Verify RoutingResult serialization and fields."""

    def test_to_dict_serialization(self):
        result = RoutingResult(
            card_id="abc123",
            channel=AlertChannel.EMAIL,
            target_role="maintenance_engineer",
            status="sent",
            detail="Email stub → maint@example.com",
        )
        d = result.to_dict()

        assert d["card_id"] == "abc123"
        assert d["channel"] == "email"
        assert d["target_role"] == "maintenance_engineer"
        assert d["status"] == "sent"
        assert isinstance(d["timestamp"], str)

    def test_to_dict_is_json_serializable(self):
        result = RoutingResult(
            card_id="xyz789",
            channel=AlertChannel.WEBHOOK,
            target_role="plant_manager",
        )
        json_str = json.dumps(result.to_dict())
        assert isinstance(json_str, str)


# ═══════════════════════════════════════════════════════════════════════
#  Documentation Helper Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRoutingTableDocumentation:
    """Verify the markdown documentation helper."""

    def test_markdown_has_header_row(self):
        md = get_routing_table_markdown()
        assert "Severity" in md
        assert "Target Role" in md
        assert "Channels" in md

    def test_markdown_has_all_rules(self):
        md = get_routing_table_markdown()
        lines = md.strip().split("\n")
        # Header + separator + one per rule
        assert len(lines) == 2 + len(ROUTING_TABLE)

    def test_markdown_contains_all_severities(self):
        md = get_routing_table_markdown()
        assert "CRITICAL" in md
        assert "WARNING" in md
        assert "INFO" in md


# ═══════════════════════════════════════════════════════════════════════
#  AlertChannel Enum Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAlertChannelEnum:
    """Verify the AlertChannel enum values."""

    def test_log_value(self):
        assert AlertChannel.LOG.value == "log"

    def test_email_value(self):
        assert AlertChannel.EMAIL.value == "email"

    def test_webhook_value(self):
        assert AlertChannel.WEBHOOK.value == "webhook"

    def test_reserved_sms(self):
        assert AlertChannel.SMS.value == "sms"

    def test_reserved_cmms(self):
        assert AlertChannel.CMMS.value == "cmms"

    def test_string_enum(self):
        """AlertChannel should be a string enum (usable in JSON)."""
        assert isinstance(AlertChannel.LOG, str)
        assert AlertChannel.LOG == "log"
