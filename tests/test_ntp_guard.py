"""
Tests for NTP Drift Guard — OI-53
===================================

Comprehensive test suite covering:
* ``check_drift()`` one-shot function
* ``NTPDriftGuard`` class (background thread, alerts, state)
* Edge cases: negative offset, boundary, NTP failures
* MQTT alert payload validation
* Config overrides
* Thread safety

All NTP calls are mocked — no real network I/O.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from omniview.edge.ntp_guard import (
    DriftStatus,
    NTPDriftGuard,
    check_drift,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


class FakeNTPResponse:
    """Minimal fake of ``ntplib.NTPStats`` with the fields we use."""

    def __init__(self, offset: float = 0.001, stratum: int = 2):
        self.offset = offset
        self.stratum = stratum


class FakeNTPClient:
    """Injectable mock NTP client that returns configurable responses."""

    def __init__(
        self,
        offset: float = 0.001,
        stratum: int = 2,
        fail: bool = False,
        fail_msg: str = "NTP timeout",
    ):
        self._offset = offset
        self._stratum = stratum
        self._fail = fail
        self._fail_msg = fail_msg
        self.call_count = 0

    def request(self, server: str, version: int = 3, timeout: float = 5.0):
        self.call_count += 1
        if self._fail:
            raise OSError(self._fail_msg)
        return FakeNTPResponse(offset=self._offset, stratum=self._stratum)


@pytest.fixture
def synced_client():
    """Client that returns a tiny offset (well within threshold)."""
    return FakeNTPClient(offset=0.002, stratum=2)


@pytest.fixture
def drifted_client():
    """Client that returns offset > 5s threshold."""
    return FakeNTPClient(offset=7.5, stratum=2)


@pytest.fixture
def negative_drift_client():
    """Client that returns negative offset (clock ahead of NTP)."""
    return FakeNTPClient(offset=-6.3, stratum=1)


@pytest.fixture
def failing_client():
    """Client that always raises on request()."""
    return FakeNTPClient(fail=True, fail_msg="Network unreachable")


@pytest.fixture
def boundary_client():
    """Client that returns offset exactly at the 5.0s threshold."""
    return FakeNTPClient(offset=5.0, stratum=3)


# ═════════════════════════════════════════════════════════════════════════
# 1. check_drift() — one-shot function tests
# ═════════════════════════════════════════════════════════════════════════


class TestCheckDrift:
    """Tests for the standalone ``check_drift()`` function."""

    def test_synced_returns_true(self, synced_client):
        status = check_drift(ntp_client=synced_client, threshold_s=5.0)
        assert status.is_synced is True
        assert status.error is None
        assert abs(status.offset_seconds) < 5.0

    def test_drifted_returns_false(self, drifted_client):
        status = check_drift(ntp_client=drifted_client, threshold_s=5.0)
        assert status.is_synced is False
        assert status.error is None
        assert status.offset_seconds == 7.5

    def test_negative_drift_detected(self, negative_drift_client):
        status = check_drift(
            ntp_client=negative_drift_client, threshold_s=5.0
        )
        assert status.is_synced is False
        assert status.offset_seconds == -6.3

    def test_zero_offset_is_synced(self):
        client = FakeNTPClient(offset=0.0)
        status = check_drift(ntp_client=client, threshold_s=5.0)
        assert status.is_synced is True
        assert status.offset_seconds == 0.0

    def test_boundary_offset_is_synced(self, boundary_client):
        """Offset == threshold should count as synced (<= comparison)."""
        status = check_drift(ntp_client=boundary_client, threshold_s=5.0)
        assert status.is_synced is True

    def test_just_over_threshold_is_not_synced(self):
        client = FakeNTPClient(offset=5.000001)
        status = check_drift(ntp_client=client, threshold_s=5.0)
        assert status.is_synced is False

    def test_ntp_failure_returns_error_status(self, failing_client):
        status = check_drift(ntp_client=failing_client, threshold_s=5.0)
        assert status.is_synced is False
        assert status.error is not None
        assert "unreachable" in status.error.lower()
        assert status.offset_seconds == 0.0

    def test_custom_server_passed_through(self, synced_client):
        status = check_drift(
            ntp_client=synced_client,
            server="time.google.com",
        )
        assert status.ntp_server == "time.google.com"

    def test_custom_threshold(self):
        client = FakeNTPClient(offset=3.0)
        status = check_drift(ntp_client=client, threshold_s=2.0)
        assert status.is_synced is False
        assert status.threshold_seconds == 2.0

    def test_stratum_captured(self):
        client = FakeNTPClient(offset=0.01, stratum=1)
        status = check_drift(ntp_client=client)
        assert status.stratum == 1

    def test_check_time_is_iso_format(self, synced_client):
        status = check_drift(ntp_client=synced_client)
        # Should parse without error
        datetime.fromisoformat(status.check_time)

    def test_offset_rounded_to_6_decimals(self):
        client = FakeNTPClient(offset=0.123456789)
        status = check_drift(ntp_client=client)
        assert status.offset_seconds == 0.123457  # rounded to 6 dp


# ═════════════════════════════════════════════════════════════════════════
# 2. DriftStatus dataclass tests
# ═════════════════════════════════════════════════════════════════════════


class TestDriftStatus:
    """Tests for the DriftStatus dataclass."""

    def test_frozen(self):
        status = DriftStatus(
            offset_seconds=0.1,
            is_synced=True,
            ntp_server="pool.ntp.org",
            check_time="2026-08-19T12:00:00Z",
            stratum=2,
            threshold_seconds=5.0,
        )
        with pytest.raises(AttributeError):
            status.offset_seconds = 999  # type: ignore[misc]

    def test_error_defaults_to_none(self):
        status = DriftStatus(
            offset_seconds=0.1,
            is_synced=True,
            ntp_server="pool.ntp.org",
            check_time="2026-08-19T12:00:00Z",
            stratum=2,
            threshold_seconds=5.0,
        )
        assert status.error is None

    def test_error_can_be_set(self):
        status = DriftStatus(
            offset_seconds=0.0,
            is_synced=False,
            ntp_server="pool.ntp.org",
            check_time="2026-08-19T12:00:00Z",
            stratum=0,
            threshold_seconds=5.0,
            error="timeout",
        )
        assert status.error == "timeout"


# ═════════════════════════════════════════════════════════════════════════
# 3. NTPDriftGuard — class-level tests
# ═════════════════════════════════════════════════════════════════════════


class TestNTPDriftGuard:
    """Tests for the NTPDriftGuard background monitor."""

    def test_initial_state(self, synced_client):
        guard = NTPDriftGuard(ntp_client=synced_client)
        assert guard.is_running is False
        assert guard.last_status is None
        assert guard.consecutive_failures == 0
        assert guard.consecutive_drift_breaches == 0
        assert guard.history == []

    def test_run_check_synced(self, synced_client):
        guard = NTPDriftGuard(ntp_client=synced_client, threshold_s=5.0)
        status = guard.run_check()
        assert status.is_synced is True
        assert guard.last_status is status
        assert guard.consecutive_failures == 0
        assert guard.consecutive_drift_breaches == 0
        assert len(guard.history) == 1

    def test_run_check_drifted(self, drifted_client):
        guard = NTPDriftGuard(ntp_client=drifted_client, threshold_s=5.0)
        status = guard.run_check()
        assert status.is_synced is False
        assert guard.consecutive_drift_breaches == 1

    def test_consecutive_drift_increments(self, drifted_client):
        guard = NTPDriftGuard(ntp_client=drifted_client, threshold_s=5.0)
        guard.run_check()
        guard.run_check()
        guard.run_check()
        assert guard.consecutive_drift_breaches == 3

    def test_drift_resets_on_sync(self):
        """Counter resets when a good check follows bad ones."""
        drifted = FakeNTPClient(offset=10.0)
        guard = NTPDriftGuard(ntp_client=drifted, threshold_s=5.0)

        guard.run_check()
        guard.run_check()
        assert guard.consecutive_drift_breaches == 2

        # Swap to a synced client
        guard._ntp_client = FakeNTPClient(offset=0.01)
        guard.run_check()
        assert guard.consecutive_drift_breaches == 0

    def test_ntp_failure_increments_consecutive_failures(
        self, failing_client
    ):
        guard = NTPDriftGuard(
            ntp_client=failing_client, threshold_s=5.0, max_retries=5
        )
        guard.run_check()
        assert guard.consecutive_failures == 1
        guard.run_check()
        assert guard.consecutive_failures == 2

    def test_ntp_failure_resets_on_success(self, failing_client):
        guard = NTPDriftGuard(ntp_client=failing_client, threshold_s=5.0)
        guard.run_check()
        guard.run_check()
        assert guard.consecutive_failures == 2

        guard._ntp_client = FakeNTPClient(offset=0.01)
        guard.run_check()
        assert guard.consecutive_failures == 0

    def test_history_capped(self, synced_client):
        guard = NTPDriftGuard(ntp_client=synced_client)
        guard._max_history = 5
        for _ in range(10):
            guard.run_check()
        assert len(guard.history) == 5

    def test_history_is_copy(self, synced_client):
        guard = NTPDriftGuard(ntp_client=synced_client)
        guard.run_check()
        h = guard.history
        h.clear()
        assert len(guard.history) == 1  # original unmodified


# ═════════════════════════════════════════════════════════════════════════
# 4. MQTT alert publishing tests
# ═════════════════════════════════════════════════════════════════════════


class TestMQTTAlerts:
    """Tests for MQTT alert payloads on drift breach and NTP unreachable."""

    def test_drift_alert_published(self, drifted_client):
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=drifted_client,
            threshold_s=5.0,
            site_id="pune-isbm",
            publish_fn=publish_fn,
        )
        guard.run_check()

        publish_fn.assert_called_once()
        topic, payload = publish_fn.call_args[0]
        assert topic == "omniview/pune-isbm/system/ntp_drift_alert"
        assert payload["event_type"] == "NTP_DRIFT_ALERT"
        assert payload["severity"] == "CRITICAL"
        assert payload["drift_seconds"] == 7.5
        assert payload["threshold_seconds"] == 5.0
        assert payload["consecutive_failures"] == 1

    def test_no_alert_when_synced(self, synced_client):
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            threshold_s=5.0,
            publish_fn=publish_fn,
        )
        guard.run_check()
        publish_fn.assert_not_called()

    def test_no_alert_without_publish_fn(self, drifted_client):
        """Guard works without a publish_fn (logging only)."""
        guard = NTPDriftGuard(
            ntp_client=drifted_client,
            threshold_s=5.0,
            publish_fn=None,
        )
        # Should not raise
        status = guard.run_check()
        assert status.is_synced is False

    def test_ntp_unreachable_alert_after_max_retries(self, failing_client):
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=failing_client,
            threshold_s=5.0,
            max_retries=3,
            publish_fn=publish_fn,
        )

        # First 2 failures — no unreachable alert
        guard.run_check()
        guard.run_check()
        publish_fn.assert_not_called()

        # 3rd failure hits max_retries — fires alert
        guard.run_check()
        publish_fn.assert_called_once()
        _, payload = publish_fn.call_args[0]
        assert payload["event_type"] == "NTP_UNREACHABLE"
        assert payload["consecutive_failures"] == 3

    def test_unreachable_alert_fires_every_check_after_max(
        self, failing_client
    ):
        """Once max retries hit, every subsequent failure also fires."""
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=failing_client,
            max_retries=2,
            publish_fn=publish_fn,
        )
        for _ in range(5):
            guard.run_check()
        # Should fire on checks 2, 3, 4, 5 (every check after reaching max)
        assert publish_fn.call_count == 4

    def test_drift_alert_payload_has_required_fields(self, drifted_client):
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=drifted_client,
            threshold_s=5.0,
            publish_fn=publish_fn,
        )
        guard.run_check()

        _, payload = publish_fn.call_args[0]
        required_fields = {
            "event_type",
            "timestamp",
            "gateway_id",
            "drift_seconds",
            "threshold_seconds",
            "ntp_server",
            "stratum",
            "consecutive_failures",
            "severity",
        }
        assert required_fields.issubset(payload.keys())

    def test_publish_fn_exception_does_not_crash_guard(self, drifted_client):
        """If publish_fn raises, the guard logs the error but continues."""
        publish_fn = MagicMock(side_effect=Exception("MQTT down"))
        guard = NTPDriftGuard(
            ntp_client=drifted_client,
            threshold_s=5.0,
            publish_fn=publish_fn,
        )
        # Should not raise
        status = guard.run_check()
        assert status.is_synced is False


# ═════════════════════════════════════════════════════════════════════════
# 5. Background thread lifecycle tests
# ═════════════════════════════════════════════════════════════════════════


class TestGuardLifecycle:
    """Tests for start/stop and background thread behavior."""

    def test_start_and_stop(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            check_interval_s=1,
        )
        guard.start()
        assert guard.is_running is True
        guard.stop(timeout=2.0)
        assert guard.is_running is False

    def test_double_start_raises(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            check_interval_s=1,
        )
        guard.start()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                guard.start()
        finally:
            guard.stop()

    def test_background_thread_runs_checks(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            check_interval_s=1,
        )
        guard.start()
        time.sleep(2.5)  # Should get ~2-3 checks
        guard.stop()

        assert len(guard.history) >= 2
        assert synced_client.call_count >= 2

    def test_stop_is_fast(self, synced_client):
        """stop() should not wait for the full check_interval."""
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            check_interval_s=60,  # long interval
        )
        guard.start()
        time.sleep(0.2)  # Let thread start

        start = time.monotonic()
        guard.stop(timeout=2.0)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0  # Should be near-instant, not 60s

    def test_thread_is_daemon(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            check_interval_s=1,
        )
        guard.start()
        assert guard._thread.daemon is True
        guard.stop()


# ═════════════════════════════════════════════════════════════════════════
# 6. Config and customization tests
# ═════════════════════════════════════════════════════════════════════════


class TestConfigOverrides:
    """Tests for custom config values."""

    def test_custom_threshold(self):
        client = FakeNTPClient(offset=3.0)
        guard = NTPDriftGuard(ntp_client=client, threshold_s=2.0)
        status = guard.run_check()
        assert status.is_synced is False

    def test_custom_server(self):
        client = FakeNTPClient(offset=0.01)
        guard = NTPDriftGuard(
            ntp_client=client, server="time.google.com"
        )
        status = guard.run_check()
        assert status.ntp_server == "time.google.com"

    def test_custom_site_id_in_topic(self):
        publish_fn = MagicMock()
        client = FakeNTPClient(offset=10.0)
        guard = NTPDriftGuard(
            ntp_client=client,
            threshold_s=5.0,
            site_id="mumbai-factory",
            publish_fn=publish_fn,
        )
        guard.run_check()
        topic, _ = publish_fn.call_args[0]
        assert topic == "omniview/mumbai-factory/system/ntp_drift_alert"

    def test_custom_max_retries(self):
        client = FakeNTPClient(fail=True)
        publish_fn = MagicMock()
        guard = NTPDriftGuard(
            ntp_client=client,
            max_retries=5,
            publish_fn=publish_fn,
        )
        for _ in range(4):
            guard.run_check()
        publish_fn.assert_not_called()  # Still below max_retries=5

        guard.run_check()
        publish_fn.assert_called_once()  # Now at 5


# ═════════════════════════════════════════════════════════════════════════
# 7. Logging tests
# ═════════════════════════════════════════════════════════════════════════


class TestLogging:
    """Tests that the guard logs at the correct levels."""

    def test_sync_ok_logs_info(self, synced_client, caplog):
        guard = NTPDriftGuard(ntp_client=synced_client, threshold_s=5.0)
        with caplog.at_level(logging.INFO):
            guard.run_check()
        assert any("NTP sync OK" in r.message for r in caplog.records)

    def test_drift_breach_logs_critical(self, drifted_client, caplog):
        guard = NTPDriftGuard(ntp_client=drifted_client, threshold_s=5.0)
        with caplog.at_level(logging.CRITICAL):
            guard.run_check()
        assert any(
            "DRIFT BREACH" in r.message for r in caplog.records
        )

    def test_ntp_failure_logs_warning(self, failing_client, caplog):
        guard = NTPDriftGuard(
            ntp_client=failing_client,
            threshold_s=5.0,
            max_retries=10,
        )
        with caplog.at_level(logging.WARNING):
            guard.run_check()
        assert any(
            "NTP check failed" in r.message for r in caplog.records
        )

    def test_ntp_unreachable_logs_critical(self, failing_client, caplog):
        guard = NTPDriftGuard(
            ntp_client=failing_client,
            threshold_s=5.0,
            max_retries=1,
        )
        with caplog.at_level(logging.CRITICAL):
            guard.run_check()
        assert any(
            "NTP UNREACHABLE" in r.message for r in caplog.records
        )


# ═════════════════════════════════════════════════════════════════════════
# 8. Repr test
# ═════════════════════════════════════════════════════════════════════════


class TestRepr:
    """Tests for __repr__."""

    def test_repr_stopped(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client,
            server="time.google.com",
            threshold_s=3.0,
            check_interval_s=30,
        )
        r = repr(guard)
        assert "time.google.com" in r
        assert "3.0s" in r
        assert "30s" in r
        assert "stopped" in r

    def test_repr_running(self, synced_client):
        guard = NTPDriftGuard(
            ntp_client=synced_client, check_interval_s=1
        )
        guard.start()
        try:
            assert "running" in repr(guard)
        finally:
            guard.stop()
