"""
NTP Drift Guard — OI-53
========================

Monitors the gateway clock against an NTP reference and raises alerts when
the offset exceeds the PRD NFR threshold (<5 s).

**Why this exists:**
Every sensor reading's timestamp must align with MSEDCL's 15-minute billing
window.  A drift >5 s makes MD near-miss detection unreliable; a drift >30 s
completely invalidates the rolling kVA calculation.  This module enforces
the "NTP-synced, sub-second; must not drift >5 s" NFR by checking
periodically and logging / alerting on breach.

**Failure modes (documented for pilot):**

1. *NTP server unreachable* — Logged as WARNING, last known offset retained,
   retry on next cycle.  No alert is fired for a single transient failure.
2. *Consecutive NTP failures (>= NTP_MAX_RETRIES)* — Logged as CRITICAL
   "NTP unreachable" event.  An MQTT alert is published so the dashboard
   can surface this to the operator.
3. *Gateway has no internet* — The guard degrades gracefully.  Offline
   buffer (OI-28) continues to cache telemetry.  The guard will resume
   checking once connectivity returns.

Design:

* Pure-function ``check_drift()`` for one-shot use and testability.
* ``NTPDriftGuard`` wraps ``check_drift()`` in a background thread with
  configurable interval, logging, and optional MQTT alert publishing.
* All NTP calls go through ``ntplib.NTPClient`` — easily mockable.

Usage::

    from omniview.edge.ntp_guard import NTPDriftGuard

    guard = NTPDriftGuard()
    guard.start()           # background thread
    ...
    guard.stop()

    # Or one-shot:
    from omniview.edge.ntp_guard import check_drift
    status = check_drift()
    print(status.offset_seconds, status.is_synced)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import ntplib

from omniview.config import (
    NTP_CHECK_INTERVAL_S,
    NTP_DRIFT_THRESHOLD_S,
    NTP_MAX_RETRIES,
    NTP_SERVER,
    NTP_TIMEOUT_S,
    SITE_ID,
)

logger = logging.getLogger(__name__)

# ── Data types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftStatus:
    """Result of a single NTP drift check.

    Attributes
    ----------
    offset_seconds : float
        Signed offset — positive means local clock is *ahead* of NTP.
    is_synced : bool
        ``True`` if ``abs(offset_seconds) <= threshold``.
    ntp_server : str
        The NTP server that was queried.
    check_time : str
        ISO-8601 timestamp of when the check was performed.
    stratum : int
        NTP stratum of the server response (1 = primary, 2+ = secondary).
    threshold_seconds : float
        The threshold used for this check.
    error : str | None
        Non-``None`` when the NTP query failed.
    """

    offset_seconds: float
    is_synced: bool
    ntp_server: str
    check_time: str
    stratum: int
    threshold_seconds: float
    error: str | None = None


# ── One-shot check ───────────────────────────────────────────────────────


def check_drift(
    *,
    server: str = NTP_SERVER,
    threshold_s: float = NTP_DRIFT_THRESHOLD_S,
    timeout_s: float = NTP_TIMEOUT_S,
    ntp_client: ntplib.NTPClient | None = None,
) -> DriftStatus:
    """Query an NTP server and return the current drift status.

    Parameters
    ----------
    server : str
        Hostname of the NTP server to query.
    threshold_s : float
        Maximum acceptable absolute offset in seconds.
    timeout_s : float
        Seconds to wait for the NTP response.
    ntp_client : ntplib.NTPClient, optional
        Injectable client instance (for testing).

    Returns
    -------
    DriftStatus
        Always returns a status — on NTP failure, ``error`` is populated
        and ``offset_seconds`` is ``0.0`` with ``is_synced = False``.
    """
    client = ntp_client or ntplib.NTPClient()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        response = client.request(server, version=3, timeout=timeout_s)
        offset = response.offset  # seconds, signed
        stratum = response.stratum
        synced = abs(offset) <= threshold_s

        return DriftStatus(
            offset_seconds=round(offset, 6),
            is_synced=synced,
            ntp_server=server,
            check_time=now_iso,
            stratum=stratum,
            threshold_seconds=threshold_s,
            error=None,
        )

    except (ntplib.NTPException, OSError, Exception) as exc:
        logger.warning(
            "NTP query to %s failed: %s",
            server,
            exc,
        )
        return DriftStatus(
            offset_seconds=0.0,
            is_synced=False,
            ntp_server=server,
            check_time=now_iso,
            stratum=0,
            threshold_seconds=threshold_s,
            error=str(exc),
        )


# ── Guard (background thread) ───────────────────────────────────────────


# Type alias for the optional MQTT publish callback.
PublishFn = Callable[[str, dict[str, Any]], None]


class NTPDriftGuard:
    """Background monitor that checks NTP drift and fires alerts.

    Parameters
    ----------
    server : str
        NTP server hostname.
    threshold_s : float
        Drift threshold in seconds (PRD NFR: 5.0).
    check_interval_s : int
        Seconds between successive NTP checks.
    max_retries : int
        Consecutive NTP failures before firing an "NTP unreachable" alert.
    timeout_s : float
        Per-query NTP timeout.
    site_id : str
        Used to build the MQTT alert topic.
    publish_fn : callable, optional
        ``fn(topic, payload_dict)`` — if provided, drift alerts are
        published via MQTT.  If ``None``, only logging occurs.
    ntp_client : ntplib.NTPClient, optional
        Injectable NTP client (for testing).
    """

    # MQTT topic template for drift alerts
    ALERT_TOPIC_TEMPLATE = "omniview/{site_id}/system/ntp_drift_alert"

    def __init__(
        self,
        *,
        server: str = NTP_SERVER,
        threshold_s: float = NTP_DRIFT_THRESHOLD_S,
        check_interval_s: int = NTP_CHECK_INTERVAL_S,
        max_retries: int = NTP_MAX_RETRIES,
        timeout_s: float = NTP_TIMEOUT_S,
        site_id: str = SITE_ID,
        publish_fn: PublishFn | None = None,
        ntp_client: ntplib.NTPClient | None = None,
    ) -> None:
        self._server = server
        self._threshold_s = threshold_s
        self._check_interval_s = check_interval_s
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._site_id = site_id
        self._publish_fn = publish_fn
        self._ntp_client = ntp_client or ntplib.NTPClient()

        # State
        self._consecutive_failures: int = 0
        self._consecutive_drift_breaches: int = 0
        self._last_status: DriftStatus | None = None
        self._history: list[DriftStatus] = []
        self._max_history: int = 60  # keep last 60 checks (~1 hour at 60s)

        # Threading
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Alert topic for this site
        self._alert_topic = self.ALERT_TOPIC_TEMPLATE.format(
            site_id=self._site_id
        )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """``True`` if the background monitor thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_status(self) -> DriftStatus | None:
        """Most recent drift check result."""
        with self._lock:
            return self._last_status

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive NTP query failures."""
        with self._lock:
            return self._consecutive_failures

    @property
    def consecutive_drift_breaches(self) -> int:
        """Number of consecutive checks where drift exceeded threshold."""
        with self._lock:
            return self._consecutive_drift_breaches

    @property
    def history(self) -> list[DriftStatus]:
        """Copy of recent drift check history."""
        with self._lock:
            return list(self._history)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background drift-check thread.

        Raises
        ------
        RuntimeError
            If the guard is already running.
        """
        if self.is_running:
            raise RuntimeError("NTPDriftGuard is already running")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ntp-drift-guard",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "NTP drift guard started (server=%s, threshold=%.1fs, interval=%ds)",
            self._server,
            self._threshold_s,
            self._check_interval_s,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the background thread to stop and wait for it.

        Parameters
        ----------
        timeout : float
            Maximum seconds to wait for the thread to finish.
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("NTP drift guard stopped")

    # ── Core loop ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main loop — runs in the background thread."""
        while not self._stop_event.is_set():
            self.run_check()
            # Use the stop event as the sleep mechanism so stop() is instant
            self._stop_event.wait(timeout=self._check_interval_s)

    def run_check(self) -> DriftStatus:
        """Execute a single drift check, update state, and log/alert.

        This is the public entry point for both the background loop and
        manual one-shot usage.

        Returns
        -------
        DriftStatus
            The result of this check.
        """
        status = check_drift(
            server=self._server,
            threshold_s=self._threshold_s,
            timeout_s=self._timeout_s,
            ntp_client=self._ntp_client,
        )

        with self._lock:
            self._last_status = status
            self._history.append(status)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            if status.error is not None:
                # NTP query failed
                self._consecutive_failures += 1
                self._log_ntp_failure(status)

                if self._consecutive_failures >= self._max_retries:
                    self._fire_ntp_unreachable_alert(status)
            else:
                # NTP query succeeded
                self._consecutive_failures = 0

                if status.is_synced:
                    self._consecutive_drift_breaches = 0
                    self._log_sync_ok(status)
                else:
                    self._consecutive_drift_breaches += 1
                    self._log_drift_breach(status)
                    self._fire_drift_alert(status)

        return status

    # ── Logging helpers ──────────────────────────────────────────────────

    def _log_sync_ok(self, status: DriftStatus) -> None:
        """Log a successful sync check."""
        logger.info(
            "NTP sync OK: offset=%.4fs (threshold=%.1fs, server=%s, stratum=%d)",
            status.offset_seconds,
            status.threshold_seconds,
            status.ntp_server,
            status.stratum,
        )

    def _log_drift_breach(self, status: DriftStatus) -> None:
        """Log when drift exceeds threshold."""
        logger.critical(
            "NTP DRIFT BREACH: offset=%.4fs exceeds threshold %.1fs "
            "(server=%s, stratum=%d, consecutive=%d)",
            status.offset_seconds,
            status.threshold_seconds,
            status.ntp_server,
            status.stratum,
            self._consecutive_drift_breaches,
        )

    def _log_ntp_failure(self, status: DriftStatus) -> None:
        """Log an NTP query failure."""
        logger.warning(
            "NTP check failed (attempt %d/%d): %s",
            self._consecutive_failures,
            self._max_retries,
            status.error,
        )

    # ── MQTT alert helpers ───────────────────────────────────────────────

    def _fire_drift_alert(self, status: DriftStatus) -> None:
        """Publish an MQTT alert when drift exceeds threshold."""
        if self._publish_fn is None:
            return

        payload = {
            "event_type": "NTP_DRIFT_ALERT",
            "timestamp": status.check_time,
            "gateway_id": f"omniview-edge-{self._site_id}",
            "drift_seconds": status.offset_seconds,
            "threshold_seconds": status.threshold_seconds,
            "ntp_server": status.ntp_server,
            "stratum": status.stratum,
            "consecutive_failures": self._consecutive_drift_breaches,
            "severity": "CRITICAL",
        }

        try:
            self._publish_fn(self._alert_topic, payload)
            logger.info(
                "Drift alert published to %s", self._alert_topic
            )
        except Exception as exc:
            logger.error(
                "Failed to publish drift alert: %s", exc
            )

    def _fire_ntp_unreachable_alert(self, status: DriftStatus) -> None:
        """Publish an MQTT alert when NTP is unreachable for too long."""
        logger.critical(
            "NTP UNREACHABLE: %d consecutive failures (server=%s)",
            self._consecutive_failures,
            self._server,
        )

        if self._publish_fn is None:
            return

        payload = {
            "event_type": "NTP_UNREACHABLE",
            "timestamp": status.check_time,
            "gateway_id": f"omniview-edge-{self._site_id}",
            "ntp_server": status.ntp_server,
            "consecutive_failures": self._consecutive_failures,
            "last_error": status.error,
            "severity": "CRITICAL",
        }

        try:
            self._publish_fn(self._alert_topic, payload)
            logger.info(
                "NTP unreachable alert published to %s",
                self._alert_topic,
            )
        except Exception as exc:
            logger.error(
                "Failed to publish NTP unreachable alert: %s", exc
            )

    # ── Repr ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        running = "running" if self.is_running else "stopped"
        return (
            f"NTPDriftGuard(server={self._server!r}, "
            f"threshold={self._threshold_s}s, "
            f"interval={self._check_interval_s}s, "
            f"status={running})"
        )
