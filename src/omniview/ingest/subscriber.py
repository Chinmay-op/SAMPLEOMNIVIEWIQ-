"""
MQTT → TimescaleDB Subscriber Bridge — OI-54
==============================================

Listens to all sensor topics for a site and writes each payload into
the corresponding TimescaleDB hypertable.

This is the "glue" between the edge/MQTT layer (OI-51) and the cloud
storage layer (OI-54).  It runs as a standalone long-lived process.

Usage::

    # Default: subscribes to SITE_ID from config
    python -m omniview.ingest.subscriber

    # Override site:
    SITE_ID=mumbai-plant python -m omniview.ingest.subscriber

Architecture::

    OmniViewMQTTClient
        ↓ subscribe(omniview/{site_id}/#)
    _on_sensor_message(topic, payload)
        ↓ parse_topic → sensor_type, device_id
        ↓ insert_reading(sensor_type, device_id, …)
    TimescaleDB hypertable

Design notes:
- Malformed payloads are logged and skipped — never crash the subscriber.
- System topics (_status, _alerts) are silently ignored.
- Duplicate readings (QoS 1 retries) are handled by the DB's
  ON CONFLICT DO NOTHING.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from omniview.config import SITE_ID
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import SENSOR_TYPES, build_wildcard, parse_topic
from omniview.ingest.db import insert_reading
from omniview.ingest.migrations import run_migrations
from omniview.ingest.validation import validate_payload

logger = logging.getLogger(__name__)

# ── Metrics (simple counters for observability) ─────────────────────────────

_stats = {
    "received": 0,
    "inserted": 0,
    "duplicates": 0,
    "errors": 0,
    "skipped_system": 0,
    "validation_failures": 0,
    "backfill_insertions": 0,  # OI-29: replayed messages from offline buffer
}
_stats_lock = threading.Lock()


def get_stats() -> dict[str, int]:
    """Return a snapshot of subscriber metrics."""
    with _stats_lock:
        return dict(_stats)


# ── Message handler ─────────────────────────────────────────────────────────


def _on_sensor_message(topic: str, payload: dict[str, Any]) -> None:
    """Process a single MQTT message and write it to TimescaleDB.

    Parameters
    ----------
    topic : str
        MQTT topic string, e.g. ``"omniview/pune-isbm/compressor-01/electrical"``.
    payload : dict
        JSON-decoded message body.
    """
    with _stats_lock:
        _stats["received"] += 1

    # -- Parse topic ----------------------------------------------------------
    try:
        parsed = parse_topic(topic)
    except ValueError:
        # System topics (_status, _alerts) or malformed — skip silently
        with _stats_lock:
            _stats["skipped_system"] += 1
        logger.debug("Skipping non-sensor topic: %s", topic)
        return

    # -- Validate sensor type -------------------------------------------------
    if parsed.sensor_type not in SENSOR_TYPES:
        with _stats_lock:
            _stats["skipped_system"] += 1
        logger.warning(
            "Unknown sensor_type %r on topic %s — skipping",
            parsed.sensor_type,
            topic,
        )
        return

    # -- Extract timestamp ----------------------------------------------------
    try:
        ts_raw = payload.get("timestamp")
        if ts_raw is None:
            # No timestamp in payload — use arrival time (with warning)
            ts = datetime.now(timezone.utc)
            logger.warning(
                "Payload on %s has no 'timestamp' field — using arrival time",
                topic,
            )
        elif isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        elif isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
            logger.warning(
                "Unrecognised timestamp type %s on %s — using arrival time",
                type(ts_raw).__name__,
                topic,
            )
    except (ValueError, TypeError, OSError) as exc:
        ts = datetime.now(timezone.utc)
        logger.warning(
            "Failed to parse timestamp on %s: %s — using arrival time",
            topic,
            exc,
        )

    # -- Extract data payload -------------------------------------------------
    data = payload.get("data", payload)
    schema_version = str(payload.get("schema_version", "1.0"))
    scenario_label = payload.get("scenario_label")  # sibling to data, not inside it
    device_id = payload.get("device_id", parsed.node_id)

    # -- Validate Payload -----------------------------------------------------
    if not validate_payload(parsed.sensor_type, schema_version, payload):
        with _stats_lock:
            _stats["validation_failures"] += 1
        # Skip invalid payloads
        return

    # -- Insert into TimescaleDB ----------------------------------------------
    try:
        inserted = insert_reading(
            sensor_type=parsed.sensor_type,
            device_id=device_id,
            site_id=parsed.site_id,
            time=ts,
            data=data,
            schema_version=schema_version,
            scenario_label=scenario_label,
        )
        with _stats_lock:
            if inserted:
                _stats["inserted"] += 1
                # OI-29: detect backfill replays (timestamp > 60s behind now)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                if age > 60:
                    _stats["backfill_insertions"] += 1
            else:
                _stats["duplicates"] += 1
    except Exception:
        with _stats_lock:
            _stats["errors"] += 1
        logger.exception("Failed to insert reading from %s", topic)


# ── Main loop ───────────────────────────────────────────────────────────────


def run_subscriber(site_id: str | None = None) -> None:
    """Start the MQTT → TimescaleDB subscriber.

    Blocks until interrupted (Ctrl+C / SIGTERM).

    Parameters
    ----------
    site_id : str, optional
        Site to subscribe to.  Defaults to ``config.SITE_ID``.
    """
    site = site_id or SITE_ID
    wildcard = build_wildcard(site)

    # Ensure tables exist before we start receiving data
    run_migrations()

    logger.info("Starting MQTT→TSDB subscriber for site %r", site)
    logger.info("Subscribing to: %s", wildcard)

    stop_event = threading.Event()

    def _signal_handler(signum: int, _frame: Any) -> None:
        logger.info("Received signal %d — shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    with OmniViewMQTTClient() as client:
        client.subscribe(wildcard, _on_sensor_message)
        logger.info("Subscriber running — press Ctrl+C to stop")

        while not stop_event.is_set():
            stop_event.wait(timeout=30)
            # Periodic stats log
            stats = get_stats()
            logger.info(
                "Subscriber stats: received=%d inserted=%d "
                "duplicates=%d errors=%d skipped=%d "
                "validation_failures=%d backfill=%d",
                stats["received"],
                stats["inserted"],
                stats["duplicates"],
                stats["errors"],
                stats["skipped_system"],
                stats["validation_failures"],
                stats["backfill_insertions"],
            )

    logger.info("Subscriber stopped. Final stats: %s", get_stats())


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    run_subscriber()
