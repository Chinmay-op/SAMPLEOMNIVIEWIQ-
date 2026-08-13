# Chinmay DevC — Technical Decisions Log

**Developer:** Chinmay Wadettiwar (DevC — Platform / Edge / Cloud / UI)  
**Sprint:** OI Sprint 1  
**Date Range:** 5 Aug – 10 Aug 2026  
**Branch:** `chinmay`

---

## Summary

This document records all significant technical decisions made across the 4 completed tasks in Sprint 1.
Each decision includes the reasoning, alternatives considered, and impact on downstream work.

---

## OI-41 — Scaffold Repo + Docker Compose (1.5 SP)

### What We Did
Created the entire runnable project foundation from scratch — Python package (`src/omniview/`), Docker Compose (Mosquitto + TimescaleDB), `.env.example`, `requirements.txt`, `pyproject.toml`, README, and `.gitignore`. Before this, the repo was just docs and notebooks.

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **Used `pyproject.toml` instead of `setup.py`** | Python 3.14 deprecated `setup.py develop`. Using `pyproject.toml` is the modern PEP 621 standard and future-proofs the project. |
| 2 | **Package layout mirrors the 6-layer architecture** | Makes it obvious where code belongs — Dnyandev's rule engine goes in `rules/`, Vibhanshu's schemas feed `edge/` and `ingest/`. Reduces onboarding time. |
| 3 | **Mosquitto set to anonymous access** | This is a POC. Adding auth + TLS adds complexity without value at this stage. Noted in config comments for production hardening. |
| 4 | **Centralised config in `config.py`** | Single source of truth. Every module imports from here instead of calling `os.getenv()` directly. Prevents scattered env-var handling and makes testing easier. |
| 5 | **Named Docker volumes for Mosquitto + TimescaleDB** | Data persists across `docker compose down/up` cycles — no accidental data loss during development. |
| 6 | **Health checks on both containers** | Downstream scripts (e.g. migrations, subscriber) can depend on services being genuinely ready, not just "container started". |
| 7 | **Shared Docker network (`omniview-net`)** | Containers talk to each other by service name. Essential for subscriber→TSDB and injector→Mosquitto connectivity. |
| 8 | **Placeholder docstrings in every stub module** | Each stub explains what will go there, which Jira ticket fills it, and key PRD notes. Team members know what to build without reading docs separately. |

---

## OI-51 — MQTT Topics + Mosquitto Client (1.0 SP)

### What We Did
Built 3 modules: `topics.py` (canonical topic hierarchy + parser), `node_registry.py` (device→sensor map for the Pune POC), and `mqtt_client.py` (production-grade paho-mqtt v2 wrapper with auto-reconnect). Also created a smoke test script for live broker verification.

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **4-segment topic pattern: `omniview/{site_id}/{node_id}/{sensor_type}`** | Clean, predictable hierarchy. Downstream consumers (subscriber, rules, dashboard) can wildcard-subscribe at any level. Matches PRD node structure. |
| 2 | **System topics use `_status` and `_alerts` prefixes** | Underscored segments prevent collision with sensor types. Subscriber silently skips these — they're consumed by different processes. |
| 3 | **`SENSOR_TYPES` as `frozenset`** | Immutable by design — no one can accidentally mutate the canonical sensor list at runtime. Used for validation in `build_topic()`. |
| 4 | **QoS 1 (at-least-once) as default** | Matches FR7's no-data-loss requirement. Duplicates are harmless because OI-54's TSDB insert layer uses `ON CONFLICT DO NOTHING`. Together this gives effectively-exactly-once semantics. |
| 5 | **paho-mqtt v2 with `CallbackAPIVersion.VERSION2`** | Forward-compatible. v1 callback signature is deprecated. |
| 6 | **MQTTv5 protocol** | Supports reason codes, shared subscriptions, and flow control properties. Future-proof for production scaling. |
| 7 | **Exponential backoff on disconnect** | Prevents thundering-herd reconnect storms if the broker goes down and multiple clients try to reconnect simultaneously. Caps at 60s. |
| 8 | **Context manager support (`with` statement)** | Guarantees clean disconnect even if exceptions occur mid-publish. Prevents zombie MQTT connections. |
| 9 | **Wildcard-matched callback routing** | `_on_message` matches incoming topics against all registered subscription filters (including `+` and `#` wildcards). One client can have multiple filtered callbacks. |
| 10 | **Smoke test as standalone script** | Quick live verification: `python -m omniview.edge.smoke_test_mqtt`. Tests connect → subscribe → publish → round-trip → disconnect. No pytest fixtures needed — just Docker. |
| 11 | **Node registry with `poll_intervals`** | Each node defines its own sensor polling cadence (15s electrical, 60s physical). The poller module (OI-13, future) reads from here instead of hardcoding. |

