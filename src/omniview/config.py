"""
Centralised configuration loader.

Reads environment variables from ``.env`` (via python-dotenv) and exposes them
as typed module-level constants.  Every service in the stack imports from here
rather than calling ``os.getenv`` directly — single source of truth.

Usage::

    from omniview.config import MQTT_BROKER_HOST, TSDB_DSN
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Walk up from this file to find .env at repo root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)

# ── MQTT (Mosquitto) ────────────────────────────────────────────────────────
MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))

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

# ── Polling intervals (seconds) ────────────────────────────────────────────
POLL_ELECTRICAL_INTERVAL: int = int(os.getenv("POLL_ELECTRICAL_INTERVAL", "15"))
POLL_PHYSICAL_INTERVAL: int = int(os.getenv("POLL_PHYSICAL_INTERVAL", "60"))

# ── Site parameters ─────────────────────────────────────────────────────────
CONTRACTED_DEMAND_KVA: float = float(os.getenv("CONTRACTED_DEMAND_KVA", "500"))
