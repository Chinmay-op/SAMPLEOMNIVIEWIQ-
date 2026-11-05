"""
OmniView IQ — Live Bots & Ingest Runner
========================================

Runs all 7 sensor simulators concurrently in background threads alongside the
MQTT → TimescaleDB subscriber. Continuously feeds live physical sensor telemetry
into Mosquitto and TimescaleDB for the Feature 2 Live Tester Dashboard.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from omniview.edge.bots import (
    generate_ambient,
    generate_electrical,
    generate_gas,
    generate_pressure,
    generate_stroke,
    generate_thermal,
    generate_vibration,
)
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic
from omniview.ingest.subscriber import run_subscriber

logger = logging.getLogger(__name__)

# Polling interval in seconds (default 5s for responsive live dashboard testing)
BOT_CYCLE_INTERVAL_S = 5.0


class LiveBotsManager:
    """Manages concurrent execution of the 7 sensor bots and the TSDB subscriber."""

    def __init__(self, cycle_interval: float = BOT_CYCLE_INTERVAL_S):
        self.cycle_interval = cycle_interval
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._counts = {
            "electrical": 0,
            "vibration": 0,
            "thermal": 0,
            "pressure": 0,
            "gas": 0,
            "stroke": 0,
            "ambient": 0,
        }
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start subscriber and all 7 bot publisher loops."""
        self._stop_event.clear()

        # 1. Start subscriber thread
        sub_thread = threading.Thread(
            target=self._run_subscriber_wrapper,
            name="SubscriberWorker",
            daemon=True,
        )
        sub_thread.start()
        self._threads.append(sub_thread)

        # Allow subscriber to connect and establish topic wildcard
        time.sleep(1.5)

        # 2. Start bot loops
        bot_configs = [
            ("electrical", "compressor-01", generate_electrical),
            ("vibration", "compressor-01", generate_vibration),
            ("thermal", "compressor-01", generate_thermal),
            ("pressure", "compressor-01", generate_pressure),
            ("gas", "compressor-01", generate_gas),
            ("stroke", "isbm-01", generate_stroke),
            ("ambient", "floor", generate_ambient),
        ]

        for sensor_type, node, generator_fn in bot_configs:
            t = threading.Thread(
                target=self._run_bot_loop,
                args=(sensor_type, node, generator_fn),
                name=f"BotWorker-{sensor_type}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        logger.info("LiveBotsManager started: 1 subscriber + 7 bots running.")

    def stop(self) -> None:
        """Signal all threads to stop."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1.0)
        self._threads.clear()
        logger.info("LiveBotsManager stopped.")

    def get_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def _run_subscriber_wrapper(self) -> None:
        try:
            run_subscriber()
        except Exception as e:
            logger.warning("Subscriber encountered error or stopped: %s", e)

    def _run_bot_loop(self, sensor_type: str, node: str, generator_fn: Any) -> None:
        topic = build_topic("pune-isbm", node, sensor_type)
        try:
            with OmniViewMQTTClient() as client:
                while not self._stop_event.is_set():
                    payload = generator_fn()
                    # Ensure timestamp is current UTC
                    if isinstance(payload, dict):
                        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
                    client.publish(topic, payload)
                    with self._lock:
                        self._counts[sensor_type] += 1
                    time.sleep(self.cycle_interval)
        except Exception as e:
            logger.warning("Bot loop [%s] error: %s", sensor_type, e)


# Global singleton for in-process or dashboard management
_manager_instance: LiveBotsManager | None = None


def get_live_bots_manager() -> LiveBotsManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LiveBotsManager()
    return _manager_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Starting Live Bots & Ingest Runner (Ctrl+C to stop)...")
    mgr = get_live_bots_manager()
    mgr.start()
    try:
        while True:
            time.sleep(5)
            print("Published sensor counts:", mgr.get_counts())
    except KeyboardInterrupt:
        print("\nStopping...")
        mgr.stop()

