"""
Lightweight migration runner — OI-54
======================================

Idempotent database setup: ensures the TimescaleDB extension is installed
and all 7 sensor-family hypertables exist.

Safe to call on every application startup — it only creates what's missing.

Usage::

    # As a module
    from omniview.ingest.migrations import run_migrations
    run_migrations()

    # From the command line
    python -m omniview.ingest.migrations
"""

from __future__ import annotations

import logging
import sys

from omniview.ingest.db import create_hypertables, ensure_timescaledb, get_engine

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run all idempotent database migrations.

    Steps:
    1. Verify TimescaleDB connection is reachable.
    2. Ensure the ``timescaledb`` extension is installed.
    3. Create all 7 sensor-family hypertables (skips existing ones).

    Raises
    ------
    ConnectionError
        If TimescaleDB is unreachable.
    """
    logger.info("Running OI-54 migrations…")

    # 1. Verify connectivity
    engine = get_engine()
    try:
        with engine.connect() as conn:
            from sqlalchemy import text

            result = conn.execute(text("SELECT version()")).scalar()
            logger.info("Connected to: %s", result)
    except Exception as exc:
        raise ConnectionError(
            f"Cannot reach TimescaleDB. Is docker-compose up? Error: {exc}"
        ) from exc

    # 2. Enable TimescaleDB extension
    ensure_timescaledb(engine)

    # 3. Create hypertables
    created = create_hypertables(engine)

    if created:
        logger.info("Migration complete — created tables: %s", ", ".join(created))
    else:
        logger.info("Migration complete — all tables already existed")


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
