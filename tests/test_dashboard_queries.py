"""
Tests for Dashboard Queries — OI-68
======================================

All TSDB calls are mocked — no real database needed.
Tests cover all 4 hero metrics, alert extraction, HI trend,
and edge cases (empty DB, missing fields).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from omniview.dashboard.queries import (
    _extract_data_field,
    get_alerts,
    get_energy_and_strokes,
    get_health_index_trend,
    get_idle_load_percent,
    get_kva_timeseries,
    get_latest_kva,
    get_peak_kva_24h,
    get_penalty_avoided,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_elec_row(
    kva: float = 140.0,
    kw: float = 130.0,
    current: float = 200.0,
    pf: float = 0.95,
    device_id: str = "pune-comp-mfm384",
    time_offset_min: int = 0,
    scenario_label: str | None = None,
) -> dict:
    """Create a fake electrical reading row."""
    t = datetime(2026, 8, 18, 10, 0, 0, tzinfo=IST) + timedelta(minutes=time_offset_min)
    data = {
        "apparent_power_kva_total": kva,
        "active_power_kw_total": kw,
        "current_a_avg": current,
        "power_factor_avg": pf,
        "md_proximity_percent": (kva / 500) * 100,
    }
    return {
        "time": t,
        "device_id": device_id,
        "site_id": "pune-isbm",
        "sensor_type": "electrical",
        "schema_version": "1.0",
        "data": data,
        "scenario_label": scenario_label,
    }


def _make_vib_row(
    zone: str = "ZONE_A",
    z_rms: float = 1.5,
    time_offset_min: int = 0,
) -> dict:
    t = datetime(2026, 8, 18, 10, 0, 0, tzinfo=IST) + timedelta(minutes=time_offset_min)
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


def _make_stroke_row(strokes: int = 1, time_offset_min: int = 0) -> dict:
    t = datetime(2026, 8, 18, 10, 0, 0, tzinfo=IST) + timedelta(minutes=time_offset_min)
    return {
        "time": t,
        "device_id": "pune-isbm-stroke01",
        "site_id": "pune-isbm",
        "sensor_type": "stroke",
        "schema_version": "1.0",
        "data": {"strokes_since_last_poll": strokes},
    }


def _make_pressure_row(
    pressure: float = 33.0,
    time_offset_min: int = 0,
    scenario_label: str | None = None,
) -> dict:
    t = datetime(2026, 8, 18, 10, 0, 0, tzinfo=IST) + timedelta(minutes=time_offset_min)
    data = {"pressure_bar": pressure}
    return {
        "time": t,
        "device_id": "pune-comp-wika01",
        "site_id": "pune-isbm",
        "sensor_type": "pressure",
        "schema_version": "1.0",
        "data": data,
        "scenario_label": scenario_label,
    }


# ═════════════════════════════════════════════════════════════════════════
# 1. _extract_data_field helper
# ═════════════════════════════════════════════════════════════════════════


class TestExtractDataField:

    def test_extracts_float_from_dict(self):
        row = {"data": {"kva": 145.5}}
        assert _extract_data_field(row, "kva") == 145.5

    def test_returns_default_for_missing_key(self):
        row = {"data": {"kva": 145.5}}
        assert _extract_data_field(row, "missing_key", 99.0) == 99.0

    def test_handles_string_data(self):
        import json
        row = {"data": json.dumps({"kva": 200.0})}
        assert _extract_data_field(row, "kva") == 200.0

    def test_handles_empty_data(self):
        row = {"data": {}}
        assert _extract_data_field(row, "kva") == 0.0

    def test_handles_missing_data_key(self):
        row = {}
        assert _extract_data_field(row, "kva") == 0.0

    def test_handles_non_numeric_value(self):
        row = {"data": {"kva": "not_a_number"}}
        assert _extract_data_field(row, "kva") == 0.0


# ═════════════════════════════════════════════════════════════════════════
# 2. Hero 1 — Latest kVA
# ═════════════════════════════════════════════════════════════════════════


class TestGetLatestKva:

    @patch("omniview.dashboard.queries.query_latest")
    def test_returns_kva_from_latest_reading(self, mock_latest):
        mock_latest.return_value = [_make_elec_row(kva=147.6)]
        result = get_latest_kva("pune-comp-mfm384")
        assert result["kva"] == 147.6
        assert result["contract_kva"] == 500

    @patch("omniview.dashboard.queries.query_latest")
    def test_returns_zero_when_no_data(self, mock_latest):
        mock_latest.return_value = []
        result = get_latest_kva("pune-comp-mfm384")
        assert result["kva"] == 0.0

    @patch("omniview.dashboard.queries.query_latest")
    def test_includes_md_proximity(self, mock_latest):
        mock_latest.return_value = [_make_elec_row(kva=480)]
        result = get_latest_kva()
        assert result["md_proximity_percent"] == 96.0


# ═════════════════════════════════════════════════════════════════════════
# 3. kVA timeseries
# ═════════════════════════════════════════════════════════════════════════


class TestGetKvaTimeseries:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_returns_dataframe(self, mock_query):
        mock_query.return_value = [
            _make_elec_row(kva=140, time_offset_min=0),
            _make_elec_row(kva=145, time_offset_min=1),
        ]
        df = get_kva_timeseries("pune-comp-mfm384", hours=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "kva" in df.columns

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_empty_when_no_data(self, mock_query):
        mock_query.return_value = []
        df = get_kva_timeseries("pune-comp-mfm384", hours=1)
        assert df.empty


# ═════════════════════════════════════════════════════════════════════════
# 4. Peak kVA
# ═════════════════════════════════════════════════════════════════════════


class TestGetPeakKva:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_finds_peak_across_devices(self, mock_query):
        def side_effect(sensor_type, device_id, start, end):
            if device_id == "pune-comp-mfm384":
                return [_make_elec_row(kva=300)]
            return [_make_elec_row(kva=450, device_id="pune-isbm-mfm384")]

        mock_query.side_effect = side_effect
        peak = get_peak_kva_24h()
        assert peak == 450

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zero_when_no_data(self, mock_query):
        mock_query.return_value = []
        assert get_peak_kva_24h() == 0.0


# ═════════════════════════════════════════════════════════════════════════
# 5. Hero 2 — Penalty Avoided
# ═════════════════════════════════════════════════════════════════════════


class TestGetPenaltyAvoided:

    def test_full_headroom(self):
        result = get_penalty_avoided(peak_kva=0.0)
        assert result["headroom_kva"] == 500
        assert result["penalty_avoided_inr"] == 500 * 350

    def test_near_limit(self):
        result = get_penalty_avoided(peak_kva=480.0)
        assert result["headroom_kva"] == 20
        assert result["penalty_avoided_inr"] == 20 * 350

    def test_at_limit(self):
        result = get_penalty_avoided(peak_kva=500.0)
        assert result["headroom_kva"] == 0
        assert result["penalty_avoided_inr"] == 0

    def test_over_limit(self):
        result = get_penalty_avoided(peak_kva=550.0)
        assert result["headroom_kva"] == 0
        assert result["penalty_avoided_inr"] == 0


# ═════════════════════════════════════════════════════════════════════════
# 6. Hero 3 — SEC
# ═════════════════════════════════════════════════════════════════════════


class TestGetEnergyAndStrokes:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_computes_sec(self, mock_query):
        elec_rows = [_make_elec_row(kw=100, device_id="pune-isbm-mfm384")]
        stroke_rows = [_make_stroke_row(strokes=10)]

        def side_effect(sensor_type, device_id, start, end):
            if sensor_type == "electrical":
                return elec_rows
            return stroke_rows

        mock_query.side_effect = side_effect
        result = get_energy_and_strokes(hours=1)
        assert result["total_strokes"] == 10
        assert result["total_kwh"] > 0

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zero_strokes_no_crash(self, mock_query):
        mock_query.return_value = []
        result = get_energy_and_strokes(hours=1)
        assert result["sec_kwh_per_1k"] == 0
        assert result["total_strokes"] == 0


# ═════════════════════════════════════════════════════════════════════════
# 7. Hero 4 — Idle Load %
# ═════════════════════════════════════════════════════════════════════════


class TestGetIdleLoadPercent:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_detects_idle_by_scenario_label(self, mock_query):
        rows = [
            _make_elec_row(current=200, device_id="pune-isbm-mfm384"),
            _make_elec_row(current=5, device_id="pune-isbm-mfm384",
                           time_offset_min=1, scenario_label="lazy_idle"),
        ]
        mock_query.return_value = rows
        result = get_idle_load_percent(hours=1)
        assert result["idle_readings"] == 1
        assert result["total_readings"] == 2
        assert result["idle_pct"] == 50.0

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_detects_idle_by_low_current(self, mock_query):
        rows = [
            _make_elec_row(current=200, device_id="pune-isbm-mfm384"),
            _make_elec_row(current=5, device_id="pune-isbm-mfm384",
                           time_offset_min=1),
        ]
        mock_query.return_value = rows
        result = get_idle_load_percent(hours=1)
        assert result["idle_readings"] == 1

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zero_when_no_data(self, mock_query):
        mock_query.return_value = []
        result = get_idle_load_percent(hours=1)
        assert result["idle_pct"] == 0.0
        assert result["total_readings"] == 0


# ═════════════════════════════════════════════════════════════════════════
# 8. Alert Feed
# ═════════════════════════════════════════════════════════════════════════


class TestGetAlerts:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_extracts_scenario_labels(self, mock_query):
        def side_effect(sensor_type, device_id, start, end):
            if sensor_type == "electrical" and device_id == "pune-comp-mfm384":
                return [
                    _make_elec_row(kva=480, scenario_label="md_nearmiss"),
                ]
            return []

        mock_query.side_effect = side_effect
        df = get_alerts(hours=1)
        assert len(df) >= 1
        assert "md_nearmiss" in df["scenario_label"].values

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_empty_when_no_scenarios(self, mock_query):
        mock_query.return_value = [_make_elec_row(kva=140)]
        df = get_alerts(hours=1, sensor_types=["electrical"])
        assert df.empty

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_leak_proxy_from_pressure(self, mock_query):
        def side_effect(sensor_type, device_id, start, end):
            if sensor_type == "pressure":
                return [_make_pressure_row(scenario_label="leak_proxy")]
            return []

        mock_query.side_effect = side_effect
        df = get_alerts(hours=1, sensor_types=["pressure"])
        assert len(df) >= 1
        assert df.iloc[0]["severity"] == "WARNING"

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_alert_has_required_columns(self, mock_query):
        mock_query.return_value = [
            _make_elec_row(scenario_label="md_nearmiss"),
        ]
        df = get_alerts(hours=1, sensor_types=["electrical"])
        required = {"time", "severity", "title", "description", "icon",
                     "device_id", "sensor_type", "scenario_label"}
        assert required.issubset(set(df.columns))


# ═════════════════════════════════════════════════════════════════════════
# 9. Health Index Trend
# ═════════════════════════════════════════════════════════════════════════


class TestGetHealthIndexTrend:

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zone_a_is_100(self, mock_query):
        mock_query.return_value = [_make_vib_row(zone="ZONE_A")]
        df = get_health_index_trend()
        assert df.iloc[0]["hi_score"] == 100

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zone_b_is_75(self, mock_query):
        mock_query.return_value = [_make_vib_row(zone="ZONE_B")]
        df = get_health_index_trend()
        assert df.iloc[0]["hi_score"] == 75

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zone_c_is_50(self, mock_query):
        mock_query.return_value = [_make_vib_row(zone="ZONE_C")]
        df = get_health_index_trend()
        assert df.iloc[0]["hi_score"] == 50

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_zone_d_is_25(self, mock_query):
        mock_query.return_value = [_make_vib_row(zone="ZONE_D")]
        df = get_health_index_trend()
        assert df.iloc[0]["hi_score"] == 25

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_returns_dataframe_with_columns(self, mock_query):
        mock_query.return_value = [
            _make_vib_row(zone="ZONE_A", time_offset_min=0),
            _make_vib_row(zone="ZONE_B", time_offset_min=60),
        ]
        df = get_health_index_trend()
        assert len(df) == 2
        assert set(df.columns) == {"time", "hi_score", "iso_zone", "z_rms", "device_id"}

    @patch("omniview.dashboard.queries.query_by_time_range")
    def test_empty_when_no_data(self, mock_query):
        mock_query.return_value = []
        df = get_health_index_trend()
        assert df.empty
