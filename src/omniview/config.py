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

# ── Calibration Offsets (OI-40) ──────────────────────────────────────────────
# Offsets applied to raw modbus/simulated readings before JSON validation
CALIBRATION_CURRENT_OFFSET_A: float = float(os.getenv("CALIBRATION_CURRENT_OFFSET_A", "0.0"))
CALIBRATION_VOLTAGE_OFFSET_V: float = float(os.getenv("CALIBRATION_VOLTAGE_OFFSET_V", "0.0"))

# ── Offline buffer (OI-28) ──────────────────────────────────────────────
BUFFER_DB_PATH: str = os.getenv(
    "BUFFER_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "offline_buffer.db"),
)
BUFFER_MAX_AGE_DAYS: int = int(os.getenv("BUFFER_MAX_AGE_DAYS", "7"))
BUFFER_MAX_SIZE_MB: int = int(os.getenv("BUFFER_MAX_SIZE_MB", "100"))
BUFFER_DRAIN_BATCH_SIZE: int = int(os.getenv("BUFFER_DRAIN_BATCH_SIZE", "50"))

# ── NTP drift guard (OI-53) ─────────────────────────────────────────────
NTP_SERVER: str = os.getenv("NTP_SERVER", "pool.ntp.org")
NTP_DRIFT_THRESHOLD_S: float = float(os.getenv("NTP_DRIFT_THRESHOLD_S", "5.0"))
NTP_CHECK_INTERVAL_S: int = int(os.getenv("NTP_CHECK_INTERVAL_S", "60"))
NTP_MAX_RETRIES: int = int(os.getenv("NTP_MAX_RETRIES", "3"))
NTP_TIMEOUT_S: float = float(os.getenv("NTP_TIMEOUT_S", "5.0"))

# ── Dashboard (OI-68) ───────────────────────────────────────────────────
DASHBOARD_REFRESH_S: int = int(os.getenv("DASHBOARD_REFRESH_S", "30"))
MD_PENALTY_RATE_PER_KVA: float = float(
    os.getenv("MD_PENALTY_RATE_PER_KVA", "350.0")
)
# Dashboard "% idle" gauge threshold — distinct from Lead's OI-57
# lazy-idle rule threshold (IDLE_CURRENT_THRESHOLD_A = 0.65 A in
# rules/lazy_idle.py).  The gauge measures "motor electrically idle
# for the Owner overview"; the rule measures "lazy-idle onset for
# Layer 3 event detection".  Do NOT unify them.
DASHBOARD_IDLE_CURRENT_THRESHOLD_A: float = float(
    os.getenv("DASHBOARD_IDLE_CURRENT_THRESHOLD_A", "5.0")
)
# Legacy alias — kept for any code that still imports it.
# New code should use DASHBOARD_IDLE_CURRENT_THRESHOLD_A for the gauge
# or the rule's own constant for lazy-idle detection.
IDLE_CURRENT_THRESHOLD_A: float = float(
    os.getenv("IDLE_CURRENT_THRESHOLD_A", "10.0")
)
IDLE_TEMP_THRESHOLD_C: float = float(
    os.getenv("IDLE_TEMP_THRESHOLD_C", "200.0")
)


# ── Alert Routing (OI-71) ───────────────────────────────────────────
ALERT_ROUTING_ENABLED: bool = os.getenv("ALERT_ROUTING_ENABLED", "true").lower() in (
    "true", "1", "yes",
)
ALERT_WEBHOOK_URL: str = os.getenv(
    "ALERT_WEBHOOK_URL", "http://localhost:9999/alerts"
)
# JSON map of role → email address (override via .env)
_EMAIL_MAP_RAW: str = os.getenv("ALERT_EMAIL_RECIPIENT_MAP", "")
ALERT_EMAIL_RECIPIENT_MAP: dict[str, str] = (
    __import__("json").loads(_EMAIL_MAP_RAW) if _EMAIL_MAP_RAW else {}
)
