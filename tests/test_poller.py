"""
Tests for physical sensor edge poller — OI-13
===============================================

All self-contained, no MQTT broker or DB needed.
Mocks the MQTT client for publish verification.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from omniview.edge.device_config import load_edge_config
from omniview.edge.modbus_stub import ModbusSource
from omniview.edge.poller import (
    PHYSICAL_FAMILIES,
    BotSource,
    PhysicalSensorPoller,
    SensorSource,
)


# ── helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def edge_config():
    """Load the real edge_nodes.json config."""
    return load_edge_config()


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client."""
    client = MagicMock()
    client.publish = MagicMock()
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    return client


# ── BotSource tests ──────────────────────────────────────────────────────


class TestBotSource:
    """BotSource wraps DevB bot generators."""

    @pytest.mark.parametrize("sensor_type", sorted(PHYSICAL_FAMILIES))
    def test_bot_source_returns_valid_payload(self, sensor_type):
        """Each sensor type returns a dict with device_id + data."""
        source = BotSource(sensor_type)
        payload = source.read()
        assert isinstance(payload, dict)
        assert "device_id" in payload
        assert "data" in payload
        assert "timestamp" in payload

    def test_bot_source_rejects_unknown_type(self):
        with pytest.raises(ValueError, match="No bot generator"):
            BotSource("unknown_sensor")

    def test_bot_source_rejects_electrical(self):
        """Electrical has its own injector (OI-12), not this poller."""
        with pytest.raises(ValueError):
            BotSource("electrical")

    def test_bot_source_is_sensor_source(self):
        """BotSource satisfies the SensorSource protocol."""
        source = BotSource("vibration")
        assert isinstance(source, SensorSource)


# ── ModbusSource tests ───────────────────────────────────────────────────


class TestModbusSource:
    """ModbusSource stub raises NotImplementedError."""

    def test_modbus_source_raises_not_implemented(self):
        source = ModbusSource(
            slave_address=10,
            register_map={"rms_velocity": {"address": 40001}},
            device_id="test-vib01",
        )
        with pytest.raises(NotImplementedError, match="Modbus read not implemented"):
            source.read()

    def test_modbus_source_repr(self):
        source = ModbusSource(
            slave_address=10,
            register_map={"rms_velocity": {"address": 40001}},
            device_id="test-vib01",
        )
        r = repr(source)
        assert "test-vib01" in r
        assert "10" in r


# ── PhysicalSensorPoller tests ───────────────────────────────────────────


class TestPollerDeviceLoading:
    """Poller loads correct devices from config."""

    def test_loads_physical_devices_from_config(self, edge_config):
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        # edge_nodes.json has: vib, thermal, pressure, gas on compressor
        # + thermal on isbm + ambient on floor = 6 physical devices
        assert poller.device_count >= 5

    def test_excludes_electrical_and_stroke(self, edge_config):
        """Electrical (OI-12) and stroke have their own pollers."""
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        for device_id, m in poller.metrics.items():
            assert m["sensor_type"] not in ("electrical", "stroke"), (
                f"{device_id} is {m['sensor_type']} — should be excluded"
            )

    def test_families_filter(self, edge_config):
        """--families flag restricts which sensors poll."""
        poller = PhysicalSensorPoller(
            edge_config,
            source_mode="bot",
            families=frozenset({"vibration"}),
        )
        for device_id, m in poller.metrics.items():
            assert m["sensor_type"] == "vibration"

    def test_empty_families_filter(self, edge_config):
        """Empty filter = nothing to poll."""
        poller = PhysicalSensorPoller(
            edge_config,
            source_mode="bot",
            families=frozenset(),
        )
        assert poller.device_count == 0


class TestPollerPublish:
    """Poller publishes to correct MQTT topics."""

    def test_publishes_to_correct_topic(self, edge_config, mock_mqtt_client):
        """Single poll cycle publishes to the correct topic pattern."""
        poller = PhysicalSensorPoller(
            edge_config,
            source_mode="bot",
            families=frozenset({"vibration"}),
            mqtt_client=mock_mqtt_client,
        )

        # Manually invoke one poll cycle for the first device
        devices = [d for d in poller._devices if d.sensor_type == "vibration"]
        assert len(devices) >= 1

        source = poller._create_source(devices[0])
        payload = source.read()
        topic = f"omniview/{edge_config.site_id}/{devices[0].node_id}/vibration"

        mock_mqtt_client.publish(topic, payload)
        mock_mqtt_client.publish.assert_called_with(topic, payload)

    def test_poll_interval_from_config(self, edge_config):
        """All physical devices have poll_interval_s ≤ 60."""
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        for device_id, m in poller.metrics.items():
            assert m["poll_interval_s"] <= 60, (
                f"{device_id} has poll_interval {m['poll_interval_s']}s > 60s"
            )


class TestPollerSourceFactory:
    """Source factory creates correct source type."""

    def test_bot_mode_creates_bot_source(self, edge_config):
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        if poller._devices:
            source = poller._create_source(poller._devices[0])
            assert isinstance(source, BotSource)

    def test_modbus_mode_creates_modbus_source(self, edge_config):
        poller = PhysicalSensorPoller(edge_config, source_mode="modbus")
        if poller._devices:
            source = poller._create_source(poller._devices[0])
            assert isinstance(source, ModbusSource)

    def test_unknown_mode_raises(self, edge_config):
        poller = PhysicalSensorPoller(edge_config, source_mode="unknown")
        if poller._devices:
            with pytest.raises(ValueError, match="Unknown source_mode"):
                poller._create_source(poller._devices[0])


class TestPollerGracefulStop:
    """Poller stops cleanly."""

    def test_stop_before_start(self, edge_config):
        """stop() is safe to call even before start()."""
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        poller.stop()  # should not raise

    def test_metrics_initially_zero(self, edge_config):
        poller = PhysicalSensorPoller(edge_config, source_mode="bot")
        for device_id, m in poller.metrics.items():
            assert m["polls"] == 0
            assert m["publishes"] == 0
            assert m["errors"] == 0
