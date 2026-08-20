"""
Unit tests for OI-29 — Buffer Replay & Chronological Backfill

Tests:
- Timestamp-sorted merge algorithm
- Sensor-type grouping
- Full replay engine (chronological, idempotent, edge cases)
- ReplayResult dataclass
- BackfillCoordinator (batch insert, gap verification, summary)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omniview.edge.buffer_replay import (
    BufferReplayEngine,
    ReplayResult,
    _extract_sensor_type,
    group_by_sensor_type,
    timestamp_sorted_merge,
)
from omniview.edge.offline_buffer import BufferedMessage, OfflineBuffer


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "replay_test.db"


@pytest.fixture
def buffer(temp_db_path: Path) -> OfflineBuffer:
    return OfflineBuffer(temp_db_path)


def _make_msg(
    id: int, topic: str, payload: dict, timestamp: float
) -> BufferedMessage:
    """Create a BufferedMessage for testing."""
    return BufferedMessage(id=id, topic=topic, payload=payload, timestamp=timestamp)


# ── TestTimestampSortedMerge ────────────────────────────────────────────────


class TestTimestampSortedMerge:
    """Test the core ordering algorithm."""

    def test_already_sorted(self) -> None:
        msgs = [
            _make_msg(1, "t/a", {}, 100.0),
            _make_msg(2, "t/b", {}, 200.0),
            _make_msg(3, "t/c", {}, 300.0),
        ]
        result = timestamp_sorted_merge(msgs)
        assert [m.id for m in result] == [1, 2, 3]

    def test_reverse_sorted(self) -> None:
        msgs = [
            _make_msg(1, "t/a", {}, 300.0),
            _make_msg(2, "t/b", {}, 200.0),
            _make_msg(3, "t/c", {}, 100.0),
        ]
        result = timestamp_sorted_merge(msgs)
        assert [m.id for m in result] == [3, 2, 1]

    def test_interleaved(self) -> None:
        msgs = [
            _make_msg(1, "t/a", {}, 300.0),
            _make_msg(2, "t/b", {}, 100.0),
            _make_msg(3, "t/c", {}, 200.0),
        ]
        result = timestamp_sorted_merge(msgs)
        assert [m.id for m in result] == [2, 3, 1]

    def test_equal_timestamps_stable(self) -> None:
        """Messages with the same timestamp preserve insertion order (stable sort)."""
        msgs = [
            _make_msg(1, "omniview/s/n/electrical", {}, 100.0),
            _make_msg(2, "omniview/s/n/vibration", {}, 100.0),
            _make_msg(3, "omniview/s/n/thermal", {}, 100.0),
        ]
        result = timestamp_sorted_merge(msgs)
        # Stable sort: original order preserved for equal timestamps
        assert [m.id for m in result] == [1, 2, 3]

    def test_empty_input(self) -> None:
        result = timestamp_sorted_merge([])
        assert result == []


# ── TestGroupBySensorType ───────────────────────────────────────────────────


class TestGroupBySensorType:
    """Test sensor family grouping from topics."""

    def test_groups_multiple_families(self) -> None:
        msgs = [
            _make_msg(1, "omniview/pune/comp-01/electrical", {}, 100.0),
            _make_msg(2, "omniview/pune/comp-01/vibration", {}, 101.0),
            _make_msg(3, "omniview/pune/comp-01/electrical", {}, 102.0),
            _make_msg(4, "omniview/pune/floor/ambient", {}, 103.0),
        ]
        groups = group_by_sensor_type(msgs)
        assert len(groups) == 3
        assert len(groups["electrical"]) == 2
        assert len(groups["vibration"]) == 1
        assert len(groups["ambient"]) == 1

    def test_unknown_topic_format(self) -> None:
        msgs = [
            _make_msg(1, "bad-topic", {}, 100.0),
            _make_msg(2, "also/bad", {}, 101.0),
        ]
        groups = group_by_sensor_type(msgs)
        assert "unknown" in groups
        assert len(groups["unknown"]) == 2

    def test_single_family(self) -> None:
        msgs = [
            _make_msg(1, "omniview/s/n/thermal", {}, 100.0),
            _make_msg(2, "omniview/s/n/thermal", {}, 200.0),
        ]
        groups = group_by_sensor_type(msgs)
        assert len(groups) == 1
        assert len(groups["thermal"]) == 2


# ── TestExtractSensorType ───────────────────────────────────────────────────


class TestExtractSensorType:
    """Test topic segment extraction."""

    def test_valid_topic(self) -> None:
        assert _extract_sensor_type("omniview/pune/comp/electrical") == "electrical"

    def test_short_topic(self) -> None:
        assert _extract_sensor_type("bad/topic") == "unknown"

    def test_five_segments(self) -> None:
        assert _extract_sensor_type("omniview/s/n/gas/extra") == "gas"


# ── TestReplayResult ────────────────────────────────────────────────────────


class TestReplayResult:
    """Test ReplayResult dataclass."""

    def test_defaults(self) -> None:
        r = ReplayResult()
        assert r.total == 0
        assert r.replayed == 0
        assert r.failed == 0
        assert r.sensor_breakdown == {}
        assert r.duration_seconds == 0.0

    def test_is_complete_when_all_replayed(self) -> None:
        r = ReplayResult(total=10, replayed=10, failed=0)
        assert r.is_complete is True

    def test_is_complete_with_failures(self) -> None:
        r = ReplayResult(total=10, replayed=7, failed=3)
        assert r.is_complete is True

    def test_is_not_complete_when_unaccounted(self) -> None:
        r = ReplayResult(total=10, replayed=5, failed=2)
        assert r.is_complete is False


# ── TestBufferReplayEngine ──────────────────────────────────────────────────


class TestReplayChronological:
    """Test that replay produces chronological output."""

    def test_empty_buffer_returns_clean_result(self, buffer: OfflineBuffer) -> None:
        engine = BufferReplayEngine(buffer=buffer, publish_fn=lambda t, p: True)
        result = engine.replay()
        assert result.total == 0
        assert result.replayed == 0
        assert result.failed == 0
        assert result.is_complete is True

    def test_replay_is_chronological(self, buffer: OfflineBuffer) -> None:
        """Messages are published in timestamp order regardless of buffer insertion order."""
        # Insert out of chronological order
        buffer.store("omniview/s/n/electrical", {"val": 3}, timestamp=300.0)
        buffer.store("omniview/s/n/electrical", {"val": 1}, timestamp=100.0)
        buffer.store("omniview/s/n/electrical", {"val": 2}, timestamp=200.0)

        published_order: list[float] = []

        def mock_publish(topic: str, payload_str: str) -> bool:
            import json
            payload = json.loads(payload_str)
            published_order.append(payload["val"])
            return True

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=mock_publish, batch_size=10
        )
        result = engine.replay()

        assert result.replayed == 3
        assert result.failed == 0
        # Chronological order verified
        assert published_order == [1, 2, 3]

    def test_multi_family_interleave_is_chronological(
        self, buffer: OfflineBuffer
    ) -> None:
        """Messages from different sensor families are interleaved by timestamp."""
        buffer.store("omniview/s/n/electrical", {"t": "e1"}, timestamp=100.0)
        buffer.store("omniview/s/n/vibration", {"t": "v1"}, timestamp=150.0)
        buffer.store("omniview/s/n/electrical", {"t": "e2"}, timestamp=200.0)
        buffer.store("omniview/s/n/thermal", {"t": "th1"}, timestamp=125.0)

        published_topics: list[str] = []

        def mock_publish(topic: str, payload_str: str) -> bool:
            published_topics.append(topic.split("/")[-1])
            return True

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=mock_publish, batch_size=10
        )
        result = engine.replay()

        assert result.replayed == 4
        # Expected chronological order: e1@100, th1@125, v1@150, e2@200
        assert published_topics == ["electrical", "thermal", "vibration", "electrical"]

    def test_partial_failure_stops_batch(self, buffer: OfflineBuffer) -> None:
        """On publish failure, stop the batch and leave remaining in buffer."""
        buffer.store("omniview/s/n/electrical", {"v": 1}, timestamp=100.0)
        buffer.store("omniview/s/n/electrical", {"v": 2}, timestamp=200.0)
        buffer.store("omniview/s/n/electrical", {"v": 3}, timestamp=300.0)

        call_count = 0

        def fail_on_second(topic: str, payload_str: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count != 2  # Fail on second message

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=fail_on_second, batch_size=10
        )
        result = engine.replay()

        assert result.replayed == 1  # Only first message succeeded
        assert result.failed == 1   # Second message failed
        # Third message stays in buffer (never attempted after failure)
        assert buffer.count() == 2  # 2nd and 3rd remain


class TestReplayIdempotency:
    """Test that replay is idempotent (safe to retry)."""

    def test_replay_after_full_ack_is_noop(self, buffer: OfflineBuffer) -> None:
        """After a complete replay, replaying again finds an empty buffer."""
        buffer.store("omniview/s/n/electrical", {"v": 1}, timestamp=100.0)

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True, batch_size=10
        )

        # First replay
        r1 = engine.replay()
        assert r1.replayed == 1
        assert buffer.count() == 0

        # Second replay — nothing left
        r2 = engine.replay()
        assert r2.total == 0
        assert r2.replayed == 0
        assert r2.is_complete is True

    def test_partial_ack_replays_remainder(self, buffer: OfflineBuffer) -> None:
        """If only some messages are acked, the rest are replayed next time."""
        buffer.store("omniview/s/n/electrical", {"v": 1}, timestamp=100.0)
        buffer.store("omniview/s/n/electrical", {"v": 2}, timestamp=200.0)
        buffer.store("omniview/s/n/electrical", {"v": 3}, timestamp=300.0)

        call_count = 0

        def fail_on_second(topic: str, payload_str: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count != 2

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=fail_on_second, batch_size=10
        )

        # First replay: 1 success, 1 failure, 1 unattempted
        r1 = engine.replay()
        assert r1.replayed == 1
        assert buffer.count() == 2

        # Reset — all succeed now
        engine2 = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True, batch_size=10
        )
        r2 = engine2.replay()
        assert r2.replayed == 2
        assert buffer.count() == 0

    def test_replaying_same_data_twice_succeeds(
        self, buffer: OfflineBuffer
    ) -> None:
        """Even if the same data is replayed (via MQTT), TSDB ON CONFLICT handles it."""
        # This tests the contract — at the edge layer, replay just publishes.
        # TSDB dedup happens downstream.
        buffer.store("omniview/s/n/electrical", {"kva": 100}, timestamp=100.0)

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True, batch_size=10
        )
        r = engine.replay()
        assert r.replayed == 1
        assert buffer.count() == 0


class TestReplaySensorBreakdown:
    """Test per-sensor-family metrics in replay result."""

    def test_sensor_breakdown_populated(self, buffer: OfflineBuffer) -> None:
        buffer.store("omniview/s/n/electrical", {}, timestamp=100.0)
        buffer.store("omniview/s/n/electrical", {}, timestamp=200.0)
        buffer.store("omniview/s/n/vibration", {}, timestamp=150.0)
        buffer.store("omniview/s/n/thermal", {}, timestamp=175.0)

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True, batch_size=10
        )
        result = engine.replay()

        assert result.sensor_breakdown["electrical"] == 2
        assert result.sensor_breakdown["vibration"] == 1
        assert result.sensor_breakdown["thermal"] == 1


class TestReplayWindow:
    """Test replay window timestamps."""

    def test_replay_window_set(self, buffer: OfflineBuffer) -> None:
        buffer.store("omniview/s/n/electrical", {}, timestamp=100.0)
        buffer.store("omniview/s/n/electrical", {}, timestamp=500.0)

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True, batch_size=10
        )
        result = engine.replay()

        assert result.replay_window_start == 100.0
        assert result.replay_window_end == 500.0


class TestReplayConnectivityCheck:
    """Test that replay respects connectivity checks."""

    def test_stops_when_disconnected(self, buffer: OfflineBuffer) -> None:
        for i in range(10):
            buffer.store("omniview/s/n/electrical", {"v": i}, timestamp=float(i * 10))

        publish_count = 0

        def mock_publish(topic: str, payload_str: str) -> bool:
            nonlocal publish_count
            publish_count += 1
            return True

        call_count = 0

        def is_connected() -> bool:
            nonlocal call_count
            call_count += 1
            # Disconnect after 5 checks (mid-batch)
            return call_count < 6

        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=mock_publish, batch_size=100,
            inter_batch_delay=0,
        )
        result = engine.replay(is_connected_fn=is_connected)

        # Should have stopped before completing all 10
        assert result.replayed < 10
        assert buffer.count() > 0  # Some messages remain


class TestLastResult:
    """Test the last_result property."""

    def test_last_result_initially_none(self, buffer: OfflineBuffer) -> None:
        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True
        )
        assert engine.last_result is None

    def test_last_result_updated_after_replay(self, buffer: OfflineBuffer) -> None:
        buffer.store("omniview/s/n/electrical", {}, timestamp=100.0)
        engine = BufferReplayEngine(
            buffer=buffer, publish_fn=lambda t, p: True
        )
        engine.replay()
        assert engine.last_result is not None
        assert engine.last_result.replayed == 1


# ── TestBackfillCoordinator ─────────────────────────────────────────────────


class TestBackfillCoordinator:
    """Test the cloud-side backfill coordinator."""

    def test_process_backfill_batch_calls_backfill_insert(self) -> None:
        from omniview.ingest.backfill_coordinator import BackfillCoordinator
        from omniview.ingest.db import BackfillResult

        with patch("omniview.ingest.backfill_coordinator.backfill_insert") as mock_bf:
            mock_bf.return_value = BackfillResult(
                total=3, inserted=2, duplicates=1, sensor_type="electrical"
            )

            coordinator = BackfillCoordinator()
            readings = {
                "electrical": [
                    {
                        "device_id": "comp-01",
                        "site_id": "pune",
                        "time": datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                        "data": {"kva": 100},
                    },
                    {
                        "device_id": "comp-01",
                        "site_id": "pune",
                        "time": datetime(2026, 8, 10, 12, 0, 15, tzinfo=timezone.utc),
                        "data": {"kva": 101},
                    },
                    {
                        "device_id": "comp-01",
                        "site_id": "pune",
                        "time": datetime(2026, 8, 10, 12, 0, 30, tzinfo=timezone.utc),
                        "data": {"kva": 102},
                    },
                ],
            }

            results = coordinator.process_backfill_batch(readings)

            mock_bf.assert_called_once_with(
                sensor_type="electrical",
                readings=readings["electrical"],
                engine=None,
            )
            assert "electrical" in results
            assert results["electrical"].inserted == 2
            assert results["electrical"].duplicates == 1

    def test_process_backfill_skips_empty_families(self) -> None:
        from omniview.ingest.backfill_coordinator import BackfillCoordinator

        with patch("omniview.ingest.backfill_coordinator.backfill_insert") as mock_bf:
            coordinator = BackfillCoordinator()
            results = coordinator.process_backfill_batch({"electrical": []})

            mock_bf.assert_not_called()
            assert len(results) == 0

    def test_verify_no_gaps_returns_coverage(self) -> None:
        from omniview.ingest.backfill_coordinator import BackfillCoordinator

        with patch(
            "omniview.ingest.backfill_coordinator.query_by_time_range"
        ) as mock_q:
            # Simulate 40 rows for a 10-minute window with 15s intervals
            # Expected: 600/15 = 40 readings → 100% coverage
            mock_q.return_value = [{"time": i} for i in range(40)]

            coordinator = BackfillCoordinator()
            result = coordinator.verify_no_gaps(
                sensor_type="electrical",
                device_id="comp-01",
                start=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 10, 12, 10, tzinfo=timezone.utc),
                expected_interval_seconds=15,
                tolerance=0.8,
            )

            assert result["has_gaps"] is False
            assert result["expected"] == 40
            assert result["actual"] == 40
            assert result["coverage"] == 1.0

    def test_verify_no_gaps_detects_gap(self) -> None:
        from omniview.ingest.backfill_coordinator import BackfillCoordinator

        with patch(
            "omniview.ingest.backfill_coordinator.query_by_time_range"
        ) as mock_q:
            # Only 10 rows for a 10-minute window with 15s intervals
            # Expected: 40, actual: 10 → 25% coverage (below 80% threshold)
            mock_q.return_value = [{"time": i} for i in range(10)]

            coordinator = BackfillCoordinator()
            result = coordinator.verify_no_gaps(
                sensor_type="electrical",
                device_id="comp-01",
                start=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 10, 12, 10, tzinfo=timezone.utc),
                expected_interval_seconds=15,
                tolerance=0.8,
            )

            assert result["has_gaps"] is True
            assert result["expected"] == 40
            assert result["actual"] == 10
            assert result["coverage"] == 0.25

    def test_get_backfill_summary(self) -> None:
        from omniview.ingest.backfill_coordinator import BackfillCoordinator
        from omniview.ingest.db import BackfillResult

        with patch("omniview.ingest.backfill_coordinator.backfill_insert") as mock_bf:
            mock_bf.side_effect = [
                BackfillResult(total=5, inserted=4, duplicates=1, sensor_type="electrical"),
                BackfillResult(total=3, inserted=3, duplicates=0, sensor_type="vibration"),
            ]

            coordinator = BackfillCoordinator()
            coordinator.process_backfill_batch({
                "electrical": [{"device_id": "c", "site_id": "s", "time": datetime.now(timezone.utc), "data": {}}] * 5,
                "vibration": [{"device_id": "c", "site_id": "s", "time": datetime.now(timezone.utc), "data": {}}] * 3,
            })

            summary = coordinator.get_backfill_summary()
            assert summary["total_inserted"] == 7
            assert summary["total_duplicates"] == 1
            assert summary["families_processed"] == 2
            assert summary["all_clean"] is True
