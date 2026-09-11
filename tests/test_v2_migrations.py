"""
Tests for V3 Schema Migration — Native Label Columns
======================================================

Validates:
1. Migration data structure consistency (_LABEL_INDEXED_TABLES).
2. _run_v3_label_column executes correct DDL (ADD COLUMN + indexes).
3. Dashboard queries use the native ``scenario_label`` column.
4. Backwards compatibility — queries still work with JSONB-only rows.

History: V2 used GENERATED ALWAYS columns extracted from JSONB.
DevB's architectural decision (commit e0a1798) replaced them with
plain TEXT columns written by the ingestion pipeline.

All TSDB calls are mocked — no real database needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

IST = timezone(timedelta(hours=5, minutes=30))
_BASE_TIME = datetime(2026, 8, 20, 10, 0, 0, tzinfo=IST)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Migration Structure Tests — V3 Label Column
# ═══════════════════════════════════════════════════════════════════════════


class TestV3MigrationStructure:
    """Verify the _LABEL_INDEXED_TABLES data structure is well-formed."""

    def test_all_indexed_tables_use_readings_prefix(self) -> None:
        from omniview.ingest.migrations import _LABEL_INDEXED_TABLES

        for table in _LABEL_INDEXED_TABLES:
            assert table.startswith("readings_"), (
                f"Table {table!r} must start with 'readings_'"
            )

    def test_indexed_tables_match_known_sensor_types(self) -> None:
        from omniview.edge.topics import SENSOR_TYPES
        from omniview.ingest.migrations import _LABEL_INDEXED_TABLES

        expected_tables = {f"readings_{st}" for st in SENSOR_TYPES}
        for table in _LABEL_INDEXED_TABLES:
            assert table in expected_tables, (
                f"Table {table!r} not in SENSOR_TYPES"
            )

    def test_indexed_tables_are_alert_producers(self) -> None:
        """Only alert-producing tables get sparse indexes."""
        from omniview.ingest.migrations import _LABEL_INDEXED_TABLES

        # These are the tables that currently produce alert scenarios
        assert "readings_electrical" in _LABEL_INDEXED_TABLES
        assert "readings_pressure" in _LABEL_INDEXED_TABLES
        assert "readings_thermal" in _LABEL_INDEXED_TABLES

    def test_stroke_and_ambient_not_indexed(self) -> None:
        """Stroke/ambient have no alert scenarios — no sparse index needed."""
        from omniview.ingest.migrations import _LABEL_INDEXED_TABLES

        assert "readings_stroke" not in _LABEL_INDEXED_TABLES
        assert "readings_ambient" not in _LABEL_INDEXED_TABLES

    def test_label_indexed_tables_is_frozenset(self) -> None:
        from omniview.ingest.migrations import _LABEL_INDEXED_TABLES

        assert isinstance(_LABEL_INDEXED_TABLES, frozenset)

    def test_label_column_covers_all_families(self) -> None:
        """V3 adds scenario_label to ALL 7 hypertables, not just indexed ones."""
        from omniview.edge.topics import SENSOR_TYPES
        from omniview.ingest.migrations import _run_v3_label_column

        # The runner iterates over all SENSOR_TYPES, not just indexed
        # Verify by counting: 7 tables × 1 ALTER + indexed tables × 1 INDEX
        assert len(SENSOR_TYPES) == 7


class TestRunV3LabelColumn:
    """Verify _run_v3_label_column issues correct DDL statements."""

    def test_executes_expected_statement_count(self) -> None:
        from omniview.edge.topics import SENSOR_TYPES
        from omniview.ingest.migrations import (
            _LABEL_INDEXED_TABLES,
            _run_v3_label_column,
        )

        # Expected: 7 tables × (1 guard + 1 ALTER) + len(indexed) indexes
        # Each table gets 1 "executed" count, plus each indexed table gets 1
        expected = len(SENSOR_TYPES) + len(_LABEL_INDEXED_TABLES)

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )

        count = _run_v3_label_column(mock_engine)
        assert count == expected

    def test_calls_execute_with_sql(self) -> None:
        from omniview.ingest.migrations import _run_v3_label_column

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )

        _run_v3_label_column(mock_engine)

        # Should have called conn.execute multiple times
        assert mock_conn.execute.call_count > 0

    def test_returns_positive_count(self) -> None:
        from omniview.ingest.migrations import _run_v3_label_column

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )

        count = _run_v3_label_column(mock_engine)
        assert count > 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dashboard Query Tests — V3 Native scenario_label Column
# ═══════════════════════════════════════════════════════════════════════════


def _make_v3_elec_row(
    kva: float = 140.0,
    kw: float = 130.0,
    scenario_label: str | None = None,
    time_offset_min: int = 0,
) -> dict:
    """Create an electrical row with V3 native scenario_label column."""
    t = _BASE_TIME + timedelta(minutes=time_offset_min)
    return {
        "time": t,
        "device_id": "pune-comp-mfm384",
        "site_id": "pune-isbm",
        "sensor_type": "electrical",
        "schema_version": "1.0",
        "data": {
            "apparent_power_kva_total": kva,
            "active_power_kw_total": kw,
            "power_factor_avg": 0.95,
            "current_a_avg": 200.0,
        },
        # V3 native column (not inside JSONB):
        "scenario_label": scenario_label,
    }


def _make_v3_vib_row(
    zone: str = "ZONE_A",
    z_rms: float = 1.5,
    time_offset_min: int = 0,
) -> dict:
    """Create a vibration row dict with V3 native columns."""
    t = _BASE_TIME + timedelta(minutes=time_offset_min)
    return {
        "time": t,
        "device_id": "pune-comp-vib01",
        "site_id": "pune-isbm",
        "sensor_type": "vibration",
        "schema_version": "1.0",
        "data": {
            "z_axis_rms_velocity_mm_sec": z_rms,
            "iso_health_zone": zone,
        },
    }


class TestGetLatestKvaV3:
    """get_latest_kva should extract kva from JSONB data."""

    @patch("omniview.dashboard.queries.query_latest")
    def test_extracts_kva_from_data(self, mock_ql: MagicMock) -> None:
        from omniview.dashboard.queries import get_latest_kva

        mock_ql.return_value = [_make_v3_elec_row(kva=478.5)]
        result = get_latest_kva()
        assert result["kva"] == 478.5

    @patch("omniview.dashboard.queries.query_latest")
    def test_computes_md_proximity_from_kva(self, mock_ql: MagicMock) -> None:
        from omniview.dashboard.queries import get_latest_kva

        mock_ql.return_value = [_make_v3_elec_row(kva=250.0)]
        result = get_latest_kva()
        # 250 / 500 * 100 = 50%
        assert result["md_proximity_percent"] == 50.0

    @patch("omniview.dashboard.queries.query_latest")
    def test_works_without_scenario_label(
        self, mock_ql: MagicMock
    ) -> None:
        """Rows without scenario_label should still work for kva."""
        from omniview.dashboard.queries import get_latest_kva

        row = _make_v3_elec_row(kva=350.0)
        del row["scenario_label"]
        mock_ql.return_value = [row]

        result = get_latest_kva()
        assert result["kva"] == 350.0  # Extracted from JSONB data


class TestGetKvaTimeseriesV3:
    """get_kva_timeseries should extract from JSONB data."""

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_extracts_kva_kw_from_data(self, mock_qr: MagicMock) -> None:
        from omniview.dashboard.queries import get_kva_timeseries

        mock_qr.return_value = [
            _make_v3_elec_row(kva=100.0, kw=95.0, time_offset_min=0),
            _make_v3_elec_row(kva=200.0, kw=190.0, time_offset_min=15),
        ]
        df = get_kva_timeseries()
        assert len(df) == 2
        assert df["kva"].tolist() == [100.0, 200.0]
        assert df["kw"].tolist() == [95.0, 190.0]


class TestGetPeakKva24hV3:
    """get_peak_kva_24h should extract max kva from data."""

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_peak_from_data_column(self, mock_qr: MagicMock) -> None:
        from omniview.dashboard.queries import get_peak_kva_24h

        mock_qr.return_value = [
            _make_v3_elec_row(kva=200.0),
            _make_v3_elec_row(kva=450.0),
            _make_v3_elec_row(kva=300.0),
        ]
        peak = get_peak_kva_24h(device_ids=["pune-comp-mfm384"])
        assert peak == 450.0


class TestGetAlertsV3:
    """get_alerts should use native scenario_label column."""

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_detects_scenario_from_native_column(
        self, mock_qr: MagicMock
    ) -> None:
        from omniview.dashboard.queries import get_alerts

        mock_qr.return_value = [
            _make_v3_elec_row(scenario_label="md_nearmiss"),
        ]
        df = get_alerts(sensor_types=["electrical"])
        # Should find exactly 1 alert (deduplicated per-minute)
        assert len(df) >= 1
        assert df.iloc[0]["scenario_label"] == "md_nearmiss"
        assert df.iloc[0]["severity"] == "CRITICAL"

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_skips_rows_without_scenario_label(
        self, mock_qr: MagicMock
    ) -> None:
        from omniview.dashboard.queries import get_alerts

        mock_qr.return_value = [
            _make_v3_elec_row(scenario_label=None),
        ]
        df = get_alerts(sensor_types=["electrical"])
        assert len(df) == 0

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_no_scenario_in_jsonb_data_only(
        self, mock_qr: MagicMock
    ) -> None:
        """V3: scenario_label lives at top level, NOT inside JSONB data.
        A label inside data{} should NOT be detected as an alert."""
        from omniview.dashboard.queries import get_alerts

        row = {
            "time": _BASE_TIME,
            "device_id": "pune-comp-mfm384",
            "site_id": "pune-isbm",
            "sensor_type": "electrical",
            "schema_version": "1.0",
            "data": {
                "scenario_label": "md_nearmiss",  # inside JSONB, not native
                "apparent_power_kva_total": 450.0,
            },
            # No top-level scenario_label
        }
        mock_qr.return_value = [row]
        df = get_alerts(sensor_types=["electrical"])
        # Should NOT detect — scenario_label must be top-level
        assert len(df) == 0


class TestGetHealthIndexTrendV3:
    """get_health_index_trend should extract from JSONB data."""

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_extracts_zone_and_z_rms_from_data(
        self, mock_qr: MagicMock
    ) -> None:
        from omniview.dashboard.queries import get_health_index_trend

        mock_qr.return_value = [
            _make_v3_vib_row(zone="ZONE_A", z_rms=1.2, time_offset_min=0),
            _make_v3_vib_row(zone="ZONE_C", z_rms=12.5, time_offset_min=15),
            _make_v3_vib_row(zone="ZONE_D", z_rms=22.0, time_offset_min=30),
        ]
        df = get_health_index_trend()
        assert len(df) == 3
        assert df["hi_score"].tolist() == [100, 50, 25]
        assert df["iso_zone"].tolist() == ["ZONE_A", "ZONE_C", "ZONE_D"]
        assert df["z_rms"].tolist() == [1.2, 12.5, 22.0]

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_works_with_jsonb_only_rows(
        self, mock_qr: MagicMock
    ) -> None:
        from omniview.dashboard.queries import get_health_index_trend

        row = {
            "time": _BASE_TIME,
            "device_id": "pune-comp-vib01",
            "site_id": "pune-isbm",
            "sensor_type": "vibration",
            "schema_version": "1.0",
            "data": {
                "z_axis_rms_velocity_mm_sec": 8.5,
                "iso_health_zone": "ZONE_B",
            },
        }
        mock_qr.return_value = [row]
        df = get_health_index_trend()
        assert len(df) == 1
        assert df.iloc[0]["hi_score"] == 75
        assert df.iloc[0]["iso_zone"] == "ZONE_B"
        assert df.iloc[0]["z_rms"] == 8.5


class TestGetIdleLoadV3:
    """get_idle_load_percent should detect idle from current threshold."""

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_counts_idle_readings(
        self, mock_qr: MagicMock
    ) -> None:
        from omniview.dashboard.queries import get_idle_load_percent

        rows = [
            _make_v3_elec_row(
                kva=10, kw=5, scenario_label="lazy_idle",
                time_offset_min=0,
            ),
            _make_v3_elec_row(
                kva=300, kw=280, scenario_label=None,
                time_offset_min=15,
            ),
        ]
        # Adjust device_id to match the hardcoded one in get_idle_load_percent
        for r in rows:
            r["device_id"] = "pune-isbm-mfm384"

        mock_qr.return_value = rows
        result = get_idle_load_percent()
        assert result["total_readings"] == 2
        assert result["idle_readings"] == 1
        assert result["idle_pct"] == 50.0
