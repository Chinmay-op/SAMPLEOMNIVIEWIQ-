"""
Tests for adapters/wire.py — C4
=================================

Covers all 7 sensor families, unknown-family passthrough,
envelope adaptation, and the no-rename-elsewhere grep check.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from omniview.adapters.wire import FAMILIES, FIELD_MAPS, adapt, map_fields


# ════════════════════════════════════════════════════════════════════════
# 1. Family coverage — every family in the contract has a mapping
# ════════════════════════════════════════════════════════════════════════


CONTRACT_FAMILIES = frozenset(
    ["electrical", "vibration", "thermal", "pressure", "gas", "stroke", "ambient"]
)


class TestFamilyCoverage:
    """wire.py must define mappings for all 7 contract families."""

    def test_all_seven_families_present(self):
        assert FAMILIES == CONTRACT_FAMILIES

    def test_families_is_frozenset(self):
        assert isinstance(FAMILIES, frozenset)

    @pytest.mark.parametrize("family", sorted(CONTRACT_FAMILIES))
    def test_each_family_has_nonempty_map(self, family: str):
        assert family in FIELD_MAPS
        assert len(FIELD_MAPS[family]) > 0


# ════════════════════════════════════════════════════════════════════════
# 2. map_fields — per-family field renaming
# ════════════════════════════════════════════════════════════════════════


class TestMapFieldsElectrical:

    def test_renames_kva(self):
        data = {"apparent_power_kva_total": 142.5, "extra_field": 99}
        out = map_fields("electrical", data)
        assert out["kva"] == 142.5
        assert "apparent_power_kva_total" not in out

    def test_renames_kw(self):
        data = {"active_power_kw_total": 130.0}
        out = map_fields("electrical", data)
        assert out["kw"] == 130.0

    def test_renames_var(self):
        data = {"reactive_power_kvar_total": 45.2}
        out = map_fields("electrical", data)
        assert out["var"] == 45.2

    def test_renames_current(self):
        data = {"current_a_avg": 200.0}
        out = map_fields("electrical", data)
        assert out["current_a"] == 200.0

    def test_renames_pf(self):
        data = {"power_factor_avg": 0.95}
        out = map_fields("electrical", data)
        assert out["pf"] == 0.95

    def test_unknown_fields_pass_through(self):
        data = {"apparent_power_kva_total": 140, "brand_new_field": "hello"}
        out = map_fields("electrical", data)
        assert out["brand_new_field"] == "hello"


class TestMapFieldsVibration:

    def test_renames_z_rms(self):
        data = {"z_axis_rms_velocity_mm_sec": 2.3}
        out = map_fields("vibration", data)
        assert out["rms_velocity_mms"] == 2.3

    def test_renames_zone(self):
        data = {"iso_health_zone": "ZONE_A"}
        out = map_fields("vibration", data)
        assert out["zone"] == "ZONE_A"

    def test_renames_kurtosis(self):
        data = {"z_axis_kurtosis": 3.5}
        out = map_fields("vibration", data)
        assert out["kurtosis_z"] == 3.5


class TestMapFieldsThermal:

    def test_renames_zone_temp(self):
        data = {"present_value_pv_c": 245.0}
        out = map_fields("thermal", data)
        assert out["zone_temp_c"] == 245.0

    def test_renames_heater_duty(self):
        data = {"manipulated_variable_mv_heat_percent": 67.0}
        out = map_fields("thermal", data)
        assert out["heater_duty_pct"] == 67.0


class TestMapFieldsPressure:

    def test_pressure_bar_passthrough(self):
        data = {"pressure_bar": 33.0}
        out = map_fields("pressure", data)
        assert out["pressure_bar"] == 33.0

    def test_renames_trend(self):
        data = {"pressure_trend_5min": "rising"}
        out = map_fields("pressure", data)
        assert out["pressure_trend_5m"] == "rising"


class TestMapFieldsGas:

    def test_renames_ppm(self):
        data = {"gas_concentration_ppm": 12.5}
        out = map_fields("gas", data)
        assert out["gas_ppm"] == 12.5

    def test_renames_thermal_rise(self):
        data = {"rate_of_thermal_rise_c_per_min": 0.3}
        out = map_fields("gas", data)
        assert out["thermal_rise_rate"] == 0.3


class TestMapFieldsStroke:

    def test_renames_counter(self):
        data = {"counter_value": 12345}
        out = map_fields("stroke", data)
        assert out["cycle_count"] == 12345

    def test_renames_cycle_time(self):
        data = {"last_cycle_time_seconds": 2.5}
        out = map_fields("stroke", data)
        assert out["cycle_time_s"] == 2.5


class TestMapFieldsAmbient:

    def test_renames_temp(self):
        data = {"ambient_temp_c": 34.0}
        out = map_fields("ambient", data)
        assert out["temp_c"] == 34.0

    def test_renames_rssi(self):
        data = {"wireless_signal_strength_dbm": -65}
        out = map_fields("ambient", data)
        assert out["rssi_dbm"] == -65


class TestMapFieldsUnknownFamily:

    def test_unknown_family_passes_through(self):
        data = {"foo": 1, "bar": 2}
        out = map_fields("mystery_sensor", data)
        assert out == {"foo": 1, "bar": 2}


# ════════════════════════════════════════════════════════════════════════
# 3. adapt — full envelope adaptation
# ════════════════════════════════════════════════════════════════════════


class TestAdapt:

    def test_renames_data_fields_in_envelope(self):
        reading = {
            "device_id": "pune-comp-mfm384",
            "timestamp": "2026-09-10T10:00:00Z",
            "sensor_type": "electrical",
            "schema_version": "1.0",
            "data": {
                "apparent_power_kva_total": 140.0,
                "active_power_kw_total": 130.0,
            },
        }
        out = adapt(reading)
        assert out["data"]["kva"] == 140.0
        assert out["data"]["kw"] == 130.0
        # Envelope fields untouched
        assert out["device_id"] == "pune-comp-mfm384"
        assert out["sensor_type"] == "electrical"
        assert out["schema_version"] == "1.0"

    def test_does_not_mutate_original(self):
        reading = {
            "sensor_type": "electrical",
            "data": {"apparent_power_kva_total": 140.0},
        }
        out = adapt(reading)
        assert "apparent_power_kva_total" in reading["data"]
        assert "kva" not in reading["data"]
        assert "kva" in out["data"]

    def test_adapt_with_missing_data_key(self):
        reading = {"sensor_type": "electrical", "value": 42}
        out = adapt(reading)
        assert out == reading


# ════════════════════════════════════════════════════════════════════════
# 4. Grep check — no other file renames fields
# ════════════════════════════════════════════════════════════════════════


class TestNoRenameElsewhere:
    """Confirm no other Python file in src/ defines field-rename dicts
    using the same DevB descriptive names."""

    # Pick a distinctive DevB field name that should only appear in wire.py
    # and in the bot that emits it.
    DISTINCTIVE_FIELDS = [
        "apparent_power_kva_total",
        "z_axis_rms_velocity_mm_sec",
        "present_value_pv_c",
    ]

    @pytest.mark.parametrize("field_name", DISTINCTIVE_FIELDS)
    def test_field_not_used_as_rename_key_outside_wire(self, field_name: str):
        """Check that the field name doesn't appear as a rename *key*
        (i.e., in a dict mapping) outside of wire.py and the bots/parsers.
        """
        import pathlib
        import re

        src = pathlib.Path(r"d:\OmniView iq\omniview-iq-poc\src\omniview")
        # Files that legitimately use DevB field names (producing payloads,
        # not renaming them):
        allowed = {
            "wire.py",
            "electrical_bot.py", "vibration_bot.py", "thermal_bot.py",
            "pressure_bot.py", "gas_bot.py", "stroke_bot.py", "ambient_bot.py",
            "modbus_parser.py", "vibration_parser.py", "thermal_parser.py",
            "cwru_loader.py",
        }
        pattern = re.compile(rf'["\']{ re.escape(field_name) }["\']\s*:')
        hits = []
        for f in src.rglob("*.py"):
            if f.name in allowed:
                continue
            text = f.read_text(errors="ignore")
            if pattern.search(text):
                hits.append(f.name)

        assert hits == [], (
            f"Field '{field_name}' found as a mapping key in: {', '.join(hits)}"
        )
