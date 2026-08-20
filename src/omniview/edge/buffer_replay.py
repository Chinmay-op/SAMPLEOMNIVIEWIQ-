"""
Buffer Replay Engine — OI-29
==============================

Timestamp-sorted merge and chronological replay of buffered telemetry
after a network outage.  Implements the "Gateway Buffer Replay &
Chronological Backfill" task from Epic OI-33.

Design notes (PRD §3.3 + System Workflow §4.4):
- After reconnect, the offline buffer (OI-28) may contain messages from
  **multiple sensor families** accumulated during the outage.
- This engine drains the buffer in **chronological batches**, applies a
  **timestamp-sorted merge** across all families, and replays them
  through the MQTT client in exact original order.
- The cloud subscriber + TSDB idempotent inserts (OI-15 ``ON CONFLICT
  DO NOTHING``) ensure replayed backfill never duplicates rows.
- The replay result provides full observability: per-sensor-family
  counts, replay window, and duration.

Usage::

    from omniview.edge.buffer_replay import BufferReplayEngine

    engine = BufferReplayEngine(buffer=offline_buf, client=mqtt_client)
    result = engine.replay()
    print(result.replayed, result.failed, result.duration_seconds)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from omniview.edge.offline_buffer import BufferedMessage, OfflineBuffer

logger = logging.getLogger(__name__)


# ── Replay result ───────────────────────────────────────────────────────────


@dataclass
class ReplayResult:
    """Outcome of a buffer replay operation.

    Attributes
    ----------
    total : int
        Total buffered messages attempted.
    replayed : int
        Successfully published messages.
    failed : int
        Messages that failed to publish.
    sensor_breakdown : dict[str, int]
        Per-sensor-type count of replayed messages.
    replay_window_start : float
        Earliest timestamp in the replayed batch (epoch seconds).
    replay_window_end : float
        Latest timestamp in the replayed batch (epoch seconds).
    duration_seconds : float
        Wall-clock duration of the replay operation.
    """

    total: int = 0
    replayed: int = 0
    failed: int = 0
    sensor_breakdown: dict[str, int] = field(default_factory=dict)
    replay_window_start: float = 0.0
    replay_window_end: float = 0.0
    duration_seconds: float = 0.0

    @property
    def is_complete(self) -> bool:
        """True if every message was either replayed or recorded as failed."""
        return self.replayed + self.failed == self.total


# ── Helpers ─────────────────────────────────────────────────────────────────


def _extract_sensor_type(topic: str) -> str:
    """Extract the sensor_type segment from an OmniView MQTT topic.

    Topic pattern: ``omniview/{site_id}/{node_id}/{sensor_type}``

    Returns ``"unknown"`` if the topic doesn't match the 4-segment
    pattern.
    """
    parts = topic.split("/")
    if len(parts) >= 4:
        return parts[3]
    return "unknown"


def timestamp_sorted_merge(
    messages: list[BufferedMessage],
) -> list[BufferedMessage]:
    """Sort messages by timestamp ascending (stable).

    This is the core ordering algorithm for chronological replay.
    Stable sort preserves insertion order for messages with equal
    timestamps (e.g. two different sensors polled at the same instant).

    Parameters
    ----------
    messages : list[BufferedMessage]
        Unsorted or partially sorted messages from the offline buffer.

    Returns
    -------
    list[BufferedMessage]
        Messages ordered by ``timestamp`` ascending.
    """
    return sorted(messages, key=lambda m: m.timestamp)


def group_by_sensor_type(
    messages: list[BufferedMessage],
) -> dict[str, list[BufferedMessage]]:
    """Group messages by sensor family extracted from the topic.

    Parameters
    ----------
    messages : list[BufferedMessage]
        Messages to group.

    Returns
    -------
    dict[str, list[BufferedMessage]]
        Keys are sensor type strings (e.g. ``"electrical"``),
        values are lists of messages for that family.
    """
    groups: dict[str, list[BufferedMessage]] = {}
    for msg in messages:
        sensor = _extract_sensor_type(msg.topic)
        groups.setdefault(sensor, []).append(msg)
    return groups


# ── Replay engine ───────────────────────────────────────────────────────────


class BufferReplayEngine:
    """Chronological replay engine for the offline buffer.

    After a network reconnect, this engine:

    1. Drains the buffer in configurable batches
    2. Applies a timestamp-sorted merge across all sensor families
    3. Publishes each message to MQTT in exact chronological order
    4. Acks successfully published messages (removing them from buffer)
    5. Tracks per-family metrics for observability

    Parameters
    ----------
    buffer : OfflineBuffer
        The SQLite offline buffer instance.
    publish_fn : callable
        A callable ``(topic, payload_str, qos) -> bool`` that publishes
        a message.  Returns ``True`` if published successfully.
    batch_size : int
        Number of messages to drain per batch (default 50).
    inter_batch_delay : float
        Seconds to pause between batches to avoid flooding the broker
        (default 0.1).
    """

    def __init__(
        self,
        buffer: OfflineBuffer,
        publish_fn: Any = None,
        batch_size: int = 50,
        inter_batch_delay: float = 0.1,
    ) -> None:
        self._buffer = buffer
        self._publish_fn = publish_fn
        self._batch_size = batch_size
        self._inter_batch_delay = inter_batch_delay
        self._last_result: ReplayResult | None = None

    @property
    def last_result(self) -> ReplayResult | None:
        """The result of the most recent replay, or ``None``."""
        return self._last_result

    def replay(
        self,
        is_connected_fn: Any = None,
        stop_event: Any = None,
    ) -> ReplayResult:
        """Execute a full chronological replay of the offline buffer.

        Drains all buffered messages in batches, sorts each batch by
        timestamp, publishes via MQTT, and acks on success.

        Parameters
        ----------
        is_connected_fn : callable, optional
            ``() -> bool`` — checked before each batch.  If it returns
            ``False``, replay stops early (connection lost again).
        stop_event : threading.Event, optional
            If set, replay stops after the current batch completes.

        Returns
        -------
        ReplayResult
            Full accounting of the replay operation.
        """
        result = ReplayResult(total=self._buffer.count())
        wall_start = time.monotonic()

        if result.total == 0:
            result.duration_seconds = 0.0
            self._last_result = result
            logger.info("Buffer replay: nothing to replay (buffer empty)")
            return result

        logger.info(
            "Buffer replay starting: %d messages to replay chronologically",
            result.total,
        )

        all_replayed = 0
        all_failed = 0

        while True:
            # Check connectivity / stop signal
            if is_connected_fn and not is_connected_fn():
                logger.warning(
                    "Buffer replay interrupted: connection lost "
                    "(replayed=%d, remaining=%d)",
                    all_replayed,
                    self._buffer.count(),
                )
                break

            if stop_event and stop_event.is_set():
                logger.info(
                    "Buffer replay stopped by signal "
                    "(replayed=%d, remaining=%d)",
                    all_replayed,
                    self._buffer.count(),
                )
                break

            # Drain a batch (already ordered by timestamp ASC from SQLite)
            batch = self._buffer.drain(self._batch_size)
            if not batch:
                break  # buffer exhausted

            # Timestamp-sorted merge — ensures strict chronological order
            # even if the SQLite drain had any ordering edge cases
            sorted_batch = timestamp_sorted_merge(batch)

            # Track replay window
            if sorted_batch:
                batch_start = sorted_batch[0].timestamp
                batch_end = sorted_batch[-1].timestamp
                if result.replay_window_start == 0.0:
                    result.replay_window_start = batch_start
                result.replay_window_end = max(
                    result.replay_window_end, batch_end
                )

            # Publish each message in chronological order
            published_ids: list[int] = []
            batch_failed = 0

            for msg in sorted_batch:
                # Abort batch if connection lost
                if is_connected_fn and not is_connected_fn():
                    break
                if stop_event and stop_event.is_set():
                    break

                success = self._try_publish(msg)
                if success:
                    published_ids.append(msg.id)
                    # Track per-sensor breakdown
                    sensor = _extract_sensor_type(msg.topic)
                    result.sensor_breakdown[sensor] = (
                        result.sensor_breakdown.get(sensor, 0) + 1
                    )
                else:
                    batch_failed += 1
                    # Stop batch on first failure — retry next cycle
                    break

            # Ack successfully published messages
            if published_ids:
                self._buffer.ack(published_ids)

            all_replayed += len(published_ids)
            all_failed += batch_failed

            logger.debug(
                "Buffer replay batch: %d/%d published, %d failed",
                len(published_ids),
                len(sorted_batch),
                batch_failed,
            )

            # If we had a failure, stop — will retry on next drain cycle
            if batch_failed > 0:
                break

            # Inter-batch delay to avoid flooding the broker
            if self._inter_batch_delay > 0:
                time.sleep(self._inter_batch_delay)

        # Finalise result
        result.replayed = all_replayed
        result.failed = all_failed
        result.duration_seconds = time.monotonic() - wall_start
        self._last_result = result

        logger.info(
            "Buffer replay complete: %d total, %d replayed, %d failed, "
            "%.1fs elapsed, window=[%.0f → %.0f]",
            result.total,
            result.replayed,
            result.failed,
            result.duration_seconds,
            result.replay_window_start,
            result.replay_window_end,
        )

        if result.sensor_breakdown:
            for sensor, count in sorted(result.sensor_breakdown.items()):
                logger.info("  %s: %d messages replayed", sensor, count)

        return result

    def _try_publish(self, msg: BufferedMessage) -> bool:
        """Attempt to publish a single buffered message.

        Parameters
        ----------
        msg : BufferedMessage
            The message to publish.

        Returns
        -------
        bool
            ``True`` if published successfully, ``False`` otherwise.
        """
        if self._publish_fn is None:
            logger.error("No publish function configured for replay engine")
            return False

        try:
            payload_str = json.dumps(msg.payload, default=str)
            return self._publish_fn(msg.topic, payload_str)
        except Exception:
            logger.exception(
                "Failed to publish buffered message ID %d to %s",
                msg.id,
                msg.topic,
            )
            return False
