"""
Tests for OI-15 — Time-Series Database Insertion Logic (Idempotent)
====================================================================

Comprehensive tests validating:
- All 7 sensor families can be inserted
- Backfill idempotency (replayed backfill does not duplicate rows)
- Time-range queries (device_id + time window)
- BackfillResult tracking accuracy
- TSDBInserter per-family metrics
- Edge cases (empty inputs, invalid types, start > end)

All database interactions are mocked — no live TimescaleDB needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from omniview.edge.topics import SENSOR_TYPES


# ── Sample data factories ──────────────────────────────────────────────────

# Minimal valid data payloads for each sensor family
_SAMPLE_DATA = {
    "electrical": {
        "voltage_v_ln_avg": 239.5,
        "voltage_v_ll_avg": 414.8,
        "current_a_avg": 205.3,
        "active_power_kw_total": 140.2,
        "apparent_power_kva_total": 147.6,
        "reactive_power_kvar_total": 45.8,
        "power_factor_avg": 0.949,
        "frequency_hz": 50.02,
        "active_energy_kwh": 150042.5,
        "apparent_energy_kvah": 157544.6,
        "rolling_kva_15min": 148.1,
        "md_proximity_percent": 29.6,
    },
    "vibration": {
        "z_axis_rms_velocity_mm_sec": 2.4,
        "x_axis_rms_velocity_mm_sec": 1.8,
        "z_axis_peak_acceleration_g": 0.85,
        "x_axis_peak_acceleration_g": 0.62,
        "high_frequency_rms_acceleration_g": 0.45,
        "temperature_c": 62.3,
        "iso_health_zone": "ZONE_B",
    },
    "thermal": {
        "barrel_temperature_c": 245.0,
        "zone_temperature_c": 238.0,
        "ambient_temperature_c": 32.5,
    },
    "pressure": {
        "pressure_bar": 32.5,
        "pressure_psi": 471.4,
        "decay_rate_bar_per_min": 0.02,
    },
    "gas": {
        "particle_count": 150,
        "overheating_index": 0.3,
    },
    "stroke": {
        "stroke_count": 4523,
        "cycle_time_sec": 12.5,
        "oee_percent": 78.4,
    },
    "ambient": {
        "temperature_c": 33.2,
        "humidity_percent": 62.5,
    },
}


def _make_reading(
    sensor_type: str,
    device_id: str = "compressor-01",
    site_id: str = "pune-isbm",
    time: datetime | None = None,
    data: dict | None = None,
) -> dict:
    """Build a reading dict for test use."""
    return {
        "device_id": device_id,
        "site_id": site_id,
        "time": time or datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
        "data": data or _SAMPLE_DATA.get(sensor_type, {"value": 42}),
    }


# ── insert_reading: all 7 sensor families ──────────────────────────────────


class TestInsertAllFamilies:
    """OI-15 AC: 'Inserts succeed for each sensor schema'."""

    @pytest.mark.parametrize("sensor_type", sorted(SENSOR_TYPES))
    @patch("omniview.ingest.db.get_engine")
    def test_insert_succeeds_for_each_sensor_family(
        self, mock_get_engine: MagicMock, sensor_type: str
    ) -> None:
        from omniview.ingest.db import insert_reading

        # Mock engine chain
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        result = insert_reading(
            sensor_type=sensor_type,
            device_id="test-device-01",
            site_id="test-site",
            time=datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc),
            data=_SAMPLE_DATA.get(sensor_type, {"value": 42}),
        )

        assert result is True
        mock_conn.execute.assert_called_once()
        # Verify the SQL targets the correct table
        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert f"readings_{sensor_type}" in executed_sql


# ── Backfill idempotency ───────────────────────────────────────────────────


class TestBackfillIdempotency:
    """OI-15 AC: 'Replayed backfill does not duplicate rows'."""

    @patch("omniview.ingest.db.get_engine")
    def test_backfill_first_insert_all_new(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.db import backfill_insert

        # All 5 rows inserted (rowcount=5)
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading(
                "electrical",
                time=base_time + timedelta(seconds=15 * i),
            )
            for i in range(5)
        ]

        result = backfill_insert("electrical", readings)

        assert result.total == 5
        assert result.inserted == 5
        assert result.duplicates == 0
        assert result.sensor_type == "electrical"
        assert result.is_clean is True

    @patch("omniview.ingest.db.get_engine")
    def test_backfill_replay_all_duplicates(
        self, mock_get_engine: MagicMock
    ) -> None:
        """Replaying the exact same backfill → all duplicates, zero inserts."""
        from omniview.ingest.db import backfill_insert

        # ON CONFLICT DO NOTHING → rowcount=0
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading(
                "electrical",
                time=base_time + timedelta(seconds=15 * i),
            )
            for i in range(5)
        ]

        result = backfill_insert("electrical", readings)

        assert result.total == 5
        assert result.inserted == 0
        assert result.duplicates == 5
        assert result.is_clean is True

    @patch("omniview.ingest.db.get_engine")
    def test_backfill_partial_overlap(
        self, mock_get_engine: MagicMock
    ) -> None:
        """Backfill with mix of new and existing → partial insert."""
        from omniview.ingest.db import backfill_insert

        # 3 out of 5 inserted
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading(
                "vibration",
                time=base_time + timedelta(seconds=60 * i),
            )
            for i in range(5)
        ]

        result = backfill_insert("vibration", readings)

        assert result.total == 5
        assert result.inserted == 3
        assert result.duplicates == 2
        assert result.sensor_type == "vibration"
        assert result.is_clean is True


# ── Backfill edge cases ────────────────────────────────────────────────────


class TestBackfillEdgeCases:
    """Edge cases for backfill_insert."""

    def test_empty_backfill_returns_zero_result(self) -> None:
        from omniview.ingest.db import backfill_insert

        result = backfill_insert("electrical", [])

        assert result.total == 0
        assert result.inserted == 0
        assert result.duplicates == 0
        assert result.sensor_type == "electrical"
        assert result.is_clean is True

    def test_backfill_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.db import backfill_insert

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            backfill_insert("nonexistent", [_make_reading("electrical")])

    @patch("omniview.ingest.db.get_engine")
    def test_backfill_chunking_with_large_batch(
        self, mock_get_engine: MagicMock
    ) -> None:
        """Verify that >100 readings are split into multiple chunks."""
        from omniview.ingest.db import backfill_insert, _BACKFILL_CHUNK_SIZE

        mock_result = MagicMock()
        mock_result.rowcount = _BACKFILL_CHUNK_SIZE
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        n = 250  # should produce 3 chunks: 100, 100, 50
        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading(
                "pressure",
                time=base_time + timedelta(seconds=60 * i),
            )
            for i in range(n)
        ]

        result = backfill_insert("pressure", readings)

        assert result.total == 250
        # 3 chunks * 100 rowcount each = 300, but last chunk is 50 rows
        # Since mock always returns 100, we get 300, but real DB would return
        # actual counts. We're testing the chunking mechanism.
        assert mock_engine.begin.call_count == 3  # 3 chunks


# ── BackfillResult dataclass ──────────────────────────────────────────────


class TestBackfillResult:
    """Verify BackfillResult properties."""

    def test_is_clean_when_all_accounted(self) -> None:
        from omniview.ingest.db import BackfillResult

        r = BackfillResult(total=10, inserted=7, duplicates=3)
        assert r.is_clean is True

    def test_is_not_clean_when_mismatch(self) -> None:
        from omniview.ingest.db import BackfillResult

        r = BackfillResult(total=10, inserted=5, duplicates=3)
        assert r.is_clean is False

    def test_defaults_to_zero(self) -> None:
        from omniview.ingest.db import BackfillResult

        r = BackfillResult()
        assert r.total == 0
        assert r.inserted == 0
        assert r.duplicates == 0
        assert r.sensor_type == ""
        assert r.is_clean is True


# ── query_by_time_range ───────────────────────────────────────────────────


class TestQueryByTimeRange:
    """OI-15 AC: 'Queryable by device_id + time range'."""

    @patch("omniview.ingest.db.get_engine")
    def test_returns_rows_within_range(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.db import query_by_time_range

        mock_row = MagicMock()
        mock_row.__iter__ = MagicMock(
            return_value=iter(
                [
                    ("time", datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)),
                    ("device_id", "compressor-01"),
                    ("site_id", "pune-isbm"),
                    ("sensor_type", "electrical"),
                    ("schema_version", "1.0"),
                    ("data", {"kva": 147.6}),
                ]
            )
        )
        # Use a simpler approach — return list of dicts from mappings
        mock_mapping = {
            "time": datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            "device_id": "compressor-01",
            "site_id": "pune-isbm",
            "sensor_type": "electrical",
            "schema_version": "1.0",
            "data": {"kva": 147.6},
        }

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_mapping]
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        rows = query_by_time_range(
            sensor_type="electrical",
            device_id="compressor-01",
            start=datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc),
        )

        assert len(rows) == 1
        assert rows[0]["device_id"] == "compressor-01"
        assert rows[0]["data"] == {"kva": 147.6}

        # Verify the SQL contains the time range filter
        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "time >=" in executed_sql
        assert "time <=" in executed_sql
        assert "device_id" in executed_sql

    def test_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.db import query_by_time_range

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            query_by_time_range(
                sensor_type="nonexistent",
                device_id="test",
                start=datetime(2026, 8, 10, tzinfo=timezone.utc),
                end=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )

    def test_rejects_inverted_time_range(self) -> None:
        from omniview.ingest.db import query_by_time_range

        with pytest.raises(ValueError, match="start .* must be <= end"):
            query_by_time_range(
                sensor_type="electrical",
                device_id="test",
                start=datetime(2026, 8, 11, tzinfo=timezone.utc),
                end=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )

    @patch("omniview.ingest.db.get_engine")
    def test_returns_empty_for_no_data_in_range(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.db import query_by_time_range

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        rows = query_by_time_range(
            sensor_type="thermal",
            device_id="isbm-01",
            start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            end=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )

        assert rows == []


# ── TSDBInserter ──────────────────────────────────────────────────────────


class TestTSDBInserter:
    """Verify TSDBInserter facade and per-family metrics."""

    @patch("omniview.ingest.db.get_engine")
    def test_insert_tracks_metrics(self, mock_get_engine: MagicMock) -> None:
        from omniview.ingest.tsdb_inserter import TSDBInserter

        # Mock engine for successful insert
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        inserter = TSDBInserter()

        inserter.insert(
            sensor_type="electrical",
            device_id="compressor-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data=_SAMPLE_DATA["electrical"],
        )

        assert inserter.total_inserts == 1
        assert inserter.total_duplicates == 0
        assert inserter.metrics["electrical"]["inserts"] == 1

    @patch("omniview.ingest.db.get_engine")
    def test_insert_tracks_duplicates(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.tsdb_inserter import TSDBInserter

        # Mock duplicate (rowcount=0)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        inserter = TSDBInserter()

        inserter.insert(
            sensor_type="vibration",
            device_id="compressor-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data=_SAMPLE_DATA["vibration"],
        )

        assert inserter.total_inserts == 0
        assert inserter.total_duplicates == 1
        assert inserter.metrics["vibration"]["duplicates"] == 1

    @patch("omniview.ingest.db.get_engine")
    def test_multi_family_metrics_isolation(
        self, mock_get_engine: MagicMock
    ) -> None:
        """Metrics for one family don't leak into another."""
        from omniview.ingest.tsdb_inserter import TSDBInserter

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        inserter = TSDBInserter()

        inserter.insert(
            sensor_type="electrical",
            device_id="compressor-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data=_SAMPLE_DATA["electrical"],
        )
        inserter.insert(
            sensor_type="thermal",
            device_id="isbm-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data=_SAMPLE_DATA["thermal"],
        )

        assert inserter.metrics["electrical"]["inserts"] == 1
        assert inserter.metrics["thermal"]["inserts"] == 1
        assert inserter.metrics["vibration"]["inserts"] == 0
        assert inserter.total_inserts == 2

    def test_insert_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.tsdb_inserter import TSDBInserter

        inserter = TSDBInserter()

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            inserter.insert(
                sensor_type="nonexistent",
                device_id="test",
                site_id="test",
                time=datetime.now(timezone.utc),
                data={},
            )

    @patch("omniview.ingest.db.get_engine")
    def test_backfill_updates_metrics(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.tsdb_inserter import TSDBInserter

        # Mock: 3 out of 5 inserted
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        inserter = TSDBInserter()

        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading("pressure", time=base_time + timedelta(seconds=60 * i))
            for i in range(5)
        ]

        result = inserter.backfill("pressure", readings)

        assert result.inserted == 3
        assert result.duplicates == 2
        assert inserter.metrics["pressure"]["inserts"] == 3
        assert inserter.metrics["pressure"]["duplicates"] == 2

    def test_backfill_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.tsdb_inserter import TSDBInserter

        inserter = TSDBInserter()

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            inserter.backfill("nonexistent", [_make_reading("electrical")])


# ── insert_readings_batch (optimized multi-value) ─────────────────────────


class TestInsertReadingsBatchOptimized:
    """Verify the refactored multi-value INSERT batch function."""

    @patch("omniview.ingest.db.get_engine")
    def test_batch_uses_multi_value_insert(
        self, mock_get_engine: MagicMock
    ) -> None:
        """The SQL should contain multiple value tuples in a single INSERT."""
        from omniview.ingest.db import insert_readings_batch

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            _make_reading("electrical", time=base_time + timedelta(seconds=15 * i))
            for i in range(3)
        ]

        count = insert_readings_batch("electrical", readings)

        assert count == 3
        # Should be a single execute call (all 3 in one multi-value INSERT)
        assert mock_conn.execute.call_count == 1
        # The SQL should reference multiple value placeholders
        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert ":time_0" in executed_sql
        assert ":time_1" in executed_sql
        assert ":time_2" in executed_sql
