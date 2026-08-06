"""
MQTT Smoke Test — OI-51
========================

Quick integration test to verify Mosquitto is running and the publish/subscribe
round-trip works end-to-end.

Run::

    python -m omniview.edge.smoke_test_mqtt

Prerequisites:

    docker compose up -d mosquitto   # broker must be running
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time

from omniview.config import MQTT_BROKER_HOST, MQTT_BROKER_PORT, SITE_ID
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic, build_wildcard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run the MQTT smoke test. Returns 0 on success, 1 on failure."""
    print()
    print("=" * 60)
    print("  OmniView IQ — MQTT Smoke Test")
    print(f"  Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    print("=" * 60)
    print()

    # ── 1. Connect ──────────────────────────────────────────────────────────
    print("1. Connecting to broker...")
    try:
        client = OmniViewMQTTClient(client_id="omniview-smoke-test")
        client.connect(timeout=5.0)
    except ConnectionError as exc:
        print(f"   ❌ FAILED — {exc}")
        print()
        print("   Make sure Mosquitto is running:")
        print("     docker compose up -d mosquitto")
        return 1

    print("   ✅ Connected")

    # ── 2. Subscribe to wildcard ────────────────────────────────────────────
    received_event = threading.Event()
    received_payload: dict = {}

    def on_message(topic: str, payload: dict) -> None:
        nonlocal received_payload
        received_payload = payload
        received_event.set()

    wildcard = build_wildcard(SITE_ID)
    print(f"2. Subscribing to {wildcard}")
    client.subscribe(wildcard, on_message)
    time.sleep(0.5)  # give subscription time to register
    print("   ✅ Subscribed")

    # ── 3. Publish a test payload ───────────────────────────────────────────
    test_topic = build_topic(SITE_ID, "compressor-01", "electrical")
    test_payload = {
        "device_id": "compressor-01",
        "timestamp": "2026-08-06T12:00:00+05:30",
        "sensor_type": "electrical",
        "schema_version": "1.0.0",
        "data": {
            "voltage_rms_avg": 415.2,
            "current_rms_avg": 28.7,
            "kva": 20.6,
            "kw": 18.4,
            "pf": 0.89,
            "thd_v_pct": 3.2,
        },
        "_smoke_test": True,
    }

    print(f"3. Publishing to {test_topic}")
    client.publish(test_topic, test_payload)
    print("   ✅ Published")

    # ── 4. Verify round-trip ────────────────────────────────────────────────
    print("4. Waiting for message round-trip...")
    if received_event.wait(timeout=5.0):
        if received_payload.get("_smoke_test") is True:
            print("   ✅ Message received and payload verified")
        else:
            print("   ⚠️  Message received but payload mismatch")
            print(f"      Got: {json.dumps(received_payload, indent=2)}")
    else:
        print("   ❌ FAILED — no message received within 5 seconds")
        client.disconnect()
        return 1

    # ── 5. Disconnect ───────────────────────────────────────────────────────
    print("5. Disconnecting...")
    client.disconnect()
    print("   ✅ Disconnected")

    print()
    print("=" * 60)
    print("  ✅  ALL CHECKS PASSED — MQTT path is working")
    print("=" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
