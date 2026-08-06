"""
MQTT Client — OI-51
====================

Production-grade MQTT client wrapper around ``paho-mqtt`` v2.

Features:

* Connects to Mosquitto using centralised config from :mod:`omniview.config`
* Publishes JSON-serialised payloads with configurable QoS (default: 1)
* Subscribes to topics with message routing via callbacks
* Automatic reconnect with exponential back-off
* Context-manager support (``with OmniViewMQTTClient() as client:``)
* Python ``logging`` throughout (no print statements)

Usage::

    from omniview.edge.mqtt_client import OmniViewMQTTClient

    with OmniViewMQTTClient() as client:
        client.publish("omniview/pune-isbm/compressor-01/electrical", payload)

Design notes:

* QoS 1 (at-least-once) is the default — matches FR7's no-data-loss
  requirement.  The TSDB insert layer (OI-54/55) handles dedup via
  idempotent upserts, giving effectively-exactly-once semantics.
* Uses ``paho-mqtt`` v2 ``CallbackAPIVersion.VERSION2`` for forward
  compatibility.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

import paho.mqtt.client as mqtt

from omniview.config import (
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_CLIENT_ID,
    MQTT_KEEPALIVE,
    MQTT_QOS,
)

logger = logging.getLogger(__name__)

# Type alias for subscriber callbacks
MessageCallback = Callable[[str, dict[str, Any]], None]


class OmniViewMQTTClient:
    """High-level MQTT client for the OmniView IQ edge layer.

    Parameters
    ----------
    client_id : str, optional
        Override the default client ID from config.
    broker_host : str, optional
        Override the default broker host from config.
    broker_port : int, optional
        Override the default broker port from config.
    qos : int, optional
        Default QoS level for publish/subscribe (0, 1, or 2).
    keepalive : int, optional
        MQTT keepalive interval in seconds.
    """

    def __init__(
        self,
        client_id: str | None = None,
        broker_host: str | None = None,
        broker_port: int | None = None,
        qos: int | None = None,
        keepalive: int | None = None,
    ) -> None:
        self._broker_host = broker_host or MQTT_BROKER_HOST
        self._broker_port = broker_port or MQTT_BROKER_PORT
        self._client_id = client_id or MQTT_CLIENT_ID
        self._qos = qos if qos is not None else MQTT_QOS
        self._keepalive = keepalive or MQTT_KEEPALIVE

        # Callback registry: topic_filter -> list of callbacks
        self._subscriptions: dict[str, list[MessageCallback]] = {}

        # Connection state
        self._connected = threading.Event()
        self._reconnect_delay = 1  # seconds, grows with back-off
        self._max_reconnect_delay = 60

        # Initialise paho client (v2 callback API)
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            protocol=mqtt.MQTTv5,
        )

        # Wire up paho callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ── Connection lifecycle ────────────────────────────────────────────────

    def connect(self, *, timeout: float = 10.0) -> None:
        """Connect to the MQTT broker and start the network loop.

        Parameters
        ----------
        timeout : float
            Maximum seconds to wait for the initial connection.

        Raises
        ------
        ConnectionError
            If the broker is unreachable within *timeout*.
        """
        logger.info(
            "Connecting to MQTT broker at %s:%d (client_id=%s)",
            self._broker_host,
            self._broker_port,
            self._client_id,
        )
        try:
            self._client.connect(
                self._broker_host,
                self._broker_port,
                keepalive=self._keepalive,
            )
        except OSError as exc:
            raise ConnectionError(
                f"Cannot reach MQTT broker at "
                f"{self._broker_host}:{self._broker_port}: {exc}"
            ) from exc

        self._client.loop_start()

        if not self._connected.wait(timeout=timeout):
            self._client.loop_stop()
            raise ConnectionError(
                f"MQTT broker at {self._broker_host}:{self._broker_port} "
                f"did not acknowledge connection within {timeout}s"
            )

        logger.info("MQTT connected successfully")

    def disconnect(self) -> None:
        """Gracefully disconnect from the MQTT broker."""
        logger.info("Disconnecting from MQTT broker")
        self._client.loop_stop()
        self._client.disconnect()
        self._connected.clear()

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if currently connected to the broker."""
        return self._connected.is_set()

    # ── Context manager ─────────────────────────────────────────────────────

    def __enter__(self) -> OmniViewMQTTClient:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.disconnect()

    # ── Publish ─────────────────────────────────────────────────────────────

    def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int | None = None,
        retain: bool = False,
    ) -> None:
        """Publish a JSON payload to an MQTT topic.

        Parameters
        ----------
        topic : str
            MQTT topic string.
        payload : dict
            Dictionary to JSON-serialise and publish.
        qos : int, optional
            Override default QoS for this message.
        retain : bool
            Whether the broker should retain this message.

        Raises
        ------
        RuntimeError
            If not connected to the broker.
        """
        if not self._connected.is_set():
            raise RuntimeError(
                "Cannot publish: not connected to MQTT broker. "
                "Call connect() first."
            )

        effective_qos = qos if qos is not None else self._qos
        message = json.dumps(payload, default=str)

        info = self._client.publish(
            topic, message, qos=effective_qos, retain=retain
        )

        logger.debug(
            "Published to %s (qos=%d, %d bytes, mid=%s)",
            topic,
            effective_qos,
            len(message),
            info.mid,
        )

    # ── Subscribe ───────────────────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        callback: MessageCallback,
        qos: int | None = None,
    ) -> None:
        """Subscribe to an MQTT topic with a callback.

        Parameters
        ----------
        topic : str
            MQTT topic (supports wildcards ``+`` and ``#``).
        callback : callable
            Called with ``(topic_str, payload_dict)`` for each message.
        qos : int, optional
            Override default QoS for this subscription.
        """
        effective_qos = qos if qos is not None else self._qos

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []

        self._subscriptions[topic].append(callback)

        if self._connected.is_set():
            self._client.subscribe(topic, qos=effective_qos)
            logger.info("Subscribed to %s (qos=%d)", topic, effective_qos)
        else:
            logger.warning(
                "Registered subscription for %s but not yet connected — "
                "will subscribe on connect",
                topic,
            )

    # ── Paho callbacks (internal) ───────────────────────────────────────────

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Handle successful broker connection."""
        if reason_code == 0:
            logger.info("MQTT broker connection established")
            self._connected.set()
            self._reconnect_delay = 1  # reset back-off

            # Re-subscribe to any registered topics (handles reconnects)
            for topic in self._subscriptions:
                client.subscribe(topic, qos=self._qos)
                logger.info("Re-subscribed to %s on reconnect", topic)
        else:
            logger.error("MQTT connection failed: reason_code=%s", reason_code)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Handle broker disconnection with exponential back-off reconnect."""
        self._connected.clear()

        if reason_code == 0:
            logger.info("MQTT disconnected cleanly")
            return

        logger.warning(
            "MQTT unexpected disconnect (reason_code=%s). "
            "Will attempt reconnect in %ds",
            reason_code,
            self._reconnect_delay,
        )

        # Schedule reconnect attempt (paho loop_start handles the retry
        # internally, but we log the back-off for observability)
        self._reconnect_delay = min(
            self._reconnect_delay * 2, self._max_reconnect_delay
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Route incoming messages to registered callbacks."""
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(
                "Failed to decode message on %s: %s (raw: %s)",
                topic,
                exc,
                message.payload[:200],
            )
            return

        logger.debug("Received message on %s (%d bytes)", topic, len(message.payload))

        # Match against subscriptions (exact and wildcard)
        for topic_filter, callbacks in self._subscriptions.items():
            if mqtt.topic_matches_sub(topic_filter, topic):
                for cb in callbacks:
                    try:
                        cb(topic, payload)
                    except Exception:
                        logger.exception(
                            "Callback error for topic %s (filter: %s)",
                            topic,
                            topic_filter,
                        )
