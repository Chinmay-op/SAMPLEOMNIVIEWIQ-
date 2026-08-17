"""
Tests for edge device configuration loader (device_config.py).

Validates:
* Config loads and validates against schema
* All POC nodes represented (compressor-01, isbm-01, floor)
* device_id → node resolution
* Poll interval lookups
* Sensor type lookups
* Register map lookups
* Error handling for unknown devices/nodes
* Duplicate device_id detection
* Schema validation catches invalid configs
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from omniview.edge.device_config import (
    EdgeConfig,
    EdgeConfigError,
    load_edge_config,
    DEFAULT_CONFIG_PATH,
    DEFAULT_SCHEMA_PATH,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config() -> EdgeConfig:
    """Load the real edge config from the repo."""
    return load_edge_config()


@pytest.fixture
def minimal_config_dict() -> dict:
    """A minimal valid config dict for unit tests."""
    return {
        "config_version": "1.0.0",
        "site": {
            "site_id": "test-site",
            "name": "Test Site",
            "contracted_demand_kva": 100,
        },
        "nodes": {
            "node-a": {
                "display_name": "Node A",
                "location": "Test location",
                "devices": [
                    {
                        "device_id": "dev-001",
                        "sensor_type": "electrical",
                        "hardware": "Test Meter",
                        "protocol": "modbus_rtu",
                        "modbus_slave_address": 1,
                        "poll_interval_s": 15,
                    },
                    {
                        "device_id": "dev-002",
                        "sensor_type": "vibration",
                        "hardware": "Test Vib",
                        "protocol": "wireless_modbus",
                        "modbus_slave_address": 10,
                        "poll_interval_s": 60,
                    },
                ],
            }
        },
    }


def _write_json(path: Path, data: dict) -> None:
    """Helper to write JSON to a temp file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ── Config file existence ───────────────────────────────────────────────────


class TestConfigFileExists:
    """Verify that the config and schema files exist in the repo."""

    def test_edge_nodes_json_exists(self):
        assert DEFAULT_CONFIG_PATH.exists(), (
            f"edge_nodes.json not found at {DEFAULT_CONFIG_PATH}"
        )

    def test_edge_config_schema_exists(self):
        assert DEFAULT_SCHEMA_PATH.exists(), (
            f"edge_config_schema.json not found at {DEFAULT_SCHEMA_PATH}"
        )


# ── Loading and validation ──────────────────────────────────────────────────


class TestLoadEdgeConfig:
    """Test config loading from the actual repo file."""

    def test_loads_without_error(self, config):
        assert config is not None

    def test_repr(self, config):
        r = repr(config)
        assert "EdgeConfig" in r
        assert "pune-isbm" in r

    def test_config_version(self, config):
        assert config.config_version == "1.0.0"


# ── Site-level properties ──────────────────────────────────────────────────


class TestSiteProperties:
    """Verify site-level metadata from the Pune POC config."""

    def test_site_id(self, config):
        assert config.site_id == "pune-isbm"

    def test_site_name(self, config):
        assert "Pune" in config.site_name

    def test_contracted_demand(self, config):
        assert config.contracted_demand_kva == 500

    def test_timezone(self, config):
        assert config.timezone == "Asia/Kolkata"

    def test_utility(self, config):
        assert config.utility == "MSEDCL"

    def test_tariff_category(self, config):
        assert config.tariff_category == "HT-I"


# ── POC nodes represented ──────────────────────────────────────────────────


class TestPOCNodes:
    """Both POC nodes (compressor + ISBM feed) must be present."""

    def test_compressor_node_exists(self, config):
        node = config.get_node("compressor-01")
        assert node is not None
        assert "Compressor" in node["display_name"]

    def test_isbm_node_exists(self, config):
        node = config.get_node("isbm-01")
        assert node is not None
        assert "ISBM" in node["display_name"]

    def test_floor_node_exists(self, config):
        node = config.get_node("floor")
        assert node is not None

    def test_node_count(self, config):
        assert config.node_count == 3  # compressor, isbm, floor

    def test_get_node_ids(self, config):
        ids = config.get_node_ids()
        assert "compressor-01" in ids
        assert "isbm-01" in ids
        assert "floor" in ids

    def test_unknown_node_raises(self, config):
        with pytest.raises(KeyError, match="Unknown node_id"):
            config.get_node("nonexistent-node")


# ── Device lookups ──────────────────────────────────────────────────────────


