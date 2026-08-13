"""
Centralised configuration loader.

Reads environment variables from ``.env`` (via python-dotenv) and exposes them
as typed module-level constants.  Every service in the stack imports from here
rather than calling ``os.getenv`` directly — single source of truth.

Usage::

    from omniview.config import MQTT_BROKER_HOST, TSDB_DSN, SITE_ID
"""

import os
import socket
from pathlib import Path

from dotenv import load_dotenv

# Walk up from this file to find .env at repo root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)

# ── MQTT (Mosquitto) ────────────────────────────────────────────────────────
MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_CLIENT_ID: str = os.getenv(
    "MQTT_CLIENT_ID", f"omniview-edge-{socket.gethostname()}"
)
MQTT_QOS: int = int(os.getenv("MQTT_QOS", "1"))  # 0=fire-forget, 1=at-least-once
MQTT_KEEPALIVE: int = int(os.getenv("MQTT_KEEPALIVE", "60"))  # seconds

# ── TimescaleDB ─────────────────────────────────────────────────────────────
TSDB_HOST: str = os.getenv("TSDB_HOST", "localhost")
TSDB_PORT: int = int(os.getenv("TSDB_PORT", "5432"))
TSDB_DB: str = os.getenv("TSDB_DB", "omniview")
TSDB_USER: str = os.getenv("TSDB_USER", "omniview")
TSDB_PASSWORD: str = os.getenv("TSDB_PASSWORD", "changeme")

TSDB_DSN: str = (
    f"postgresql://{TSDB_USER}:{TSDB_PASSWORD}"
    f"@{TSDB_HOST}:{TSDB_PORT}/{TSDB_DB}"
)
TSDB_CHUNK_INTERVAL: str = os.getenv("TSDB_CHUNK_INTERVAL", "7 days")

# ── Polling intervals (seconds) ────────────────────────────────────────────
POLL_ELECTRICAL_INTERVAL: int = int(os.getenv("POLL_ELECTRICAL_INTERVAL", "15"))
POLL_PHYSICAL_INTERVAL: int = int(os.getenv("POLL_PHYSICAL_INTERVAL", "60"))

# ── Site parameters ─────────────────────────────────────────────────────────
SITE_ID: str = os.getenv("SITE_ID", "pune-isbm")
CONTRACTED_DEMAND_KVA: float = float(os.getenv("CONTRACTED_DEMAND_KVA", "500"))

# ── Offline buffer (OI-28) ──────────────────────────────────────────────
BUFFER_DB_PATH: str = os.getenv(
    "BUFFER_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "offline_buffer.db"),
)
BUFFER_MAX_AGE_DAYS: int = int(os.getenv("BUFFER_MAX_AGE_DAYS", "7"))
BUFFER_MAX_SIZE_MB: int = int(os.getenv("BUFFER_MAX_SIZE_MB", "100"))
BUFFER_DRAIN_BATCH_SIZE: int = int(os.getenv("BUFFER_DRAIN_BATCH_SIZE", "50"))
