# OI-28: Gateway Offline Storage Buffer Implementation

## Context
Implemented FR7 from the PRD: an offline storage buffer on the edge gateway to cache telemetry during network outages. The buffer must retain messages across process restarts and replay them chronologically on reconnect to prevent gaps in the cloud time-series data.

## Implementation Details
1. **SQLite Buffer (Decision 1):** Created `src/omniview/edge/offline_buffer.py` implementing `OfflineBuffer`. Used SQLite with WAL mode for concurrent read/write and transactional safety without external dependencies.
2. **Buffer Location (Decision 2):** Resides in the Edge layer as the gateway's responsibility. Stored by default at `data/offline_buffer.db`.
3. **Retention Policy (Decision 3):** Added config options `BUFFER_MAX_AGE_DAYS` (7 days), `BUFFER_MAX_SIZE_MB` (100MB), and `BUFFER_DRAIN_BATCH_SIZE` (50) to `config.py`. The buffer silently purges expired messages periodically.
4. **MQTT Client Integration:** Modified `OmniViewMQTTClient` in `src/omniview/edge/mqtt_client.py`:
   - `publish()` now intercepts messages when `is_connected == False` and stores them in the SQLite buffer instead of raising an error.
   - On reconnect (`_on_connect`), a background drain thread starts to batch-publish the stored messages in exact chronological order.
   - Successfully published messages are acknowledged (`ack()`) and removed from the buffer.
5. **Testing:**
   - Wrote comprehensive unit tests in `tests/test_offline_buffer.py` verifying ordered drain, purge, and restart survival.
   - Updated `tests/test_mqtt_client.py` to assert that disconnected publish calls are buffered rather than dropped.

## Output
- The edge gateway is now resilient against 4G network drops.
- Telemetry continuity is guaranteed for the downstream rule engine and TSDB.