class TestDeviceLookups:
    """Test device_id → node resolution and device metadata."""

    def test_compressor_electrical_device(self, config):
        device = config.get_device("pune-comp-mfm384")
        assert device["sensor_type"] == "electrical"
        assert device["hardware"] == "Selec MFM384-C-CE"

    def test_compressor_vibration_device(self, config):
        device = config.get_device("pune-comp-vib01")
        assert device["sensor_type"] == "vibration"

    def test_compressor_pressure_device(self, config):
        device = config.get_device("pune-comp-wika01")
        assert device["sensor_type"] == "pressure"
        assert "WIKA" in device["hardware"]

    def test_isbm_electrical_device(self, config):
        device = config.get_device("pune-isbm-mfm384")
        assert device["sensor_type"] == "electrical"
        assert device["modbus_slave_address"] == 2

    def test_isbm_thermal_device(self, config):
        device = config.get_device("pune-isbm-therm01")
        assert device["sensor_type"] == "thermal"

    def test_isbm_stroke_device(self, config):
        device = config.get_device("pune-isbm-stroke01")
        assert device["sensor_type"] == "stroke"

    def test_floor_ambient_device(self, config):
        device = config.get_device("pune-floor-ambient01")
        assert device["sensor_type"] == "ambient"

    def test_unknown_device_raises(self, config):
        with pytest.raises(KeyError, match="Unknown device_id"):
            config.get_device("nonexistent-device")

    def test_get_all_device_ids(self, config):
        ids = config.get_all_device_ids()
        assert len(ids) >= 9  # 5 compressor + 3 isbm + 1 floor
        assert ids == sorted(ids)  # sorted


# ── device_id → node_id resolution ─────────────────────────────────────────


class TestDeviceToNodeResolution:
    """The core mapping: which node does a device belong to."""

    def test_compressor_devices_resolve_to_compressor(self, config):
        assert config.get_node_for_device("pune-comp-mfm384") == "compressor-01"
        assert config.get_node_for_device("pune-comp-vib01") == "compressor-01"
        assert config.get_node_for_device("pune-comp-wika01") == "compressor-01"

    def test_isbm_devices_resolve_to_isbm(self, config):
        assert config.get_node_for_device("pune-isbm-mfm384") == "isbm-01"
        assert config.get_node_for_device("pune-isbm-therm01") == "isbm-01"
        assert config.get_node_for_device("pune-isbm-stroke01") == "isbm-01"

    def test_floor_devices_resolve_to_floor(self, config):
        assert config.get_node_for_device("pune-floor-ambient01") == "floor"

    def test_unknown_device_node_raises(self, config):
        with pytest.raises(KeyError, match="Unknown device_id"):
            config.get_node_for_device("fake-device")


# ── Poll intervals ──────────────────────────────────────────────────────────


class TestPollIntervals:
    """Verify poll intervals match architecture doc specs."""

    def test_electrical_poll_15s(self, config):
        """FR1: electrical parameters polled at ≤15s."""
        assert config.get_poll_interval("pune-comp-mfm384") == 15
        assert config.get_poll_interval("pune-isbm-mfm384") == 15

    def test_vibration_poll_60s(self, config):
        assert config.get_poll_interval("pune-comp-vib01") == 60

    def test_pressure_poll_60s(self, config):
        assert config.get_poll_interval("pune-comp-wika01") == 60

    def test_thermal_poll_60s(self, config):
        assert config.get_poll_interval("pune-comp-therm01") == 60
        assert config.get_poll_interval("pune-isbm-therm01") == 60

    def test_stroke_poll_15s(self, config):
        """Stroke counter polls at electrical cadence for correlation."""
        assert config.get_poll_interval("pune-isbm-stroke01") == 15

    def test_ambient_poll_60s(self, config):
        assert config.get_poll_interval("pune-floor-ambient01") == 60


# ── Sensor type lookups ────────────────────────────────────────────────────


class TestSensorTypeLookups:
    """Test sensor_type extraction and filtering."""

    def test_get_sensor_type(self, config):
        assert config.get_sensor_type("pune-comp-mfm384") == "electrical"
        assert config.get_sensor_type("pune-comp-vib01") == "vibration"

    def test_get_devices_by_sensor_type_electrical(self, config):
        elec = config.get_devices_by_sensor_type("electrical")
        assert len(elec) == 2  # compressor + isbm
        assert all(d["sensor_type"] == "electrical" for d in elec)

    def test_get_devices_by_sensor_type_vibration(self, config):
        vib = config.get_devices_by_sensor_type("vibration")
        assert len(vib) == 1

    def test_get_devices_by_sensor_type_nonexistent(self, config):
        result = config.get_devices_by_sensor_type("nonexistent")
        assert result == []


