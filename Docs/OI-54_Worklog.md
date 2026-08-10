# OI-54 — TimescaleDB Hypertables: Session Worklog

**Date:** 10 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Ticket:** [OI-54](https://mightium.atlassian.net/browse/OI-54)  
**Branch:** `chinmay`  
**Depends on:** OI-41 (scaffold) ✅, OI-51 (MQTT topics) ✅

---

## What Was the Task?

The `ingest/db.py` stub from OI-41 only had placeholder docstrings — no database logic. The goal was to implement the full TimescaleDB storage layer: connection pool, hypertable DDL for all 7 sensor families, idempotent upsert inserts, and an MQTT→TSDB subscriber bridge.

**Acceptance Criteria (all met ✅):**

- [x] 7 hypertables created (one per sensor family)
- [x] Idempotent inserts via `ON CONFLICT DO NOTHING`
- [x] MQTT→TSDB subscriber bridge as standalone process
- [x] Migration runner safe to call on every startup
- [x] Unit tests (20 new tests, all passing)
- [x] Zero regressions (51/51 total tests pass)

---

## What Was Built

### 1. `src/omniview/ingest/db.py` — Database Core

Full implementation replacing the OI-41 stub:

| Function | Purpose |
|----------|---------|
| `get_engine()` | Singleton SQLAlchemy engine with connection pooling (pool_size=5, max_overflow=10) |
| `reset_engine()` | Dispose engine for testing/shutdown |
| `ensure_timescaledb()` | Idempotent `CREATE EXTENSION IF NOT EXISTS timescaledb` |
| `create_hypertables()` | Creates 7 tables with hypertable conversion, GIN indexes |
| `insert_reading()` | Single-row idempotent upsert, returns True/False |
| `insert_readings_batch()` | Bulk idempotent upsert, returns count of inserted rows |
| `query_latest()` | Fetch most recent N readings for a device |

**Hypertable schema (same for all 7 tables):**
```sql
CREATE TABLE IF NOT EXISTS readings_{sensor_type} (
    time            TIMESTAMPTZ     NOT NULL,
    device_id       TEXT            NOT NULL,
    site_id         TEXT            NOT NULL,
    sensor_type     TEXT            NOT NULL DEFAULT '{sensor_type}',
    schema_version  TEXT            NOT NULL DEFAULT '1.0',
    data            JSONB           NOT NULL,
    UNIQUE (device_id, time)
);
```

**Tables:** `readings_electrical`, `readings_vibration`, `readings_thermal`, `readings_pressure`, `readings_gas`, `readings_stroke`, `readings_ambient`

### 2. `src/omniview/ingest/migrations.py` — Migration Runner

Lightweight startup migration:
- Verifies TimescaleDB connectivity
- Ensures the `timescaledb` extension
- Creates all 7 hypertables (skips existing)
- Runnable as `python -m omniview.ingest.migrations`

### 3. `src/omniview/ingest/subscriber.py` — MQTT→TSDB Bridge

Long-lived process that subscribes to `omniview/{site_id}/#` and writes every sensor payload to the correct hypertable:

- Parses topic → sensor_type + device_id + site_id
- Extracts timestamp (supports ISO 8601, Unix epoch, or arrival-time fallback)
- Calls `insert_reading()` for each message
- System topics (`_status`, `_alerts`) silently skipped
- Malformed payloads logged and skipped — never crashes
- Graceful shutdown via SIGINT/SIGTERM
- Periodic stats logging (received/inserted/duplicates/errors)
- Runnable as `python -m omniview.ingest.subscriber`

### 4. Config Updates

- `config.py`: Added `TSDB_CHUNK_INTERVAL` (defaults to `"7 days"`)
- `.env.example`: Documented the new env var

### 5. `ingest/__init__.py` — Updated Public API

Exports: `get_engine`, `create_hypertables`, `insert_reading`, `insert_readings_batch`, `query_latest`, `run_migrations`

---

## Files Created/Modified (8 total)

```
 MOD  src/omniview/config.py             — Added TSDB_CHUNK_INTERVAL
 MOD  .env.example                       — Documented chunk interval
 MOD  src/omniview/ingest/__init__.py     — Public imports
 MOD  src/omniview/ingest/db.py           — Full implementation (was stub)
 NEW  src/omniview/ingest/migrations.py   — Idempotent migration runner
 NEW  src/omniview/ingest/subscriber.py   — MQTT→TSDB bridge
 NEW  tests/test_db.py                    — 12 unit tests
 NEW  tests/test_subscriber.py            — 8 unit tests
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_db.py -v` | ✅ 12/12 passed |
| `pytest tests/test_subscriber.py -v` | ✅ 8/8 passed |
| `pytest tests/ -v` (full suite) | ✅ 51/51 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.ingest import get_engine, insert_reading, run_migrations` |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| One table per sensor family | Each family has different JSONB shapes. Keeps queries fast (scan only electrical for MD rules). Matches DevB's 7-schema contract. |
| JSONB `data` column | Sensor schemas still evolving (DevB OI-23/5/6/7). Avoids migration on every schema change. Rule engine extracts fields via `data->>'kva'`. |
| `ON CONFLICT DO NOTHING` | QoS 1 duplicates silently dropped. Same `(device_id, time)` is always identical content. |
| Default 7-day chunk interval | TimescaleDB default — adequate for POC data volume (~8k rows/day per node). |
| No Alembic | 7 tables, POC scope, idempotent DDL — simple Python function is cleaner. |
| Standalone subscriber process | Decouples ingest from edge/injector. Can scale or restart independently. |
| GIN index on JSONB | Enables efficient queries like `data->>'kva' > 450` for rule engine and dashboard. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-12 | CSV→MQTT electrical injector | MQTT ✅ + TSDB ✅ |
| **Chinmay** | OI-55 | Payload validation + Day-1 seed script | TSDB ✅ |
| **Chinmay** | OI-68 | Live dashboard (queries `readings_*` tables) | TSDB ✅ |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert rule | TSDB ✅ (reads `readings_electrical`) |

---

*Session completed: 10 August 2026, 12:35 PM IST*
