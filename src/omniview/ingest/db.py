"""
TimescaleDB connection helpers — OI-54
=======================================

Provides:
- ``get_engine()``          — SQLAlchemy engine (singleton) from ``omniview.config``
- ``ensure_timescaledb()``  — idempotent ``CREATE EXTENSION``
- ``create_hypertables()``  — idempotent DDL for all 7 sensor-family hypertables
- ``insert_reading()``      — single-row idempotent upsert
- ``insert_readings_batch()`` — bulk idempotent upsert
- ``query_latest()``        — fetch most-recent N readings for a device

Design notes (PRD §5.4 + System Workflow §3.3):
- One table per sensor family (electrical, vibration, thermal, pressure,
  gas, stroke, ambient) — keeps queries fast and matches DevB's 7-schema
  contract.
- ``device_id + time`` unique constraint enables ``ON CONFLICT DO NOTHING``
  for effectively-exactly-once semantics over QoS 1 at-least-once delivery.
- JSONB ``data`` column allows schema flexibility while DevB's sensor
  schemas are still evolving (OI-23/5/6/7).
- Late / backfilled readings insert at their correct historical position —
  TimescaleDB handles out-of-order writes natively.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from omniview.config import TSDB_CHUNK_INTERVAL, TSDB_DSN
from omniview.edge.topics import SENSOR_TYPES

logger = logging.getLogger(__name__)

# ── Singleton engine ────────────────────────────────────────────────────────

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a shared SQLAlchemy engine connected to TimescaleDB.

    Uses a connection pool (``pool_size=5``, ``max_overflow=10``) to
    handle concurrent ingest and query workloads without creating
    excessive connections.

    Returns
    -------
    Engine
        A SQLAlchemy :class:`~sqlalchemy.engine.Engine` instance.
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = create_engine(
            TSDB_DSN,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # verify connections before use
        )
        logger.info("Created TSDB engine → %s", TSDB_DSN.split("@")[-1])
    return _engine


def reset_engine() -> None:
    """Dispose of the current engine (for testing or shutdown).

    After calling this, the next ``get_engine()`` call will create a
    fresh engine with a new connection pool.
    """
    global _engine  # noqa: PLW0603
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("TSDB engine disposed")


# ── Table naming ────────────────────────────────────────────────────────────

_TABLE_PREFIX = "readings_"


def _table_name(sensor_type: str) -> str:
    """Return the hypertable name for a sensor family.

    Examples
    --------
    >>> _table_name("electrical")
    'readings_electrical'
    """
    return f"{_TABLE_PREFIX}{sensor_type}"


# ── DDL — idempotent schema setup ──────────────────────────────────────────


def ensure_timescaledb(engine: Engine | None = None) -> None:
    """Ensure the TimescaleDB extension is installed.

    Idempotent — safe to call on every startup.
    """
    eng = engine or get_engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    logger.info("TimescaleDB extension ensured")


def create_hypertables(engine: Engine | None = None) -> list[str]:
    """Create all 7 sensor-family hypertables (idempotent).

    Each table has:
    - ``time TIMESTAMPTZ NOT NULL`` — partition column
    - ``device_id TEXT NOT NULL`` — node identifier
    - ``site_id TEXT NOT NULL`` — site identifier
    - ``sensor_type TEXT NOT NULL`` — redundant with table name, useful
      for cross-table queries and validation
    - ``schema_version TEXT NOT NULL DEFAULT '1.0'`` — contract version
    - ``data JSONB NOT NULL`` — sensor-family-specific payload
    - Unique constraint on ``(device_id, time)`` for idempotent upserts
    - GIN index on ``data`` for JSONB field queries

    Parameters
    ----------
    engine : Engine, optional
        Override the default engine (useful for testing).

    Returns
    -------
    list[str]
        Names of tables that were created (empty strings for those that
        already existed).
    """
    eng = engine or get_engine()
    created: list[str] = []

    for sensor_type in sorted(SENSOR_TYPES):
        tbl = _table_name(sensor_type)

        with eng.begin() as conn:
            # -- Create table (IF NOT EXISTS) ----------------------------------
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {tbl} (
                    time            TIMESTAMPTZ     NOT NULL,
                    device_id       TEXT            NOT NULL,
                    site_id         TEXT            NOT NULL,
                    sensor_type     TEXT            NOT NULL
                                                   DEFAULT '{sensor_type}',
                    schema_version  TEXT            NOT NULL DEFAULT '1.0',
                    data            JSONB           NOT NULL,
                    UNIQUE (device_id, time)
                )
            """))

            # -- Convert to hypertable (idempotent) ----------------------------
            # TimescaleDB raises if table is already a hypertable, so we
            # guard with a check against timescaledb_information.hypertables.
            is_hypertable = conn.execute(text("""
                SELECT 1
                  FROM timescaledb_information.hypertables
                 WHERE hypertable_name = :tbl
                 LIMIT 1
            """), {"tbl": tbl}).scalar()

            if not is_hypertable:
                conn.execute(text(f"""
                    SELECT create_hypertable(
                        '{tbl}', 'time',
                        chunk_time_interval => INTERVAL '{TSDB_CHUNK_INTERVAL}',
                        if_not_exists       => TRUE
                    )
                """))
                logger.info("Created hypertable: %s (chunk=%s)", tbl, TSDB_CHUNK_INTERVAL)
                created.append(tbl)
            else:
                logger.debug("Hypertable already exists: %s", tbl)

            # -- GIN index on JSONB data column --------------------------------
            idx_name = f"idx_{tbl}_data"
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS {idx_name}
                    ON {tbl} USING GIN (data)
            """))

    logger.info(
        "Hypertable setup complete: %d created, %d already existed",
        len(created),
        len(SENSOR_TYPES) - len(created),
    )
    return created


# ── DML — insert helpers ───────────────────────────────────────────────────


def insert_reading(
    sensor_type: str,
    device_id: str,
    site_id: str,
    time: datetime,
    data: dict[str, Any],
    schema_version: str = "1.0",
    engine: Engine | None = None,
) -> bool:
    """Insert a single sensor reading (idempotent).

    Uses ``INSERT ... ON CONFLICT (device_id, time) DO NOTHING`` to
    silently skip duplicates — matching QoS 1 at-least-once delivery
    semantics.

    Parameters
    ----------
    sensor_type : str
        One of the 7 sensor families (e.g. ``"electrical"``).
    device_id : str
        Node identifier (e.g. ``"compressor-01"``).
    site_id : str
        Site identifier (e.g. ``"pune-isbm"``).
    time : datetime
        Reading timestamp (should be timezone-aware).
    data : dict
        Sensor payload as a dictionary (stored as JSONB).
    schema_version : str
        Schema version tag (default ``"1.0"``).
    engine : Engine, optional
        Override the default engine.

    Returns
    -------
    bool
        ``True`` if the row was inserted, ``False`` if it was a
        duplicate and was skipped.

    Raises
    ------
    ValueError
        If *sensor_type* is not in :data:`~omniview.edge.topics.SENSOR_TYPES`.
    """
    if sensor_type not in SENSOR_TYPES:
        raise ValueError(
            f"Unknown sensor_type {sensor_type!r}. "
            f"Must be one of: {sorted(SENSOR_TYPES)}"
        )

    eng = engine or get_engine()
    tbl = _table_name(sensor_type)

    import json

    with eng.begin() as conn:
        result = conn.execute(
            text(f"""
                INSERT INTO {tbl} (time, device_id, site_id, sensor_type,
                                   schema_version, data)
                VALUES (:time, :device_id, :site_id, :sensor_type,
                        :schema_version, CAST(:data AS jsonb))
                ON CONFLICT (device_id, time) DO NOTHING
            """),
            {
                "time": time,
                "device_id": device_id,
                "site_id": site_id,
                "sensor_type": sensor_type,
                "schema_version": schema_version,
                "data": json.dumps(data, default=str),
            },
        )
        inserted = result.rowcount > 0

    if inserted:
        logger.debug(
            "Inserted reading: %s/%s @ %s", tbl, device_id, time.isoformat()
        )
    else:
        logger.debug(
            "Skipped duplicate: %s/%s @ %s", tbl, device_id, time.isoformat()
        )
    return inserted


def insert_readings_batch(
    sensor_type: str,
    readings: list[dict[str, Any]],
    engine: Engine | None = None,
) -> int:
    """Bulk-insert multiple readings for a sensor family (idempotent).

    Each item in *readings* must contain keys:
    ``device_id``, ``site_id``, ``time``, ``data``, and optionally
    ``schema_version`` (defaults to ``"1.0"``).

    Parameters
    ----------
    sensor_type : str
        One of the 7 sensor families.
    readings : list[dict]
        List of reading dicts.
    engine : Engine, optional
        Override the default engine.

    Returns
    -------
    int
        Number of rows actually inserted (duplicates excluded).
    """
    if not readings:
        return 0

    if sensor_type not in SENSOR_TYPES:
        raise ValueError(
            f"Unknown sensor_type {sensor_type!r}. "
            f"Must be one of: {sorted(SENSOR_TYPES)}"
        )

    import json

    eng = engine or get_engine()
    tbl = _table_name(sensor_type)
    total_inserted = 0

    with eng.begin() as conn:
        for r in readings:
            result = conn.execute(
                text(f"""
                    INSERT INTO {tbl} (time, device_id, site_id, sensor_type,
                                       schema_version, data)
                    VALUES (:time, :device_id, :site_id, :sensor_type,
                            :schema_version, CAST(:data AS jsonb))
                    ON CONFLICT (device_id, time) DO NOTHING
                """),
                {
                    "time": r["time"],
                    "device_id": r["device_id"],
                    "site_id": r["site_id"],
                    "sensor_type": sensor_type,
                    "schema_version": r.get("schema_version", "1.0"),
                    "data": json.dumps(r["data"], default=str),
                },
            )
            total_inserted += result.rowcount

    logger.info(
        "Batch insert into %s: %d/%d rows inserted (rest were duplicates)",
        tbl,
        total_inserted,
        len(readings),
    )
    return total_inserted


# ── Queries ─────────────────────────────────────────────────────────────────


def query_latest(
    sensor_type: str,
    device_id: str,
    limit: int = 10,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    """Fetch the most recent readings for a device and sensor type.

    Parameters
    ----------
    sensor_type : str
        One of the 7 sensor families.
    device_id : str
        Node identifier.
    limit : int
        Maximum number of rows to return (default 10).
    engine : Engine, optional
        Override the default engine.

    Returns
    -------
    list[dict]
        Each dict contains ``time``, ``device_id``, ``site_id``,
        ``sensor_type``, ``schema_version``, and ``data``.
    """
    if sensor_type not in SENSOR_TYPES:
        raise ValueError(
            f"Unknown sensor_type {sensor_type!r}. "
            f"Must be one of: {sorted(SENSOR_TYPES)}"
        )

    eng = engine or get_engine()
    tbl = _table_name(sensor_type)

    with eng.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT time, device_id, site_id, sensor_type,
                       schema_version, data
                  FROM {tbl}
                 WHERE device_id = :device_id
                 ORDER BY time DESC
                 LIMIT :limit
            """),
            {"device_id": device_id, "limit": limit},
        ).mappings().all()

    return [dict(row) for row in rows]
