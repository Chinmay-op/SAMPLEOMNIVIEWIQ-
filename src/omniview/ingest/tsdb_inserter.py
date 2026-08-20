"""
TSDBInserter — High-Level Insertion Facade — OI-15
====================================================

Wraps the low-level ``db.py`` functions into a single class with
per-sensor-family metrics tracking.

Usage::

    inserter = TSDBInserter()

    # Single insert
    inserted = inserter.insert(
        sensor_type="electrical",
        device_id="compressor-01",
        site_id="pune-isbm",
        time=datetime.now(timezone.utc),
        data={"kva": 147.6, "kw": 140.2, ...},
    )

    # Backfill (e.g. offline buffer drain)
    result = inserter.backfill(
        sensor_type="electrical",
        readings=[...],
    )
    print(result.inserted, result.duplicates)

    # Query
    rows = inserter.query_range(
        sensor_type="electrical",
        device_id="compressor-01",
        start=datetime(2026, 8, 10, tzinfo=timezone.utc),
        end=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )

    # Metrics
    print(inserter.metrics)
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from omniview.edge.topics import SENSOR_TYPES
from omniview.ingest.db import (
    BackfillResult,
    backfill_insert,
    insert_reading,
    query_by_time_range,
    query_latest,
)

logger = logging.getLogger(__name__)


class TSDBInserter:
    """High-level facade for TimescaleDB sensor data operations.

    Tracks per-sensor-family insertion metrics (inserts, duplicates,
    errors) across the lifetime of the instance.  Thread-safe.

    Parameters
    ----------
    engine : optional
        SQLAlchemy Engine override (passed through to ``db.py``
        functions).  Defaults to the module-level singleton.
    """

    def __init__(self, engine=None) -> None:
        self._engine = engine
        self._lock = threading.Lock()
        # Per-family counters
        self._metrics: dict[str, dict[str, int]] = {
            st: {"inserts": 0, "duplicates": 0, "errors": 0}
            for st in sorted(SENSOR_TYPES)
        }

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def metrics(self) -> dict[str, dict[str, int]]:
        """Return a snapshot of per-family insertion metrics."""
        with self._lock:
            return {st: dict(counts) for st, counts in self._metrics.items()}

    @property
    def total_inserts(self) -> int:
        """Total inserts across all families."""
        with self._lock:
            return sum(c["inserts"] for c in self._metrics.values())

    @property
    def total_duplicates(self) -> int:
        """Total duplicates across all families."""
        with self._lock:
            return sum(c["duplicates"] for c in self._metrics.values())

    @property
    def total_errors(self) -> int:
        """Total errors across all families."""
        with self._lock:
            return sum(c["errors"] for c in self._metrics.values())

    # ── Single insert ───────────────────────────────────────────────────

    def insert(
        self,
        sensor_type: str,
        device_id: str,
        site_id: str,
        time: datetime,
        data: dict[str, Any],
        schema_version: str = "1.0",
    ) -> bool:
        """Insert a single reading and update metrics.

        Parameters match :func:`~omniview.ingest.db.insert_reading`.

        Returns
        -------
        bool
            ``True`` if inserted, ``False`` if duplicate.
        """
        if sensor_type not in SENSOR_TYPES:
            raise ValueError(
                f"Unknown sensor_type {sensor_type!r}. "
                f"Must be one of: {sorted(SENSOR_TYPES)}"
            )

        try:
            inserted = insert_reading(
                sensor_type=sensor_type,
                device_id=device_id,
                site_id=site_id,
                time=time,
                data=data,
                schema_version=schema_version,
                engine=self._engine,
            )
            with self._lock:
                if inserted:
                    self._metrics[sensor_type]["inserts"] += 1
                else:
                    self._metrics[sensor_type]["duplicates"] += 1
            return inserted
        except ValueError:
            raise  # re-raise validation errors
        except Exception:
            with self._lock:
                self._metrics[sensor_type]["errors"] += 1
            logger.exception(
                "TSDBInserter: failed to insert %s/%s", sensor_type, device_id
            )
            raise

    # ── Backfill ────────────────────────────────────────────────────────

    def backfill(
        self,
        sensor_type: str,
        readings: list[dict[str, Any]],
    ) -> BackfillResult:
        """Run a backfill insert and update metrics.

        Parameters match :func:`~omniview.ingest.db.backfill_insert`.

        Returns
        -------
        BackfillResult
            Counts of total, inserted, and duplicate readings.
        """
        if sensor_type not in SENSOR_TYPES:
            raise ValueError(
                f"Unknown sensor_type {sensor_type!r}. "
                f"Must be one of: {sorted(SENSOR_TYPES)}"
            )

        result = backfill_insert(
            sensor_type=sensor_type,
            readings=readings,
            engine=self._engine,
        )

        with self._lock:
            self._metrics[sensor_type]["inserts"] += result.inserted
            self._metrics[sensor_type]["duplicates"] += result.duplicates

        return result

    # ── Queries ─────────────────────────────────────────────────────────

    def query_range(
        self,
        sensor_type: str,
        device_id: str,
        start: datetime,
        end: datetime,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Query readings by device_id + time range.

        Parameters match :func:`~omniview.ingest.db.query_by_time_range`.
        """
        return query_by_time_range(
            sensor_type=sensor_type,
            device_id=device_id,
            start=start,
            end=end,
            limit=limit,
            engine=self._engine,
        )

    def query_latest(
        self,
        sensor_type: str,
        device_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Query most recent readings.

        Parameters match :func:`~omniview.ingest.db.query_latest`.
        """
        return query_latest(
            sensor_type=sensor_type,
            device_id=device_id,
            limit=limit,
            engine=self._engine,
        )
