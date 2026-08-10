"""
omniview.ingest — Cloud Ingestion & Storage Layer (Layer 3, part 1)
====================================================================

Handles MQTT → TimescaleDB writes:

* **db** — Connection pool, hypertable creation, idempotent inserts  (OI-54)
* **migrations** — Idempotent startup migration runner              (OI-54)
* **subscriber** — MQTT→TSDB bridge process                         (OI-54)

Future modules:
* Payload schema validation + version check  (OI-55)
* Day-1 seed script                          (OI-55)
"""

from omniview.ingest.db import (
    create_hypertables,
    get_engine,
    insert_reading,
    insert_readings_batch,
    query_latest,
)
from omniview.ingest.migrations import run_migrations

__all__ = [
    "create_hypertables",
    "get_engine",
    "insert_reading",
    "insert_readings_batch",
    "query_latest",
    "run_migrations",
]
