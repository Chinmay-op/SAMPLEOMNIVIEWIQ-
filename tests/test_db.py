"""
Tests for omniview.ingest.db — OI-54
======================================

Unit tests that run without a live TimescaleDB instance.
All database interactions are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── get_engine tests ────────────────────────────────────────────────────────


class TestGetEngine:
    """Verify engine singleton behaviour."""

    def setup_method(self) -> None:
        """Reset the module-level engine before each test."""
        import omniview.ingest.db as db_mod

        db_mod._engine = None

    @patch("omniview.ingest.db.create_engine")
    def test_creates_engine_on_first_call(self, mock_create: MagicMock) -> None:
        from omniview.ingest.db import get_engine

        mock_create.return_value = MagicMock()
        engine = get_engine()
        mock_create.assert_called_once()
        assert engine is mock_create.return_value

    @patch("omniview.ingest.db.create_engine")
    def test_returns_same_engine_on_subsequent_calls(
        self, mock_create: MagicMock
    ) -> None:
        from omniview.ingest.db import get_engine

        mock_create.return_value = MagicMock()
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2
        mock_create.assert_called_once()

    @patch("omniview.ingest.db.create_engine")
    def test_reset_engine_allows_new_creation(
        self, mock_create: MagicMock
    ) -> None:
        from omniview.ingest.db import get_engine, reset_engine

        mock_engine = MagicMock()
        mock_create.return_value = mock_engine

        get_engine()
        reset_engine()
        mock_engine.dispose.assert_called_once()

        # Next call creates a fresh engine
        mock_create.return_value = MagicMock()
        e2 = get_engine()
        assert mock_create.call_count == 2
        assert e2 is not mock_engine


# ── Table naming tests ──────────────────────────────────────────────────────


class TestTableNaming:
    """Verify table name generation."""

    def test_table_name_electrical(self) -> None:
        from omniview.ingest.db import _table_name

        assert _table_name("electrical") == "readings_electrical"

    def test_table_name_all_families(self) -> None:
        from omniview.ingest.db import _table_name
        from omniview.edge.topics import SENSOR_TYPES

        for st in SENSOR_TYPES:
            name = _table_name(st)
            assert name.startswith("readings_")
            assert st in name


# ── insert_reading tests ───────────────────────────────────────────────────


class TestInsertReading:
    """Verify insert_reading logic."""

    def test_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.db import insert_reading

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            insert_reading(
                sensor_type="nonexistent",
                device_id="test-01",
                site_id="test-site",
                time=datetime.now(timezone.utc),
                data={"value": 42},
            )

    @patch("omniview.ingest.db.get_engine")
    def test_returns_true_on_successful_insert(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.db import insert_reading

        # Mock the engine → connection → result chain
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
            sensor_type="electrical",
            device_id="compressor-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data={
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
        )
        assert result is True

    @patch("omniview.ingest.db.get_engine")
    def test_returns_false_on_duplicate(
        self, mock_get_engine: MagicMock
    ) -> None:
        from omniview.ingest.db import insert_reading

        mock_result = MagicMock()
        mock_result.rowcount = 0  # ON CONFLICT DO NOTHING → 0 rows
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        result = insert_reading(
            sensor_type="electrical",
            device_id="compressor-01",
            site_id="pune-isbm",
            time=datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc),
            data={
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
        )
        assert result is False


# ── insert_readings_batch tests ────────────────────────────────────────────


class TestInsertReadingsBatch:
    """Verify batch insert logic."""

    def test_empty_list_returns_zero(self) -> None:
        from omniview.ingest.db import insert_readings_batch

        assert insert_readings_batch("electrical", []) == 0

    def test_rejects_unknown_sensor_type(self) -> None:
        from omniview.ingest.db import insert_readings_batch

        with pytest.raises(ValueError, match="Unknown sensor_type"):
            insert_readings_batch("nonexistent", [{"data": {}}])

    @patch("omniview.ingest.db.get_engine")
    def test_counts_inserted_rows(self, mock_get_engine: MagicMock) -> None:
        from omniview.ingest.db import insert_readings_batch

        # Simulate 3 readings: 2 inserted, 1 duplicate
        mock_results = [MagicMock(rowcount=1), MagicMock(rowcount=1), MagicMock(rowcount=0)]
        call_idx = {"i": 0}

        def execute_side_effect(*args, **kwargs):
            r = mock_results[call_idx["i"]]
            call_idx["i"] += 1
            return r

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = execute_side_effect
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        readings = [
            {
                "device_id": "compressor-01",
                "site_id": "pune-isbm",
                "time": datetime(2026, 8, 10, 12, 0, i, tzinfo=timezone.utc),
                "data": {
                    "voltage_v_ln_avg": 239.5,
                    "voltage_v_ll_avg": 414.8,
                    "current_a_avg": 205.3,
                    "active_power_kw_total": 140.2,
                    "apparent_power_kva_total": 147.6 + i,
                    "reactive_power_kvar_total": 45.8,
                    "power_factor_avg": 0.949,
                    "frequency_hz": 50.02,
                    "active_energy_kwh": 150042.5,
                    "apparent_energy_kvah": 157544.6,
                    "rolling_kva_15min": 148.1,
                    "md_proximity_percent": 29.6,
                },
            }
            for i in range(3)
        ]

        count = insert_readings_batch("electrical", readings)
        assert count == 2


# ── create_hypertables tests ──────────────────────────────────────────────


class TestCreateHypertables:
    """Verify hypertable creation covers all 7 families."""

    @patch("omniview.ingest.db.get_engine")
    def test_creates_all_seven_tables(self, mock_get_engine: MagicMock) -> None:
        from omniview.edge.topics import SENSOR_TYPES
        from omniview.ingest.db import create_hypertables

        executed_sql: list[str] = []

        mock_conn = MagicMock()

        def capture_execute(stmt, *args, **kwargs):
            sql_text = str(stmt) if not hasattr(stmt, "text") else stmt.text
            executed_sql.append(sql_text)
            # Return a mock with .scalar() returning None (not a hypertable yet)
            result = MagicMock()
            result.scalar.return_value = None
            return result

        mock_conn.execute.side_effect = capture_execute
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        created = create_hypertables()

        # Should have created tables for all 7 sensor types
        assert len(created) == len(SENSOR_TYPES)
        for st in SENSOR_TYPES:
            assert f"readings_{st}" in created