# ── Register maps ──────────────────────────────────────────────────────────


class TestRegisterMaps:
    """Verify Modbus register map metadata."""

    def test_compressor_electrical_register_map(self, config):
        rmap = config.get_register_map("pune-comp-mfm384")
        assert "voltage_v_ln_avg" in rmap
        assert "apparent_power_kva_total" in rmap
        assert rmap["voltage_v_ln_avg"]["type"] == "float32"
        assert rmap["voltage_v_ln_avg"]["unit"] == "V"

    def test_vibration_register_map(self, config):
        rmap = config.get_register_map("pune-comp-vib01")
        assert "rms_velocity_mm_s" in rmap

    def test_pressure_register_map(self, config):
        rmap = config.get_register_map("pune-comp-wika01")
        assert "pressure_bar" in rmap

    def test_get_devices_for_node(self, config):
        devices = config.get_devices_for_node("compressor-01")
        assert len(devices) == 5  # electrical, vibration, pressure, thermal, gas


# ── Devices-for-node ───────────────────────────────────────────────────────


class TestDevicesForNode:
    """Test listing all devices on a node."""

    def test_compressor_device_count(self, config):
        devices = config.get_devices_for_node("compressor-01")
        assert len(devices) == 5

    def test_isbm_device_count(self, config):
        devices = config.get_devices_for_node("isbm-01")
        assert len(devices) == 3

    def test_floor_device_count(self, config):
        devices = config.get_devices_for_node("floor")
        assert len(devices) == 1

    def test_unknown_node_raises(self, config):
        with pytest.raises(KeyError, match="Unknown node_id"):
            config.get_devices_for_node("nonexistent")


# ── Edge cases and error handling ──────────────────────────────────────────


class TestErrorHandling:
    """Test config loading failure modes."""

    def test_missing_config_file(self, tmp_path):
        with pytest.raises(EdgeConfigError, match="not found"):
            load_edge_config(config_path=tmp_path / "missing.json")

    def test_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        with pytest.raises(EdgeConfigError, match="not valid JSON"):
            load_edge_config(config_path=bad_file, validate=False)

    def test_schema_validation_failure(self, tmp_path):
        """Config missing required field should fail validation."""
        bad_config = {"config_version": "1.0.0"}  # missing "site" and "nodes"
        config_file = tmp_path / "bad_config.json"
        _write_json(config_file, bad_config)

        with pytest.raises(EdgeConfigError, match="validation failed"):
            load_edge_config(config_path=config_file)

    def test_duplicate_device_id_raises(self, minimal_config_dict, tmp_path):
        """Duplicate device_id across nodes should raise."""
        # Add a second node with a duplicate device_id
        minimal_config_dict["nodes"]["node-b"] = {
            "display_name": "Node B",
            "location": "Another location",
            "devices": [
                {
                    "device_id": "dev-001",  # duplicate!
                    "sensor_type": "pressure",
                    "hardware": "Test Pressure",
                    "protocol": "modbus_rtu",
                    "modbus_slave_address": 20,
                    "poll_interval_s": 60,
                },
            ],
        }
        config_file = tmp_path / "dup.json"
        _write_json(config_file, minimal_config_dict)

        with pytest.raises(EdgeConfigError, match="Duplicate device_id"):
            load_edge_config(config_path=config_file, validate=False)

    def test_load_without_validation(self, minimal_config_dict, tmp_path):
        """Config loads successfully when validate=False."""
        config_file = tmp_path / "ok.json"
        _write_json(config_file, minimal_config_dict)

        cfg = load_edge_config(config_path=config_file, validate=False)
        assert cfg.site_id == "test-site"
        assert cfg.device_count == 2

    def test_missing_schema_warns_but_loads(self, minimal_config_dict, tmp_path):
        """Missing schema file should warn and still load."""
        config_file = tmp_path / "ok.json"
        _write_json(config_file, minimal_config_dict)

        cfg = load_edge_config(
            config_path=config_file,
            schema_path=tmp_path / "missing_schema.json",
        )
        assert cfg.site_id == "test-site"


# ── Counts / properties ────────────────────────────────────────────────────


class TestCounts:
    """Verify aggregate counts match expected POC structure."""

    def test_total_device_count(self, config):
        assert config.device_count == 9  # 5 + 3 + 1

    def test_total_node_count(self, config):
        assert config.node_count == 3
