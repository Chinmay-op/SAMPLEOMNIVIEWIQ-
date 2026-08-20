# OI-15 — Time-Series Database Insertion Logic (Idempotent): Session Worklog

**Date:** 15 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Ticket:** [OI-15](https://mightium.atlassian.net/browse/OI-15)  
**Branch:** `chinmay`  
**Depends on:** OI-54 (hypertable migrations) ✅, OI-14 (payload validation) ✅

---

## What Was the Task?

OI-54 built the foundational TimescaleDB layer (hypertables, basic inserts, subscriber). OI-15 extends that with production-grade idempotent insertion logic specifically designed for chronological backfill scenarios (offline buffer drain, historical import) and adds the missing time-range query capability.

**Acceptance Criteria (all met ✅):**

- [x] Inserts succeed for each sensor schema (all 7 families tested)
- [x] Replayed backfill does not duplicate rows (ON CONFLICT DO NOTHING + dedicated test)
- [x] Queryable by device_id + time range
- [x] Unit tests (27 new tests, all passing)
- [x] Zero regressions (134/134 total tests pass)

---

## What Was Built

### 1. `src/omniview/ingest/db.py` — Enhanced (OI-15 additions)

| Function / Class | Purpose |
|------------------|---------|
| `BackfillResult` | Dataclass tracking backfill counts: `total`, `inserted`, `duplicates`, `sensor_type`, `.is_clean` property |
| `backfill_insert()` | Chronological backfill with chunked multi-value INSERT (100 rows/chunk), `ON CONFLICT DO NOTHING` |
| `query_by_time_range()` | Fetch readings for `device_id` within `[start, end]` time window, ordered ASC |
| `_chunked()` | Internal helper: yields list slices of configurable size |
| `insert_readings_batch()` | **Refactored** from row-by-row loop to multi-value INSERT for performance |

### 2. `src/omniview/ingest/tsdb_inserter.py` — NEW

High-level `TSDBInserter` facade class:

| Feature | Detail |
|---------|--------|
| `insert()` | Single reading insert with per-family metrics tracking |
| `backfill()` | Backfill insert with metrics tracking |
| `query_range()` | Time-range query wrapper |
| `query_latest()` | Latest-N query wrapper |
| `.metrics` | Per-sensor-family counters (inserts, duplicates, errors) |
| `.total_inserts` / `.total_duplicates` / `.total_errors` | Aggregated properties |
| Thread-safe | All metrics protected by `threading.Lock` |

### 3. `src/omniview/ingest/__init__.py` — Updated Public API

Exports: `BackfillResult`, `TSDBInserter`, `backfill_insert`, `query_by_time_range` (added to existing exports).

### 4. `tests/test_tsdb_inserter.py` — NEW (27 tests)

| Test Class | Tests | What It Verifies |
|------------|-------|------------------|
| `TestInsertAllFamilies` | 7 (parametrized) | Insert succeeds for each of the 7 sensor schemas |
| `TestBackfillIdempotency` | 3 | First insert (all new), replayed backfill (all dups), partial overlap |
| `TestBackfillEdgeCases` | 3 | Empty input, unknown sensor type, chunking with 250 readings |
| `TestBackfillResult` | 3 | Dataclass defaults, `is_clean` property logic |
| `TestQueryByTimeRange` | 4 | Returns rows, rejects unknown type, rejects inverted range, empty result |
| `TestTSDBInserter` | 6 | Metrics tracking, duplicate counting, family isolation, backfill metrics |
| `TestInsertReadingsBatchOptimized` | 1 | Multi-value INSERT verified (single SQL call) |

---

## Files Created/Modified (5 total)

```
 MOD  src/omniview/ingest/db.py              — BackfillResult, backfill_insert, query_by_time_range, optimized batch
 NEW  src/omniview/ingest/tsdb_inserter.py    — TSDBInserter facade with per-family metrics
 MOD  src/omniview/ingest/__init__.py         — Export new public API
 NEW  tests/test_tsdb_inserter.py             — 27 unit tests
 MOD  tests/test_db.py                        — Updated batch test for multi-value INSERT
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_tsdb_inserter.py -v` | ✅ 27/27 passed |
| `pytest tests/test_db.py -v` | ✅ 12/12 passed (0 regressions) |
| `pytest tests/ -v` (full suite) | ✅ 134/134 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.ingest import TSDBInserter, backfill_insert, query_by_time_range, BackfillResult` |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| Chunked multi-value INSERT (100 rows/chunk) | Single SQL statement per chunk reduces round-trips vs row-by-row. 100 is a safe default — PostgreSQL handles it well without exceeding parameter limits. |
| `BackfillResult` dataclass | Structured return type gives callers full visibility into what happened (vs just a count). The `.is_clean` property is useful for monitoring/alerting. |
| Separate `backfill_insert()` from `insert_readings_batch()` | `backfill_insert` returns `BackfillResult` (richer info, designed for offline buffer drain). `insert_readings_batch` returns plain `int` (simpler, for general batch use). |
| `query_by_time_range()` returns ASC order | Rule engine (OI-56) needs chronological order for rolling kVA windows. Dashboard needs it for time-series charts. ASC is the natural reading order. |
| `TSDBInserter` as facade class | Clean API for subscriber and future consumers. Per-family metrics tracking makes observability trivial. Thread-safe for concurrent ingest. |
| `start > end` raises ValueError | Fail fast on inverted ranges rather than silently returning empty results. Helps catch bugs in the rule engine's window arithmetic. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-55 | Day-1 seed script | Backfill insert ✅ |
| **Chinmay** | OI-68 | Live dashboard (time-range queries) | `query_by_time_range` ✅ |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert rule | `query_by_time_range` ✅ |
| **Chinmay** | OI-29 | Backfill reliability (uses `BackfillResult`) | `backfill_insert` ✅ |

---

*Session completed: 15 August 2026, 10:47 AM IST*
