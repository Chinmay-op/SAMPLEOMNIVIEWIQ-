"""
Physical Sensor Edge Poller — OI-13
=====================================

Unified polling daemon for physical sensors (vibration, thermal,
pressure, gas, ambient).  Reads device configuration from
``edge_nodes.json`` (OI-52), polls at each device's configured
cadence (≤60 s), and publishes schema-valid MQTT payloads.

**Day-1 mode** (``--mode bot``): uses DevB's synthetic bot generators.
**Modbus mode** (``--mode modbus``): stub raises ``NotImplementedError``
until hardware cutover — swap only the ``ModbusSource.read()`` body.

Architecture::

    edge_nodes.json
         │
         ▼
    PhysicalSensorPoller
         │
         ├─ For each non-electrical device:
         │    SensorSource.read() → validate → MQTT publish
         │
         └─ One thread per node (all sensors on a node share a thread)

Usage::

    # Day-1 synthetic mode
    python -m omniview.edge.poller --mode bot

    # Specific families only
    python -m omniview.edge.poller --mode bot --families vibration,pressure

    # In code
    from omniview.edge.poller import PhysicalSensorPoller
    poller = PhysicalSensorPoller(config, source_mode="bot")
    poller.start()  # blocking
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Any, Protocol, runtime_checkable

from omniview.edge.bots import (
    generate_ambient,
    generate_gas,
    generate_pressure,
    generate_thermal,
    generate_vibration,
)
from omniview.edge.device_config import EdgeConfig, load_edge_config
from omniview.edge.modbus_stub import ModbusSource
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

logger = logging.getLogger(__name__)

# Sensor families handled by this poller (excludes electrical + stroke
# which have their own dedicated injectors / pollers)
PHYSICAL_FAMILIES: frozenset[str] = frozenset({
    "vibration",
    "thermal",
    "pressure",
    "gas",
    "ambient",
})

# Map sensor_type → DevB bot generator function
_BOT_GENERATORS: dict[str, Any] = {
    "vibration": generate_vibration,
    "thermal": generate_thermal,
    "pressure": generate_pressure,
    "gas": generate_gas,
    "ambient": generate_ambient,
}


# ── Source protocol ──────────────────────────────────────────────────────


@runtime_checkable
class SensorSource(Protocol):
    """Interface for sensor data sources — synthetic bots or live Modbus."""

    def read(self) -> dict[str, Any]:
        """Read one sample from the sensor.

        Returns
        -------
        dict
            A payload dict matching the sensor's JSON schema.
        """
        ...  # pragma: no cover


# ── Bot source (Day-1) ──────────────────────────────────────────────────


class BotSource:
    """Day-1 source: wraps DevB's ``generate_reading()`` functions.

    Parameters
    ----------
    sensor_type : str
        One of :data:`PHYSICAL_FAMILIES`.

    Raises
    ------
    ValueError
        If *sensor_type* has no bot generator registered.
    """

    def __init__(self, sensor_type: str) -> None:
        if sensor_type not in _BOT_GENERATORS:
            raise ValueError(
                f"No bot generator for sensor_type {sensor_type!r}. "
                f"Available: {sorted(_BOT_GENERATORS.keys())}"
            )
        self._sensor_type = sensor_type
        self._generator = _BOT_GENERATORS[sensor_type]

    def read(self) -> dict[str, Any]:
        """Generate one synthetic reading via DevB bot."""
        return self._generator()

    def __repr__(self) -> str:
        return f"BotSource({self._sensor_type!r})"


# ── Device poller state ─────────────────────────────────────────────────


class _DevicePollState:
    """Tracks per-device polling metrics."""

    def __init__(self, device: dict[str, Any], node_id: str) -> None:
        self.device_id: str = device["device_id"]
        self.sensor_type: str = device["sensor_type"]
        self.node_id: str = node_id
        self.poll_interval_s: int = device["poll_interval_s"]
        self.modbus_slave_address: int = device.get("modbus_slave_address", 0)
        self.register_map: dict = device.get("register_map", {})

        # Metrics
        self.polls: int = 0
        self.publishes: int = 0
        self.errors: int = 0


# ── Main poller ──────────────────────────────────────────────────────────


class PhysicalSensorPoller:
    """Unified edge poller for physical sensor families.

    Parameters
    ----------
    config : EdgeConfig
        Loaded edge device configuration (from OI-52).
    source_mode : str
        ``"bot"`` for Day-1 synthetic data, ``"modbus"`` for live
        Modbus RTU reads.
    families : frozenset[str] or None
        Restrict polling to specific families.  Defaults to all
        :data:`PHYSICAL_FAMILIES`.
    mqtt_client : OmniViewMQTTClient or None
        Optional pre-configured MQTT client.  If ``None``, a new
        client is created using default config.
    """

    def __init__(
        self,
        config: EdgeConfig,
        source_mode: str = "bot",
        families: frozenset[str] | None = None,
        mqtt_client: OmniViewMQTTClient | None = None,
    ) -> None:
        self._config = config
        self._source_mode = source_mode
        self._families = PHYSICAL_FAMILIES if families is None else families
        self._mqtt_client = mqtt_client
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

        # Build device list from config
        self._devices: list[_DevicePollState] = []
        for node_id in config.get_node_ids():
            for device in config.get_devices_for_node(node_id):
                sensor_type = device["sensor_type"]
                if sensor_type in self._families:
                    self._devices.append(_DevicePollState(device, node_id))

        logger.info(
            "PhysicalSensorPoller: mode=%s, families=%s, devices=%d",
            source_mode, sorted(self._families), len(self._devices),
        )

    # ── Source factory ───────────────────────────────────────────────

    def _create_source(self, device: _DevicePollState) -> SensorSource:
        """Create the appropriate source for a device."""
        if self._source_mode == "bot":
            return BotSource(device.sensor_type)
        elif self._source_mode == "modbus":
            return ModbusSource(
                slave_address=device.modbus_slave_address,
                register_map=device.register_map,
                device_id=device.device_id,
            )
        else:
            raise ValueError(
                f"Unknown source_mode {self._source_mode!r}. "
                f"Use 'bot' or 'modbus'."
            )

    # ── Poll loop (per node) ─────────────────────────────────────────

    def _poll_node(
        self,
        node_id: str,
        devices: list[_DevicePollState],
        client: OmniViewMQTTClient,
    ) -> None:
        """Poll all physical sensors on a node in a loop."""
        sources = {d.device_id: self._create_source(d) for d in devices}

        logger.info(
            "[%s] Polling %d devices: %s",
            node_id,
            len(devices),
            [d.device_id for d in devices],
        )

        while not self._stop_event.is_set():
            for device in devices:
                if self._stop_event.is_set():
                    break

                source = sources[device.device_id]
                try:
                    payload = source.read()
                    device.polls += 1

                    # Build MQTT topic
                    topic = build_topic(
                        self._config.site_id,
                        device.node_id,
                        device.sensor_type,
                    )

                    # Publish
                    client.publish(topic, payload)
                    device.publishes += 1

                    data = payload.get("data", {})
                    logger.debug(
                        "[%s] %s → %s (keys: %s)",
                        node_id,
                        device.device_id,
                        topic,
                        list(data.keys())[:3],
                    )

                except NotImplementedError as exc:
                    device.errors += 1
                    logger.error("[%s] %s: %s", node_id, device.device_id, exc)
                    # In modbus mode, don't spam — stop this device
                    break
                except Exception as exc:
                    device.errors += 1
                    logger.warning(
                        "[%s] %s poll error: %s",
                        node_id, device.device_id, exc,
                    )

            # Sleep for the shortest poll interval on this node
            min_interval = min(d.poll_interval_s for d in devices)
            self._stop_event.wait(min_interval)

    # ── Public API ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start polling all configured devices.  Blocks until stopped."""
        # Group devices by node
        nodes: dict[str, list[_DevicePollState]] = {}
        for device in self._devices:
            nodes.setdefault(device.node_id, []).append(device)

        if not nodes:
            logger.warning("No devices to poll — check config and families filter")
            return

        # Create or use provided MQTT client
        client = self._mqtt_client or OmniViewMQTTClient()

        try:
            if self._mqtt_client is None:
                client.connect()

            print(
                f"Physical Sensor Poller started — mode={self._source_mode}, "
                f"devices={len(self._devices)}, nodes={len(nodes)}"
            )

            # One thread per node
            for node_id, devices in nodes.items():
                t = threading.Thread(
                    target=self._poll_node,
                    args=(node_id, devices, client),
                    name=f"poller-{node_id}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

            # Block main thread until stop
            while not self._stop_event.is_set():
                self._stop_event.wait(1.0)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — stopping poller")
        finally:
            self.stop()
            if self._mqtt_client is None:
                client.disconnect()

    def stop(self) -> None:
        """Signal all poll threads to stop."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5.0)
        self._threads.clear()
        logger.info("Poller stopped")

    # ── Metrics ──────────────────────────────────────────────────────

    @property
    def metrics(self) -> dict[str, dict[str, int]]:
        """Per-device polling metrics."""
        return {
            d.device_id: {
                "sensor_type": d.sensor_type,
                "node_id": d.node_id,
                "polls": d.polls,
                "publishes": d.publishes,
                "errors": d.errors,
                "poll_interval_s": d.poll_interval_s,
            }
            for d in self._devices
        }

    @property
    def device_count(self) -> int:
        """Number of devices being polled."""
        return len(self._devices)


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the physical sensor poller."""
    parser = argparse.ArgumentParser(
        description="OmniView IQ — Physical Sensor Edge Poller (OI-13)",
    )
    parser.add_argument(
        "--mode",
        choices=["bot", "modbus"],
        default="bot",
        help="Data source: 'bot' (Day-1 synthetic) or 'modbus' (live hardware). Default: bot",
    )
    parser.add_argument(
        "--families",
        type=str,
        default=None,
        help=(
            "Comma-separated sensor families to poll. "
            f"Default: all ({','.join(sorted(PHYSICAL_FAMILIES))})"
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to edge_nodes.json config. Default: config/edge_nodes.json",
    )

    args = parser.parse_args()

    # Parse families
    families = None
    if args.families:
        families = frozenset(f.strip() for f in args.families.split(","))
        invalid = families - PHYSICAL_FAMILIES
        if invalid:
            parser.error(
                f"Unknown families: {invalid}. "
                f"Valid: {sorted(PHYSICAL_FAMILIES)}"
            )

    # Load config
    config = load_edge_config(config_path=args.config)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Setup signal handler
    poller = PhysicalSensorPoller(
        config=config,
        source_mode=args.mode,
        families=families,
    )

    def _signal_handler(sig, frame):
        print("\nShutting down...")
        poller.stop()

    signal.signal(signal.SIGINT, _signal_handler)

    poller.start()


if __name__ == "__main__":
    main()
