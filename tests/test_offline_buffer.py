import json
import sqlite3
import time
from pathlib import Path

import pytest

from omniview.edge.offline_buffer import OfflineBuffer


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "offline_buffer.db"


@pytest.fixture
def buffer(temp_db_path: Path) -> OfflineBuffer:
    return OfflineBuffer(temp_db_path)


class TestOfflineBuffer:
    def test_init_creates_table(self, buffer: OfflineBuffer, temp_db_path: Path) -> None:
        assert temp_db_path.exists()
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='buffered_messages'"
            )
            assert cursor.fetchone() is not None

    def test_store_and_count(self, buffer: OfflineBuffer) -> None:
        assert buffer.count() == 0
        buffer.store("test/topic", {"val": 1})
        assert buffer.count() == 1
        buffer.store("test/topic", {"val": 2})
        assert buffer.count() == 2

    def test_drain_chronological_order(self, buffer: OfflineBuffer) -> None:
        # Store out of order timestamps, but they should be drained in chronological order
        buffer.store("topic1", {"id": 1}, timestamp=100.0)
        buffer.store("topic3", {"id": 3}, timestamp=300.0)
        buffer.store("topic2", {"id": 2}, timestamp=200.0)

        messages = buffer.drain(batch_size=10)
        assert len(messages) == 3
        
        assert messages[0].topic == "topic1"
        assert messages[0].payload["id"] == 1
        assert messages[0].timestamp == 100.0
        
        assert messages[1].topic == "topic2"
        assert messages[1].timestamp == 200.0
        
        assert messages[2].topic == "topic3"
        assert messages[2].timestamp == 300.0

    def test_drain_batch_size(self, buffer: OfflineBuffer) -> None:
        for i in range(5):
            buffer.store(f"topic{i}", {"val": i})
            
        messages = buffer.drain(batch_size=2)
        assert len(messages) == 2

    def test_ack_removes_messages(self, buffer: OfflineBuffer) -> None:
        buffer.store("test/topic", {"val": 1})
        buffer.store("test/topic", {"val": 2})
        
        messages = buffer.drain(batch_size=10)
        assert len(messages) == 2
        assert buffer.count() == 2
        
        # Ack only the first message
        buffer.ack([messages[0].id])
        
        assert buffer.count() == 1
        remaining = buffer.drain(batch_size=10)
        assert len(remaining) == 1
        assert remaining[0].payload["val"] == 2

    def test_purge_expired(self, buffer: OfflineBuffer, temp_db_path: Path) -> None:
        buffer.store("test/topic", {"val": 1})
        
        # Manually backdate the created_at field to 10 days ago
        ten_days_ago = time.time() - (10 * 24 * 3600)
        with sqlite3.connect(temp_db_path) as conn:
            conn.execute("UPDATE buffered_messages SET created_at = ?", (ten_days_ago,))
            
        buffer.store("test/topic", {"val": 2}) # This one is recent
        
        assert buffer.count() == 2
        
        deleted = buffer.purge_expired(max_age_days=7)
        assert deleted == 1
        assert buffer.count() == 1
        
        remaining = buffer.drain(batch_size=10)
        assert remaining[0].payload["val"] == 2

    def test_survives_restart(self, temp_db_path: Path) -> None:
        buf1 = OfflineBuffer(temp_db_path)
        buf1.store("test/topic", {"val": 1})
        assert buf1.count() == 1
        
        # Create a new instance pointing to same file (simulating restart)
        buf2 = OfflineBuffer(temp_db_path)
        assert buf2.count() == 1
        
        messages = buf2.drain(batch_size=10)
        assert len(messages) == 1
        assert messages[0].payload["val"] == 1
        
    def test_size_bytes(self, buffer: OfflineBuffer) -> None:
        size = buffer.size_bytes()
        assert size > 0