---

## OI-54 — TimescaleDB Hypertables + MQTT→TSDB Subscriber (1.5 SP)

### What We Did
Implemented the full cloud ingest layer: `db.py` (connection pool, 7 hypertables DDL, idempotent upsert, batch insert, latest-query), `migrations.py` (safe startup runner), and `subscriber.py` (long-lived MQTT→TSDB bridge process).

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **One hypertable per sensor family (7 tables)** | Each family has different JSONB shapes. Keeps queries fast — e.g. MD rule engine only scans `readings_electrical`, not all sensor data. Matches DevB's 7-schema contract. |
| 2 | **JSONB `data` column instead of typed columns** | Sensor schemas are still evolving (DevB OI-23/5/6/7). JSONB avoids a migration every time a schema field is added/removed. Rule engine and dashboard extract fields via `data->>'kva'`. |
| 3 | **`ON CONFLICT (device_id, time) DO NOTHING`** | QoS 1 duplicates are silently dropped. Same `(device_id, time)` pair always has identical content, so "do nothing" is safe. |
| 4 | **7-day chunk interval** | TimescaleDB default. Adequate for POC data volume (~8k rows/day per node). Optimizes partition pruning for time-range queries. |
| 5 | **No Alembic migration framework** | Only 7 tables, POC scope, all DDL is idempotent. A simple Python function is cleaner and has zero learning curve for the team. |
| 6 | **Standalone subscriber process** | Decouples ingest from edge/injector. Can be scaled or restarted independently. One subscriber per site — subscribes to `omniview/{site_id}/#`. |
| 7 | **GIN index on JSONB `data` column** | Enables efficient queries like `data->>'kva' > 450` for the rule engine and dashboard. Without this, every query would full-scan the JSONB blob. |
| 8 | **Arrival-time fallback for timestamp parsing** | If a payload lacks a parseable timestamp, we use the arrival time. This prevents data loss from malformed messages — better to have approximate time than no record. |
| 9 | **System topics (`_status`, `_alerts`) silently skipped** | Subscriber only writes sensor data. Alert and status topics are consumed by other processes. No error logging for expected topic types. |
| 10 | **Periodic stats logging** | Subscriber logs received/inserted/duplicates/errors periodically. Essential for debugging ingest pipelines without being overwhelmed by per-message logs. |

---

## OI-12 — CSV→MQTT Electrical Injector (2.0 SP)

