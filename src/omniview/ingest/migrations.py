"""
Lightweight migration runner — OI-54 + V3 Label Columns
=========================================================

Idempotent database setup: ensures the TimescaleDB extension is installed,
all 7 sensor-family hypertables exist, and a native ``scenario_label``
column is present on each table for rule-engine labeling.

Safe to call on every application startup — it only creates what's missing.

Usage::

    # As a module
    from omniview.ingest.migrations import run_migrations
    run_migrations()

    # From the command line
    python -m omniview.ingest.migrations

Design note (DevB architectural decision):
    The ``scenario_label`` column is a plain TEXT column — **not** a
    generated column.  Labels are written by the ingestion pipeline as
    a sibling to the JSONB ``data`` payload.  Raw telemetry in ``data``
    is never mutated with inference results.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine

from omniview.edge.topics import SENSOR_TYPES
from omniview.ingest.db import create_hypertables, ensure_timescaledb, get_engine

logger = logging.getLogger(__name__)


# ── V3 Native Label Column ─────────────────────────────────────────────────
#
# Tables that currently produce alert scenarios (from seed.py injectors
# and the upcoming Lead rule engine).  We add sparse indexes only on
# these tables — the other families get the column but no index until
# consumers appear.
#
# See: implementation_plan.md (V3) for full rationale.

_LABEL_INDEXED_TABLES: frozenset[str] = frozenset(
    {
        "readings_electrical",  # md_nearmiss, lazy_idle
        "readings_pressure",    # leak_proxy
        "readings_thermal",     # lazy_idle
    }
)


def _run_v3_label_column(engine: Engine) -> int:
    """Add a native ``scenario_label TEXT`` column to all hypertables.

    This is a plain column — NOT a generated column.  Labels are
    written by the ingestion pipeline as a sibling to the JSONB
    ``data`` payload, per DevB's architectural decision.

    Includes a guard to drop any pre-existing GENERATED version of
    the column (from V2) before re-adding as a plain column.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine connected to TimescaleDB.

    Returns
    -------
    int
        Number of DDL statements executed (includes no-ops).
    """
    tables = [f"readings_{st}" for st in sorted(SENSOR_TYPES)]
    executed = 0

    for tbl in tables:
        with engine.begin() as conn:
            # Guard: if a GENERATED scenario_label exists from V2,
            # drop it first (generated columns can't be converted)
            conn.execute(text(f"""
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{tbl}'
                      AND column_name = 'scenario_label'
                      AND is_generated = 'ALWAYS'
                  ) THEN
                    ALTER TABLE {tbl} DROP COLUMN scenario_label;
                  END IF;
                END $$
            """))

            conn.execute(text(f"""
                ALTER TABLE {tbl}
                  ADD COLUMN IF NOT EXISTS scenario_label TEXT
            """))
            executed += 1
            logger.debug("V3 label column: %s", tbl)

    # Sparse indexes on alert-producing tables
    for tbl in sorted(_LABEL_INDEXED_TABLES):
        with engine.begin() as conn:
            idx_name = f"idx_{tbl.replace('readings_', '')}_scenario"
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS {idx_name}
                  ON {tbl} (scenario_label)
                  WHERE scenario_label IS NOT NULL
            """))
            executed += 1
            logger.debug("V3 label index: %s", idx_name)

    return executed


def run_migrations() -> None:
    """Run all idempotent database migrations.

    Steps:
    1. Verify TimescaleDB connection is reachable.
    2. Ensure the ``timescaledb`` extension is installed.
    3. Create all 7 sensor-family hypertables (skips existing ones).
    4. V3: Add native ``scenario_label`` column + sparse indexes.

    Raises
    ------
    ConnectionError
        If TimescaleDB is unreachable.
    """
    logger.info("Running OI-54 + V3 migrations…")

    # 1. Verify connectivity
    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()")).scalar()
            logger.info("Connected to: %s", result)
    except Exception as exc:
        raise ConnectionError(
            f"Cannot reach TimescaleDB. Is docker-compose up? Error: {exc}"
        ) from exc

    # 2. Enable TimescaleDB extension
    ensure_timescaledb(engine)

    # 3. Create hypertables (V1 — OI-54)
    created = create_hypertables(engine)

    if created:
        logger.info("V1 migration — created tables: %s", ", ".join(created))
    else:
        logger.info("V1 migration — all tables already existed")

    # 4. Add native label column + indexes (V3 — DevB architectural decision)
    v3_count = _run_v3_label_column(engine)
    logger.info(
        "V3 migration — %d label-column/index statements executed "
        "across %d tables",
        v3_count,
        len([f"readings_{st}" for st in SENSOR_TYPES]),
    )


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    try:
        run_migrations()
    except ConnectionError as exc:
        logger.error(str(exc))
        sys.exit(1)
