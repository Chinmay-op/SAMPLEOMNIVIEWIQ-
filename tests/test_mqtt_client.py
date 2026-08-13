"""
Unit tests for omniview.edge.mqtt_client — OI-51

Uses mocked paho-mqtt internals — no real broker required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from omniview.edge.mqtt_client import OmniViewMQTTClient


class TestOmniViewMQTTClientInit:
    """Test client initialisation and configuration."""

    def test_default_config(self):
        client = OmniViewMQTTClient()
        assert client._broker_host == "localhost"
        assert client._broker_port == 1883
        assert client._qos == 1

    def test_custom_config(self):
        client = OmniViewMQTTClient(
            broker_host="mqtt.example.com",
            broker_port=8883,
            qos=0,
            keepalive=30,
        )
        assert client._broker_host == "mqtt.example.com"
        assert client._broker_port == 8883
        assert client._qos == 0
        assert client._keepalive == 30

    def test_not_connected_initially(self):
        client = OmniViewMQTTClient()
        assert client.is_connected is False


class TestPublish:
    """Test publish behaviour (mocked broker)."""

    def _make_connected_client(self) -> OmniViewMQTTClient:
        """Create a client that appears connected (for testing publish)."""
        client = OmniViewMQTTClient()
        client._connected.set()  # simulate successful connect
        client._client.publish = MagicMock(
            return_value=MagicMock(mid=42)
        )
        return client

    def test_publish_json_serialization(self):
        client = self._make_connected_client()
        payload = {"voltage": 415.2, "current": 28.7}

        client.publish("omniview/pune-isbm/compressor-01/electrical", payload)

        call_args = client._client.publish.call_args
        published_topic = call_args[0][0]
        published_message = call_args[0][1]

        assert published_topic == "omniview/pune-isbm/compressor-01/electrical"
        # Verify it's valid JSON
        decoded = json.loads(published_message)
        assert decoded["voltage"] == 415.2
        assert decoded["current"] == 28.7

    def test_publish_uses_default_qos(self):
        client = self._make_connected_client()
        client.publish("test/topic", {"key": "value"})

        call_kwargs = client._client.publish.call_args
        assert call_kwargs.kwargs["qos"] == 1  # default QoS

    def test_publish_qos_override(self):
        client = self._make_connected_client()
        client.publish("test/topic", {"key": "value"}, qos=0)

        call_kwargs = client._client.publish.call_args
        assert call_kwargs.kwargs["qos"] == 0

    def test_publish_when_disconnected_buffers(self, tmp_path):
        from omniview.config import BUFFER_DB_PATH
        
        # Override buffer path to use tmp_path
        with patch("omniview.edge.mqtt_client.BUFFER_DB_PATH", str(tmp_path / "test_buffer.db")):
            client = OmniViewMQTTClient()
            # Initial state is disconnected
            assert client.is_connected is False
            
            client.publish("test/topic", {"key": "value"})
            
            # Message should be stored in buffer
            assert client._buffer.count() == 1
            messages = client._buffer.drain(batch_size=1)
            assert messages[0].topic == "test/topic"
            assert messages[0].payload == {"key": "value"}


class TestSubscribe:
    """Test subscribe and message routing (mocked broker)."""

    def test_subscribe_registers_callback(self):
        client = OmniViewMQTTClient()
        callback = MagicMock()

        client.subscribe("omniview/pune-isbm/#", callback)

        assert "omniview/pune-isbm/#" in client._subscriptions
        assert callback in client._subscriptions["omniview/pune-isbm/#"]

    def test_message_routing_calls_callback(self):
        client = OmniViewMQTTClient()
        callback = MagicMock()
        client._subscriptions["omniview/pune-isbm/#"] = [callback]

        # Simulate an incoming message
        mock_message = MagicMock()
        mock_message.topic = "omniview/pune-isbm/compressor-01/electrical"
        mock_message.payload = json.dumps({"voltage": 415.2}).encode("utf-8")

        client._on_message(client._client, None, mock_message)

        callback.assert_called_once_with(
            "omniview/pune-isbm/compressor-01/electrical",
            {"voltage": 415.2},
        )

    def test_invalid_json_does_not_crash(self):
        """Ensure malformed payloads are logged, not raised."""
        client = OmniViewMQTTClient()
        callback = MagicMock()
        client._subscriptions["test/#"] = [callback]

        mock_message = MagicMock()
        mock_message.topic = "test/topic"
        mock_message.payload = b"not valid json {{"

        # Should not raise
        client._on_message(client._client, None, mock_message)

        # Callback should NOT have been called
        callback.assert_not_called()


class TestContextManager:
    """Test context manager protocol."""

    @patch.object(OmniViewMQTTClient, "connect")
    @patch.object(OmniViewMQTTClient, "disconnect")
    def test_context_manager_calls_connect_disconnect(
        self, mock_disconnect: MagicMock, mock_connect: MagicMock
    ):
        with OmniViewMQTTClient() as client:
            mock_connect.assert_called_once()
            assert isinstance(client, OmniViewMQTTClient)

        mock_disconnect.assert_called_once()