### What We Did
Built a full CSV→MQTT replay injector with built-in synthetic data generation. Reads electrical CSVs (auto-detecting column names), or generates realistic factory load profiles, and publishes them as schema-valid JSON payloads to MQTT. Includes CLI, speed control, burst mode, looping.

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **Auto-detect CSV columns via 80+ alias map** | DevB's OI-8 format isn't finalized yet. Also handles UCI Steel Industry dataset columns, legacy formats, etc. Makes the injector tolerant of different CSV sources. |
| 2 | **Built-in synthetic generator (no external deps)** | DevB OI-8 hasn't shipped yet. We can demo the full Day-1 pipeline (inject → MQTT → subscriber → TSDB) independently. Zero external data dependency. |
| 3 | **Deterministic RNG (`seed=42`)** | Same synthetic data on every run. Enables reproducible tests, reproducible demos, and reproducible debugging. |
| 4 | **MD near-miss spikes every ~400 readings** | Gives Dnyandev's OI-56 rule engine realistic test data with near-miss events roughly every 100 minutes (at 15s intervals). The rule engine needs these to trigger. |
| 5 | **Physically derived parameters (kVA→PF→kW→kVAR→I→V chain)** | Ensures consistency. Dashboard won't show impossible combinations like kW > kVA or PF > 1.0. Each value is mathematically derived from the base kVA. |
| 6 | **Burst mode** | Enables fast TSDB seeding. Combined with subscriber (OI-54), can populate weeks of historical data in seconds. Critical for dashboard development. |
| 7 | **23 canonical field names matching Selec MFM384 Modbus register map** | When we switch from CSV replay to live Modbus polling (OI-13), the field names stay the same. No downstream code changes needed. |
| 8 | **CLI matching README documentation exactly** | Users (and CI) can run exactly the commands documented in the README. No guessing or README/code drift. |

---

## OI-14 — Payload Validation + Schema Versioning (1.0 SP)

### What We Did
Integrated a validation layer (`validation.py`) into the cloud ingest pipeline. The subscriber now checks incoming MQTT JSON payloads against standard JSON schemas using the `jsonschema` library before inserting them into TimescaleDB.

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **Added `jsonschema` as a dependency** | Industry standard for JSON Schema validation. DevB is authoring standard JSON schemas (OI-23), so native schema validation is the cleanest approach. |
| 2 | **Validation drops invalid payloads** | Rather than inserting them into a dead-letter table or flagging them as `is_valid=False`, we simply drop them and log a `validation_failures` metric. Keeps TSDB clean and simplifies the rule engine queries. |
| 3 | **Bypass validation for undefined schemas** | While waiting for DevB to finalize schemas for all 7 sensor types, we only validate `electrical` (using a local placeholder). Other types return `True` by default, unblocking parallel dev without breaking the pipeline. |

---

## OI-28 — Gateway Offline Storage Buffer Implementation (2.0 SP)

### What We Did
Implemented FR7 from the PRD. Added an offline storage buffer (`offline_buffer.py`) using SQLite to cache telemetry locally on the edge gateway when the 4G network drops. Integrated this into `OmniViewMQTTClient` so that it intercepts publish calls during outages and chronologically replays the buffered messages in a background thread upon reconnection.

### Decisions

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | **Used SQLite over append files** | SQLite natively supports transactional safety (ACID) and chronological `ORDER BY` drains. It's built into Python, avoiding external dependencies, and handles process crashes gracefully. |
| 2 | **Buffer is an Edge Layer responsibility** | The buffer lives in `src/omniview/edge/offline_buffer.py`. The cloud TSDB ingest logic (`subscriber.py`) doesn't need to know the buffer exists; it just receives chronological messages. |
| 3 | **7-day / 100MB retention limit** | Prevents the gateway's flash storage from filling up. 7 days matches the TSDB chunk interval and is more than enough for a 3-week POC. |
| 4 | **Drain batching with sleep delay** | Prevents flooding the Mosquitto broker on reconnect. Messages are drained in batches of 50 with a 0.1s pause between batches. |

---

## Cross-Cutting Decisions (All Tasks)

| Decision | Reasoning |
|----------|-----------|
| **All stubs include Jira ticket references** | Any team member reading the code knows exactly which ticket owns that module. Reduces context-switching. |
| **Unit tests for every module** | 79 total tests (28 injector + 20 db/subscriber + 31 topics/mqtt_client). Every new module ships with tests. CI green gate. |
| **Python logging (no `print()`)** | Structured, level-filtered logging. Production can set `WARNING`, development uses `DEBUG`. No print-statement cleanup needed later. |
| **Everything importable from package root** | `from omniview.edge import ElectricalInjector` works. Clean public API via `__init__.py` exports. |
| **Config via `.env` + `config.py`** | 12-factor app pattern. Environment-specific values (broker host, TSDB password) stay in `.env`, defaults in `config.py`. No hardcoded connection strings. |

---

*Last updated: 11 August 2026*
