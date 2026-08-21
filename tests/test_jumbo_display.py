"""
Tests for OI-72 — Jumbo-Display Modbus Register Feed Stub
============================================================

All tests are self-contained — no TSDB, MQTT, or Modbus hardware needed.
Tests use the ``"mock"`` data source, so no database queries run.

Test groups:
  - Float ↔ register conversion
  - RegisterAddress constants
  - RegisterSnapshot serialization
  - JumboDisplayFeed update (mock data source)
  - Register read-back accuracy
  - Heartbeat counter
  - Drift check (no drift after fresh update)
  - Drift check (simulated drift)
  - DriftCheckResult serialization
  - Register map documentation
  - Severity mapping
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from omniview.dashboard.jumbo_display import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_NONE,
    SEVERITY_WARNING,
    DriftCheckResult,
    JumboDisplayFeed,
    RegisterAddress,
    RegisterSnapshot,
    float_to_registers,
    registers_to_float,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════════════════════════════
#  Float ↔ Register Conversion
# ═══════════════════════════════════════════════════════════════════════


class TestFloatRegisterConversion:
    """Verify IEEE 754 float ↔ Modbus register encoding."""

    def test_round_trip_positive(self):
        """float → registers → float should be identity."""
        for val in [0.0, 1.0, 478.5, 500.0, 1234.567, 99999.99]:
            high, low = float_to_registers(val)
            result = registers_to_float(high, low)
            assert abs(result - val) < 0.01, f"Failed for {val}"

    def test_round_trip_zero(self):
        high, low = float_to_registers(0.0)
        assert registers_to_float(high, low) == 0.0

    def test_round_trip_negative(self):
        high, low = float_to_registers(-42.5)
        result = registers_to_float(high, low)
        assert abs(result - (-42.5)) < 0.01

    def test_registers_are_uint16(self):
        """Both register values should be 16-bit unsigned integers."""
        high, low = float_to_registers(478.5)
        assert 0 <= high <= 0xFFFF
        assert 0 <= low <= 0xFFFF

    def test_specific_value_478_5(self):
        """Known value: 478.5f → specific register values."""
        high, low = float_to_registers(478.5)
        # Verify round trip rather than exact register values
        assert abs(registers_to_float(high, low) - 478.5) < 0.001

    def test_specific_value_500(self):
        high, low = float_to_registers(500.0)
        assert abs(registers_to_float(high, low) - 500.0) < 0.001


# ═══════════════════════════════════════════════════════════════════════
#  Register Address Constants
# ═══════════════════════════════════════════════════════════════════════


class TestRegisterAddress:
    """Verify register address constants."""

    def test_addresses_are_sequential(self):
        """No overlapping register addresses."""
        used = set()
        float_regs = [
            (RegisterAddress.LIVE_KVA, 2),
            (RegisterAddress.CONTRACT_KVA, 2),
            (RegisterAddress.MD_PROXIMITY, 2),
            (RegisterAddress.PENALTY_AVOIDED, 2),
            (RegisterAddress.IDLE_LOAD_PCT, 2),
            (RegisterAddress.PEAK_KVA_24H, 2),
        ]
        uint16_regs = [
            RegisterAddress.WARNING_COUNT,
            RegisterAddress.CRITICAL_COUNT,
            RegisterAddress.ACTIVE_SEVERITY,
            RegisterAddress.HEARTBEAT,
        ]

        for base, size in float_regs:
            for offset in range(size):
                addr = base + offset
                assert addr not in used, f"Register {addr} overlaps!"
                used.add(addr)

        for addr in uint16_regs:
            assert addr not in used, f"Register {addr} overlaps!"
            used.add(addr)

    def test_total_registers(self):
        assert RegisterAddress.TOTAL_REGISTERS == 16

    def test_live_kva_at_zero(self):
        assert RegisterAddress.LIVE_KVA == 0

    def test_heartbeat_at_13(self):
        assert RegisterAddress.HEARTBEAT == 13


# ═══════════════════════════════════════════════════════════════════════
#  JumboDisplayFeed — Mock Data Source
# ═══════════════════════════════════════════════════════════════════════


class TestJumboDisplayFeedMock:
    """Test the feed using mock data (no DB required)."""

    def test_update_returns_snapshot(self):
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()
        assert isinstance(snapshot, RegisterSnapshot)

    def test_mock_values_populate_registers(self):
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()

        # Mock values from _fetch_mock_values
        assert abs(snapshot.live_kva - 478.5) < 0.01
        assert abs(snapshot.contract_kva - 500.0) < 0.01
        assert abs(snapshot.md_proximity_pct - 95.7) < 0.1
        assert abs(snapshot.penalty_avoided_inr - 7525.0) < 1.0
        assert abs(snapshot.idle_load_pct - 12.3) < 0.1
        assert snapshot.warning_count == 2
        assert snapshot.critical_count == 1
        assert snapshot.active_severity == SEVERITY_CRITICAL

    def test_register_count(self):
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()
        assert len(snapshot.registers) == RegisterAddress.TOTAL_REGISTERS

    def test_register_read_back_float(self):
        """Values written to registers should read back correctly."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        # Read back live_kva from raw registers
        regs = feed.registers
        kva = registers_to_float(
            regs[RegisterAddress.LIVE_KVA],
            regs[RegisterAddress.LIVE_KVA + 1],
        )
        assert abs(kva - 478.5) < 0.01

    def test_register_read_back_uint16(self):
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        regs = feed.registers
        assert regs[RegisterAddress.WARNING_COUNT] == 2
        assert regs[RegisterAddress.CRITICAL_COUNT] == 1
        assert regs[RegisterAddress.ACTIVE_SEVERITY] == SEVERITY_CRITICAL

    def test_last_snapshot_property(self):
        feed = JumboDisplayFeed(data_source="mock")
        assert feed.last_snapshot is None

        snapshot = feed.update()
        assert feed.last_snapshot is snapshot

    def test_registers_property_returns_copy(self):
        """The registers property should return a copy, not the internal dict."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        regs1 = feed.registers
        regs2 = feed.registers
        assert regs1 == regs2
        assert regs1 is not regs2  # different dict objects


# ═══════════════════════════════════════════════════════════════════════
#  Heartbeat Counter
# ═══════════════════════════════════════════════════════════════════════


class TestHeartbeat:
    """Verify the heartbeat counter increments and wraps."""

    def test_heartbeat_increments(self):
        feed = JumboDisplayFeed(data_source="mock")

        s1 = feed.update()
        s2 = feed.update()
        s3 = feed.update()

        assert s1.heartbeat == 1
        assert s2.heartbeat == 2
        assert s3.heartbeat == 3

    def test_heartbeat_in_register(self):
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()

        regs = feed.registers
        assert regs[RegisterAddress.HEARTBEAT] == 1

    def test_heartbeat_wraps_at_65536(self):
        feed = JumboDisplayFeed(data_source="mock")
        feed._heartbeat = 65535  # one before wrap
        snapshot = feed.update()
        assert snapshot.heartbeat == 0  # wrapped


# ═══════════════════════════════════════════════════════════════════════
#  Drift Check
# ═══════════════════════════════════════════════════════════════════════


class TestDriftCheck:
    """Verify drift detection between registers and dashboard."""

    def test_no_drift_after_fresh_update(self):
        """Immediately after update, drift should be zero (mock source)."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()
        result = feed.check_drift()

        assert isinstance(result, DriftCheckResult)
        assert result.drifted is False
        assert result.max_drift_pct < 0.1  # within tolerance

    def test_drift_detected_when_registers_tampered(self):
        """If we manually change a register, drift should be detected."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        # Tamper with live_kva register (write a very different value)
        feed._write_float(RegisterAddress.LIVE_KVA, 999.0)

        result = feed.check_drift()
        assert result.drifted is True
        assert result.max_drift_pct > 1.0
        assert "live_kva" in result.field_drifts
        assert result.field_drifts["live_kva"]["drifted"] is True

    def test_drift_check_tolerance(self):
        """With high tolerance, small drift should not trigger."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        # Small tamper — 0.01% different
        original = feed._read_float(RegisterAddress.LIVE_KVA)
        feed._write_float(RegisterAddress.LIVE_KVA, original * 1.00005)

        result = feed.check_drift(tolerance_pct=0.01)
        assert result.drifted is False

    def test_drift_check_integer_fields(self):
        """Integer fields should detect any difference."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()

        # Tamper warning count
        feed._write_uint16(RegisterAddress.WARNING_COUNT, 99)

        result = feed.check_drift()
        assert result.drifted is True
        assert result.field_drifts["warning_count"]["drifted"] is True

    def test_no_drift_all_fields_checked(self):
        """All expected fields should appear in drift result."""
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()
        result = feed.check_drift()

        expected_fields = {
            "live_kva", "contract_kva", "md_proximity_pct",
            "penalty_avoided_inr", "idle_load_pct", "peak_kva_24h",
            "warning_count", "critical_count", "active_severity",
        }
        assert expected_fields == set(result.field_drifts.keys())


# ═══════════════════════════════════════════════════════════════════════
#  Serialization
# ═══════════════════════════════════════════════════════════════════════


class TestSerialization:
    """Verify snapshot and drift result serialization."""

    def test_snapshot_to_dict(self):
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()
        d = snapshot.to_dict()

        assert isinstance(d["timestamp"], str)
        assert d["live_kva"] == 478.5
        assert d["register_count"] == 16

    def test_snapshot_to_dict_json_serializable(self):
        import json
        feed = JumboDisplayFeed(data_source="mock")
        snapshot = feed.update()
        json_str = json.dumps(snapshot.to_dict())
        assert isinstance(json_str, str)

    def test_drift_result_to_dict(self):
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()
        result = feed.check_drift()
        d = result.to_dict()

        assert isinstance(d["timestamp"], str)
        assert d["drifted"] is False
        assert d["tolerance_pct"] == 0.1

    def test_drift_result_to_dict_json_serializable(self):
        import json
        feed = JumboDisplayFeed(data_source="mock")
        feed.update()
        result = feed.check_drift()
        json_str = json.dumps(result.to_dict())
        assert isinstance(json_str, str)


# ═══════════════════════════════════════════════════════════════════════
#  Severity Mapping
# ═══════════════════════════════════════════════════════════════════════


class TestSeverityMapping:
    """Verify severity constants."""

    def test_severity_none(self):
        assert SEVERITY_NONE == 0

    def test_severity_info(self):
        assert SEVERITY_INFO == 1

    def test_severity_warning(self):
        assert SEVERITY_WARNING == 2

    def test_severity_critical(self):
        assert SEVERITY_CRITICAL == 3

    def test_critical_is_highest(self):
        assert SEVERITY_CRITICAL > SEVERITY_WARNING > SEVERITY_INFO > SEVERITY_NONE


# ═══════════════════════════════════════════════════════════════════════
#  Register Map Documentation
# ═══════════════════════════════════════════════════════════════════════


class TestRegisterMapDocumentation:
    """Verify the markdown documentation helper."""

    def test_markdown_has_header(self):
        md = JumboDisplayFeed.get_register_map_markdown()
        assert "Address" in md
        assert "Name" in md
        assert "Type" in md

    def test_markdown_has_all_registers(self):
        md = JumboDisplayFeed.get_register_map_markdown()
        assert "live_kva" in md
        assert "contract_kva" in md
        assert "heartbeat" in md
        assert "peak_kva_24h" in md
        assert "active_severity" in md

    def test_markdown_shows_dashboard_source(self):
        md = JumboDisplayFeed.get_register_map_markdown()
        assert "get_latest_kva" in md
        assert "get_penalty_avoided" in md
