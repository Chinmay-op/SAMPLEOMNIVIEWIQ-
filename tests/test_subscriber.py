"""
Tests for omniview.ingest.subscriber — OI-54
===============================================

Unit tests for the MQTT → TimescaleDB bridge.
All MQTT and DB interactions are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── _on_sensor_message tests ───────────────────────────────────────────────


class TestOnSensorMessage:
    """Verify message handling logic."""

    def setup_method(self) -> None:
        """Reset subscriber stats before each test."""
        import omniview.ingest.subscriber as sub_mod

        with sub_mod._stats_lock:
            for key in sub_mod._stats:
                sub_mod._stats[key] = 0

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_valid_message_inserts_reading(
        self, mock_insert: MagicMock
    ) -> None:
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        mock_insert.return_value = True

        payload = {
            "timestamp": "2026-08-10T12:00:00+00:00",
            "schema_version": "1.0",
            "data": {"kva": 450.5, "kw": 380.2, "pf": 0.85},
        }

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/electrical", payload
        )

        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args
        assert call_kwargs.kwargs["sensor_type"] == "electrical"
        assert call_kwargs.kwargs["device_id"] == "compressor-01"
        assert call_kwargs.kwargs["site_id"] == "pune-isbm"
        assert call_kwargs.kwargs["data"] == payload["data"]

        stats = get_stats()
        assert stats["received"] == 1
        assert stats["inserted"] == 1

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_duplicate_increments_duplicate_counter(
        self, mock_insert: MagicMock
    ) -> None:
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        mock_insert.return_value = False  # ON CONFLICT → not inserted

        payload = {
            "timestamp": "2026-08-10T12:00:00+00:00",
            "data": {"kva": 450.5, "kw": 380.2, "pf": 0.85},
        }

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/electrical", payload
        )

        stats = get_stats()
        assert stats["duplicates"] == 1
        assert stats["inserted"] == 0

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_system_topic_skipped(self, mock_insert: MagicMock) -> None:
        """System topics (_status, _alerts) should be silently ignored."""
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        _on_sensor_message(
            "omniview/pune-isbm/_status/compressor-01", {"online": True}
        )

        mock_insert.assert_not_called()
        stats = get_stats()
        assert stats["skipped_system"] == 1

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_unknown_sensor_type_skipped(
        self, mock_insert: MagicMock
    ) -> None:
        """Topics with unrecognised sensor types should be skipped."""
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/unknown_sensor",
            {"value": 42},
        )

        mock_insert.assert_not_called()
        stats = get_stats()
        assert stats["skipped_system"] == 1

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_missing_timestamp_uses_arrival_time(
        self, mock_insert: MagicMock
    ) -> None:
        """Payloads without 'timestamp' should use UTC now as fallback."""
        from omniview.ingest.subscriber import _on_sensor_message

        mock_insert.return_value = True

        payload = {"data": {"temperature_c": 65.2}}  # no timestamp

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/thermal", payload
        )

        mock_insert.assert_called_once()
        ts = mock_insert.call_args.kwargs["time"]
        assert ts.tzinfo is not None  # must be timezone-aware

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_unix_timestamp_parsed(self, mock_insert: MagicMock) -> None:
        """Numeric timestamps (Unix epoch) should be parsed correctly."""
        from omniview.ingest.subscriber import _on_sensor_message

        mock_insert.return_value = True

        # 2026-08-10T12:00:00Z as Unix timestamp
        payload = {
            "timestamp": 1786353600,
            "data": {"pressure_bar": 32.5},
        }

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/pressure", payload
        )

        mock_insert.assert_called_once()
        ts = mock_insert.call_args.kwargs["time"]
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_insert_exception_increments_error_counter(
        self, mock_insert: MagicMock
    ) -> None:
        """DB errors should be logged but never crash the subscriber."""
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        mock_insert.side_effect = RuntimeError("DB connection lost")

        payload = {
            "timestamp": "2026-08-10T12:00:00+00:00",
            "data": {"kva": 450.5, "kw": 380.2, "pf": 0.85},
        }

        # Should NOT raise
        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/electrical", payload
        )

        stats = get_stats()
        assert stats["errors"] == 1
        assert stats["inserted"] == 0

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_payload_without_data_key_uses_full_payload(
        self, mock_insert: MagicMock
    ) -> None:
        """If no 'data' key, the entire payload is stored as data."""
        from omniview.ingest.subscriber import _on_sensor_message

        mock_insert.return_value = True

        payload = {
            "timestamp": "2026-08-10T12:00:00+00:00",
            "kva": 450.5,
            "kw": 380.2,
            "pf": 0.85,
        }

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/electrical", payload
        )

        stored_data = mock_insert.call_args.kwargs["data"]
        # Full payload is used as data (since no 'data' key)
        assert stored_data == payload

    @patch("omniview.ingest.subscriber.insert_reading")
    def test_invalid_payload_skipped(self, mock_insert: MagicMock) -> None:
        """Payloads that fail schema validation should be skipped."""
        from omniview.ingest.subscriber import _on_sensor_message, get_stats

        # Payload missing 'kw' and 'pf'
        payload = {
            "timestamp": "2026-08-10T12:00:00+00:00",
            "data": {"kva": 450.5},
        }

        _on_sensor_message(
            "omniview/pune-isbm/compressor-01/electrical", payload
        )

        mock_insert.assert_not_called()
        stats = get_stats()
        assert stats["validation_failures"] == 1
        assert stats["inserted"] == 0
