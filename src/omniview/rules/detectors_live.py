"""
Detectors Live — Poll-Cycle Runner (``detectors_live``)
========================================================

**The missing glue layer.**  This module connects TimescaleDB (storage)
to the rule engine (intelligence) and feeds results to the alert
pipeline (delivery).

Architecture::

    ┌──────────┐      ┌──────────┐      ┌──────────────┐      ┌──────────┐
    │ TSDB     │ ──►  │ wire.py  │ ──►  │ Detectors    │ ──►  │ _alerts  │
    │ query    │      │ adapt()  │      │ evaluate()   │      │ MQTT     │
    └──────────┘      └──────────┘      └──────────────┘      └──────────┘

On each poll cycle:
    1. Pull latest readings from each TSDB sensor-family table
    2. Run data through ``wire.adapt()`` to map DevB → Lead field names
    3. Pass each adapted sample to every registered detector
    4. Collect emitted events
    5. Publish events to ``omniview/{site}/_alerts/{event_type}``
    6. Feed events to the ActionCardGenerator for card creation
    7. Log cycle metrics

Design principles:
    - **Non-blocking:** Each detector runs independently — a failing
      detector logs an error and doesn't block others.
    - **Pluggable:** Adding a detector = adding one entry to the
      ``DETECTOR_REGISTRY``.
    - **Same ``evaluate(sample) → Event | None`` API** that
      ``GasOverheatDetector`` already uses.

Usage::

    from omniview.rules.detectors_live import DetectorsLiveRunner

    runner = DetectorsLiveRunner()
    runner.run_once()           # single poll cycle
    runner.run_forever()        # blocking loop with sleep

    # Or as a CLI entry point:
    python -m omniview.rules.detectors_live

Reference: System Workflow §3.3, Phase Plan Phase C/D, PRD FR3–FR8.
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from omniview.adapters.wire import adapt
from omniview.config import (
    DETECTOR_POLL_INTERVAL_S,
    DETECTOR_WINDOW_S,
    SITE_ID,
)
from omniview.rules.demand_window import DemandWindowDetector, MDRiskEvent
from omniview.rules.gas_overheat import GasOverheatDetector, GasOverheatEvent
from omniview.rules.gas_model import EnhancedGasOverheatDetector
from omniview.rules.lazy_idle import LazyIdleDetector, LazyIdleEvent
from omniview.rules.pressure_leak import PressureLeakDetector, PressureLeakEvent
from omniview.rules.vibration_zone import VibrationZoneDetector, VibrationZoneEvent

logger = logging.getLogger(__name__)


# ── Detector protocol ───────────────────────────────────────────────────


class Detector(Protocol):
    """Protocol for Layer 3 detectors — all must implement evaluate()."""

    def evaluate(self, sample: dict[str, Any]) -> Any: ...


# ── Detector registry ───────────────────────────────────────────────────


@dataclass
class DetectorEntry:
    """Registration entry for a detector."""
    name: str
    detector: Detector
    sensor_types: list[str]  # which sensor families this detector consumes
    enabled: bool = True


def build_default_registry() -> list[DetectorEntry]:
    """Create the default set of all Layer 3 detectors.

    Each detector is mapped to the sensor families it consumes.
    The runner will only pass readings from matching families.
    """
    return [
        DetectorEntry(
            name="gas_overheat",
            detector=EnhancedGasOverheatDetector(),
            # Gas + electrical: the enhanced detector caches electrical
            # current_a_avg internally for I²R correlation (§3 root-cause).
            # Unlike lazy_idle's broken cross-family pattern, this works
            # because the detector caches data and returns None on
            # electrical readings instead of requiring both in one sample.
            sensor_types=["gas", "electrical"],
        ),
        DetectorEntry(
            name="demand_window",
            detector=DemandWindowDetector(),
            sensor_types=["electrical"],
        ),
        DetectorEntry(
            name="lazy_idle",
            detector=LazyIdleDetector(),
            # Lazy-idle needs BOTH thermal + electrical — we run on both
            # and the detector internally handles missing fields
            sensor_types=["thermal", "electrical"],
        ),
        DetectorEntry(
            name="pressure_leak",
            detector=PressureLeakDetector(),
            sensor_types=["pressure"],
        ),
        DetectorEntry(
            name="vibration_zone",
            detector=VibrationZoneDetector(),
            sensor_types=["vibration"],
        ),
    ]


# ── Cycle metrics ────────────────────────────────────────────────────────


@dataclass
class CycleMetrics:
    """Metrics from a single poll cycle."""
    cycle_number: int = 0
    readings_processed: int = 0
    events_emitted: int = 0
    detectors_run: int = 0
    detectors_errored: int = 0
    duration_ms: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)


# ── Runner ───────────────────────────────────────────────────────────────


class DetectorsLiveRunner:
    """Poll-cycle runner that connects TSDB → wire.py → detectors → alerts.

    Parameters
    ----------
    site_id : str
        Site identifier for MQTT topics (default from config).
    poll_interval_s : int
        Seconds between poll cycles (default from config).
    window_s : int
        TSDB lookback window in seconds (default from config).
    registry : list[DetectorEntry], optional
        Custom detector registry (default builds all standard detectors).
    publish_fn : callable, optional
        ``(topic: str, payload_str: str) → bool`` for MQTT publishing.
        If None, events are logged but not published.
    """

    def __init__(
        self,
        site_id: str = SITE_ID,
        poll_interval_s: int = DETECTOR_POLL_INTERVAL_S,
        window_s: int = DETECTOR_WINDOW_S,
        registry: list[DetectorEntry] | None = None,
        publish_fn: Any = None,
    ) -> None:
        self._site_id = site_id
        self._poll_interval = poll_interval_s
        self._window_s = window_s
        self._registry = registry or build_default_registry()
        self._publish_fn = publish_fn
        self._cycle_count = 0
        self._stop = threading.Event()
        self._last_metrics: CycleMetrics | None = None

        # Cumulative stats
        self._total_readings = 0
        self._total_events = 0
        self._total_errors = 0

    @property
    def last_metrics(self) -> CycleMetrics | None:
        return self._last_metrics

    # ── Public API ───────────────────────────────────────────────────────

    def run_once(
        self, readings_by_family: dict[str, list[dict[str, Any]]] | None = None,
    ) -> CycleMetrics:
        """Execute a single poll cycle.

        Parameters
        ----------
        readings_by_family : dict, optional
            Pre-fetched readings grouped by sensor family.
            If None, pulls from TSDB via ``_fetch_readings()``.

        Returns
        -------
        CycleMetrics
        """
        self._cycle_count += 1
        start = time.monotonic()
        metrics = CycleMetrics(cycle_number=self._cycle_count)

        # 1. Fetch readings (from TSDB or provided)
        if readings_by_family is None:
            readings_by_family = self._fetch_readings()

        # 2. For each family, adapt and run matching detectors
        for family, readings in readings_by_family.items():
            for raw_reading in readings:
                # Ensure sensor_type is set for wire.adapt()
                if "sensor_type" not in raw_reading:
                    raw_reading["sensor_type"] = family

                # Apply wire.py field mapping (DevB → Lead names)
                adapted = adapt(raw_reading)

                metrics.readings_processed += 1

                # Run each detector that matches this family
                for entry in self._registry:
                    if not entry.enabled:
                        continue
                    if family not in entry.sensor_types:
                        continue

                    metrics.detectors_run += 1

                    try:
                        event = entry.detector.evaluate(adapted)
                        if event is not None:
                            event_dict = (
                                event.to_dict()
                                if hasattr(event, "to_dict")
                                else {"event": str(event)}
                            )
                            metrics.events_emitted += 1
                            metrics.events.append(event_dict)

                            # Publish to MQTT _alerts topic
                            self._publish_event(entry.name, event_dict)

                            logger.info(
                                "🔔 [%s] Event emitted: %s severity=%s device=%s",
                                entry.name,
                                event_dict.get("event_type", "unknown"),
                                event_dict.get("severity", "?"),
                                event_dict.get("device_id", "?"),
                            )
                    except Exception:
                        metrics.detectors_errored += 1
                        logger.exception(
                            "Detector %r failed on %s reading",
                            entry.name,
                            family,
                        )

        # Finalize
        metrics.duration_ms = (time.monotonic() - start) * 1000
        self._last_metrics = metrics
        self._total_readings += metrics.readings_processed
        self._total_events += metrics.events_emitted
        self._total_errors += metrics.detectors_errored

        if metrics.events_emitted > 0:
            logger.info(
                "Cycle %d: %d readings → %d events (%.1f ms)",
                self._cycle_count,
                metrics.readings_processed,
                metrics.events_emitted,
                metrics.duration_ms,
            )
        else:
            logger.debug(
                "Cycle %d: %d readings → 0 events (%.1f ms)",
                self._cycle_count,
                metrics.readings_processed,
                metrics.duration_ms,
            )

        return metrics

    def run_forever(self) -> None:
        """Blocking loop that runs poll cycles until stopped.

        Stop via Ctrl+C, SIGTERM, or calling ``stop()``.
        """
        logger.info(
            "DetectorsLiveRunner starting: poll=%ds, window=%ds, "
            "detectors=%d, site=%s",
            self._poll_interval,
            self._window_s,
            len([e for e in self._registry if e.enabled]),
            self._site_id,
        )

        # Register signal handlers
        def _handle_signal(signum: int, _frame: Any) -> None:
            logger.info("Received signal %d — stopping detector runner", signum)
            self._stop.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Detector cycle failed — will retry next cycle")

            self._stop.wait(timeout=self._poll_interval)

        logger.info(
            "DetectorsLiveRunner stopped. Totals: %d readings, %d events, %d errors",
            self._total_readings,
            self._total_events,
            self._total_errors,
        )

    def stop(self) -> None:
        """Signal the runner to stop after the current cycle."""
        self._stop.set()

    # ── Private ──────────────────────────────────────────────────────────

    def _fetch_readings(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch latest readings from TSDB for each sensor family.

        Returns a dict of ``{family: [reading_dicts]}``.
        """
        readings: dict[str, list[dict[str, Any]]] = {}

        try:
            from omniview.ingest.db import get_engine, query_latest

            engine = get_engine()
            families = ["electrical", "vibration", "thermal", "pressure", "gas", "stroke", "ambient"]

            for family in families:
                try:
                    rows = query_latest(
                        sensor_type=family,
                        limit=10,
                        engine=engine,
                    )
                    if rows:
                        readings[family] = rows
                except Exception:
                    logger.debug("No readings for family %s", family)

        except ImportError:
            logger.warning(
                "TSDB not available — run_once() with pre-fetched data instead"
            )
        except Exception:
            logger.exception("Failed to fetch readings from TSDB")

        return readings

    def _publish_event(self, detector_name: str, event_dict: dict[str, Any]) -> None:
        """Publish an event to the MQTT _alerts topic."""
        event_type = event_dict.get("event_type", detector_name)
        topic = f"omniview/{self._site_id}/_alerts/{event_type}"

        if self._publish_fn is not None:
            try:
                payload_str = json.dumps(event_dict, default=str)
                self._publish_fn(topic, payload_str)
                logger.debug("Published event to %s", topic)
            except Exception:
                logger.exception("Failed to publish event to %s", topic)
        else:
            logger.debug(
                "Event would be published to %s (no publish_fn configured)",
                topic,
            )


# ── CLI entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    runner = DetectorsLiveRunner()
    runner.run_forever()
