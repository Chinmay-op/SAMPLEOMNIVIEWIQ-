"""
omniview.ingest — Cloud Ingestion & Storage Layer (Layer 3, part 1)
====================================================================

Handles MQTT → TimescaleDB writes:

* **db** — Connection pool, hypertable creation, idempotent inserts  (OI-54)
* **migrations** — Idempotent startup migration runner              (OI-54)
* **subscriber** — MQTT→TSDB bridge process                         (OI-54)
* **tsdb_inserter** — High-level insertion facade with metrics      (OI-15)

Payload validation:
* **validation** — JSON schema validation against DevB contracts    (OI-14)

Backfill coordination:
* **backfill_coordinator** — Cloud-side backfill + gap verification (OI-29)

Seeding:
* **seed** — Day-1 hybrid dataset loader for demos/testing            (OI-55)
"""

from omniview.ingest.backfill_coordinator import BackfillCoordinator
from omniview.ingest.db import (
    BackfillResult,
    backfill_insert,
    create_hypertables,
    get_engine,
    insert_reading,
    insert_readings_batch,
    query_by_time_range,
    query_latest,
)
from omniview.ingest.migrations import run_migrations
from omniview.ingest.seed import SeedResult, seed_all
from omniview.ingest.tsdb_inserter import TSDBInserter
from omniview.ingest.validation import validate_payload

__all__ = [
    "BackfillCoordinator",
    "BackfillResult",
    "SeedResult",
    "TSDBInserter",
    "backfill_insert",
    "create_hypertables",
    "get_engine",
    "insert_reading",
    "insert_readings_batch",
    "query_by_time_range",
    "query_latest",
    "run_migrations",
    "seed_all",
    "validate_payload",
]
