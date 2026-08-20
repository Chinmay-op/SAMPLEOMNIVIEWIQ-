"""
Backfill Coordinator — OI-29
==============================

Coordinates the cloud-side receipt of replayed telemetry with the
idempotent TSDB insertion layer (OI-15).

Provides:
- ``process_backfill_batch()`` — groups readings by sensor family and
  routes them through ``backfill_insert()`` for efficient chunked writes
- ``verify_no_gaps()`` — queries the TSDB after backfill to confirm
  the outage window has been filled (no gaps)
- ``get_backfill_summary()`` — aggregated per-family results

Design notes:
- The subscriber (OI-54) already handles individual message inserts via
  ``insert_reading()``.  This coordinator adds the *bulk* path used
  when the edge gateway replays buffered messages.
- All inserts use ``ON CONFLICT (device_id, time) DO NOTHING`` — safe
  to call multiple times (idempotent).
- Gap verification uses ``query_by_time_range()`` and checks that the
  returned row count meets a minimum expected density.

Usage::

    from omniview.ingest.backfill_coordinator import BackfillCoordinator

    coordinator = BackfillCoordinator()
    results = coordinator.process_backfill_batch(readings_by_sensor)
    gap_check = coordinator.verify_no_gaps(
        sensor_type="electrical",
        device_id="compressor-01",
        start=outage_start,
        end=outage_end,
        expected_interval_seconds=15,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from omniview.ingest.db import (
    BackfillResult,
    backfill_insert,
    query_by_time_range,
)

logger = logging.getLogger(__name__)


class BackfillCoordinator:
    """Coordinates backfill inserts with gap verification.

    Wraps the low-level ``backfill_insert()`` and ``query_by_time_range()``
    functions into a higher-level workflow for the buffer replay scenario.

    Parameters
    ----------
    engine : optional
        SQLAlchemy Engine override (passed through to ``db.py``).
    """

    def __init__(self, engine: Any = None) -> None:
        self._engine = engine
        self._last_results: dict[str, BackfillResult] = {}

    @property
    def last_results(self) -> dict[str, BackfillResult]:
        """Per-sensor-type results from the most recent backfill batch."""
        return dict(self._last_results)

    def process_backfill_batch(
        self,
        readings_by_sensor: dict[str, list[dict[str, Any]]],
    ) -> dict[str, BackfillResult]:
        """Insert backfill readings grouped by sensor family.

        Each family's readings are routed through ``backfill_insert()``
        for efficient chunked multi-value INSERT with ``ON CONFLICT
        DO NOTHING``.

        Parameters
        ----------
        readings_by_sensor : dict[str, list[dict]]
            Keys are sensor type strings (e.g. ``"electrical"``), values
            are lists of reading dicts with keys: ``device_id``,
            ``site_id``, ``time``, ``data``, and optionally
            ``schema_version``.

        Returns
        -------
        dict[str, BackfillResult]
            Per-sensor-type ``BackfillResult`` objects.
        """
        results: dict[str, BackfillResult] = {}

        for sensor_type, readings in readings_by_sensor.items():
            if not readings:
                continue

            logger.info(
                "Backfill coordinator: processing %d %s readings",
                len(readings),
                sensor_type,
            )

            try:
                result = backfill_insert(
                    sensor_type=sensor_type,
                    readings=readings,
                    engine=self._engine,
                )
                results[sensor_type] = result

                logger.info(
                    "Backfill coordinator: %s → %d inserted, %d duplicates",
                    sensor_type,
                    result.inserted,
                    result.duplicates,
                )
            except ValueError:
                logger.warning(
                    "Backfill coordinator: skipping unknown sensor_type %r",
                    sensor_type,
                )
            except Exception:
                logger.exception(
                    "Backfill coordinator: failed to backfill %s",
                    sensor_type,
                )

        self._last_results = results
        return results

    def verify_no_gaps(
        self,
        sensor_type: str,
        device_id: str,
        start: datetime,
        end: datetime,
        expected_interval_seconds: int = 15,
        tolerance: float = 0.8,
    ) -> dict[str, Any]:
        """Verify that the TSDB has no gaps in a time window.

        After a backfill replay, this confirms that the outage window
        shows data, not a hole.

        Parameters
        ----------
        sensor_type : str
            Sensor family to check.
        device_id : str
            Device identifier.
        start : datetime
            Start of the window to verify.
        end : datetime
            End of the window to verify.
        expected_interval_seconds : int
            Expected polling interval (e.g. 15s for electrical).
        tolerance : float
            Fraction of expected readings that must be present
            (default 0.8 = 80%).  Allows for minor gaps without
            flagging a false alarm.

        Returns
        -------
        dict[str, Any]
            ``{"has_gaps": bool, "expected": int, "actual": int,
            "coverage": float, "threshold": float}``
        """
        rows = query_by_time_range(
            sensor_type=sensor_type,
            device_id=device_id,
            start=start,
            end=end,
            engine=self._engine,
        )

        window_seconds = (end - start).total_seconds()
        expected_count = max(1, int(window_seconds / expected_interval_seconds))
        actual_count = len(rows)
        coverage = actual_count / expected_count if expected_count > 0 else 0.0
        has_gaps = coverage < tolerance

        result = {
            "has_gaps": has_gaps,
            "expected": expected_count,
            "actual": actual_count,
            "coverage": round(coverage, 4),
            "threshold": tolerance,
        }

        if has_gaps:
            logger.warning(
                "Gap detected for %s/%s in [%s, %s]: "
                "expected ~%d readings, found %d (%.1f%% coverage, "
                "threshold=%.0f%%)",
                sensor_type,
                device_id,
                start.isoformat(),
                end.isoformat(),
                expected_count,
                actual_count,
                coverage * 100,
                tolerance * 100,
            )
        else:
            logger.info(
                "No gaps for %s/%s in [%s, %s]: "
                "%d/%d readings (%.1f%% coverage ✓)",
                sensor_type,
                device_id,
                start.isoformat(),
                end.isoformat(),
                actual_count,
                expected_count,
                coverage * 100,
            )

        return result

    def get_backfill_summary(self) -> dict[str, Any]:
        """Return an aggregated summary of the last backfill operation.

        Returns
        -------
        dict[str, Any]
            ``{"total_inserted": int, "total_duplicates": int,
            "families_processed": int, "all_clean": bool,
            "per_family": dict}``
        """
        total_inserted = sum(r.inserted for r in self._last_results.values())
        total_duplicates = sum(
            r.duplicates for r in self._last_results.values()
        )
        all_clean = all(r.is_clean for r in self._last_results.values())

        return {
            "total_inserted": total_inserted,
            "total_duplicates": total_duplicates,
            "families_processed": len(self._last_results),
            "all_clean": all_clean,
            "per_family": {
                st: {
                    "total": r.total,
                    "inserted": r.inserted,
                    "duplicates": r.duplicates,
                    "is_clean": r.is_clean,
                }
                for st, r in self._last_results.items()
            },
        }
