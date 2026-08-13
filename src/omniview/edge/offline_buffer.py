"""
Offline Buffer (OI-28)
======================

SQLite-based local buffer for offline telemetry resilience.
Implements FR7 from the PRD to ensure no data gaps during network outages.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class BufferedMessage(NamedTuple):
    """A message retrieved from the buffer."""
    id: int
    topic: str
    payload: dict[str, Any]
    timestamp: float


class OfflineBuffer:
    """Local SQLite buffer for telemetry data during network outages.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the table and indexes if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # We use WAL mode for better concurrency (reads don't block writes)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS buffered_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                )
                """
            )
            # Index on timestamp for chronological ordered drain
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_buffer_ts "
                "ON buffered_messages(timestamp)"
            )
            # Index on created_at for fast purging of old messages
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_buffer_created "
                "ON buffered_messages(created_at)"
            )

    def store(
        self, topic: str, payload: dict[str, Any], timestamp: float | None = None
    ) -> None:
        """Store a message in the buffer.

        Parameters
        ----------
        topic : str
            The MQTT topic.
        payload : dict
            The message payload. Must be JSON serializable.
        timestamp : float, optional
            The telemetry timestamp. Defaults to current time.
        """
        if timestamp is None:
            # Try to extract from payload, otherwise use current time
            timestamp = payload.get("timestamp", time.time())

        payload_str = json.dumps(payload, default=str)
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO buffered_messages (topic, payload, timestamp) "
                    "VALUES (?, ?, ?)",
                    (topic, payload_str, timestamp),
                )
        except Exception as e:
            logger.error("Failed to store message in buffer: %s", e)
            raise

    def drain(self, batch_size: int = 50) -> list[BufferedMessage]:
        """Retrieve the oldest N messages in chronological order.

        Parameters
        ----------
        batch_size : int
            Maximum number of messages to retrieve.

        Returns
        -------
        list[BufferedMessage]
            The oldest messages.
        """
        messages = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, topic, payload, timestamp 
                    FROM buffered_messages 
                    ORDER BY timestamp ASC 
                    LIMIT ?
                    """,
                    (batch_size,),
                )
                for row in cursor:
                    try:
                        payload = json.loads(row[2])
                        messages.append(
                            BufferedMessage(
                                id=row[0],
                                topic=row[1],
                                payload=payload,
                                timestamp=row[3],
                            )
                        )
                    except json.JSONDecodeError:
                        logger.error(
                            "Corrupted JSON in buffer for message ID %d. "
                            "It will be skipped but remains in buffer until purged.",
                            row[0]
                        )
        except Exception as e:
            logger.error("Failed to drain buffer: %s", e)
            
        return messages

    def ack(self, message_ids: list[int]) -> None:
        """Delete successfully published messages from the buffer.

        Parameters
        ----------
        message_ids : list[int]
            The IDs of the messages to delete.
        """
        if not message_ids:
            return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ",".join("?" * len(message_ids))
                conn.execute(
                    f"DELETE FROM buffered_messages WHERE id IN ({placeholders})",
                    message_ids,
                )
        except Exception as e:
            logger.error("Failed to ack messages %s: %s", message_ids, e)
            raise

    def purge_expired(self, max_age_days: int) -> int:
        """Remove messages older than the retention window.

        Parameters
        ----------
        max_age_days : int
            Maximum age of messages in days.

        Returns
        -------
        int
            Number of messages deleted.
        """
        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM buffered_messages WHERE created_at < ?",
                    (cutoff_time,),
                )
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info("Purged %d expired messages from buffer", deleted)
                return deleted
        except Exception as e:
            logger.error("Failed to purge expired messages: %s", e)
            return 0

    def count(self) -> int:
        """Get the current number of messages in the buffer."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM buffered_messages")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def size_bytes(self) -> int:
        """Get the size of the database file in bytes."""
        try:
            return self.db_path.stat().st_size
        except FileNotFoundError:
            return 0
