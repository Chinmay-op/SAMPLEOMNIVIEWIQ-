# OmniView IQ — Phase 3: Live Integration Test Report

**Test Run Date:** 2026-08-11  
**Start Time (IST):** 17:54  
**End Time (IST):** 18:10  
**Environment:** Windows 11, Docker Desktop, Python 3.14  
**Site:** `pune-isbm` | **Node:** `compressor-01`

---

## Summary Table

| # | Step | What it Proves | Result | Key Numbers |
|---|------|---------------|--------|-------------|
| 1 | `docker compose up -d` | Infrastructure boots and both containers reach healthy state | ✅ PASS | 2/2 containers healthy |
| 2 | `python -m omniview.ingest.migrations` | TimescaleDB schema is created correctly — all 7 sensor-family hypertables | ✅ PASS | 7/7 hypertables created |
| 3 | `python -m omniview.edge.smoke_test_mqtt` | MQTT broker round-trip works: connect → subscribe → publish → receive → disconnect | ✅ PASS | 5/5 checks passed |
| 4 | `python -m omniview.ingest.subscriber` | Subscriber starts, connects to MQTT and subscribes to wildcard topic | ✅ PASS | Subscribed to `omniview/pune-isbm/#` |
| 5 | `python -m omniview.edge.injector --synthetic --max 20 --burst` | Injector generates and publishes 20 synthetic electrical readings | ✅ PASS | 20/20 messages published |
| 6 | Subscriber output check | Subscriber receives all messages and inserts them into TimescaleDB with zero errors | ✅ PASS | received=20, inserted=20, duplicates=0, errors=0 |
| 7 | `SELECT count(*) FROM readings_electrical` | Data persisted correctly in TimescaleDB | ✅ PASS | 20 rows confirmed |

**Overall Verdict: ✅ ALL 7 STEPS PASSED**

---

## Data Flow Diagram

```
┌───────────────────┐       ┌──────────────────┐       ┌───────────────────┐       ┌────────────────────┐
│                   │       │                  │       │                   │       │                    │
│  Edge Injector    │──────▶│   Mosquitto      │──────▶│   Subscriber      │──────▶│   TimescaleDB      │
│  (omniview.edge.  │ MQTT  │   MQTT Broker    │ MQTT  │   (omniview.      │  SQL  │   (readings_       │
│   injector)       │ QoS 1 │   port 1883      │ push  │   ingest.         │ INSERT│    electrical)     │
│                   │       │                  │       │   subscriber)     │       │                    │
│  20 synthetic     │       │  topic:          │       │  Parse topic →    │       │  20 rows stored    │
│  electrical       │       │  omniview/       │       │  Extract data →   │       │  JSONB payload     │
│  readings         │       │  pune-isbm/      │       │  Insert reading   │       │  with unique       │
│                   │       │  compressor-01/  │       │                   │       │  (device_id, time) │
│                   │       │  electrical      │       │                   │       │                    │
└───────────────────┘       └──────────────────┘       └───────────────────┘       └────────────────────┘
```

---

## Step 1 — Docker Compose Up

**Command:** `docker compose up -d`

### Container Status Output
```
NAME                 STATUS                    PORTS
omniview-mosquitto   Up 16 seconds (healthy)   0.0.0.0:1883->1883/tcp, [::]:1883->1883/tcp,
                                               0.0.0.0:9001->9001/tcp, [::]:9001->9001/tcp
omniview-tsdb        Up 16 seconds (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
```

### Key Details
- **Mosquitto** (eclipse-mosquitto:2): Healthy, MQTT on port 1883, WebSocket on 9001
- **TimescaleDB** (timescale/timescaledb:latest-pg16): Healthy, PostgreSQL on port 5432
- Both containers reached `(healthy)` status within 16 seconds of startup
- Network `omniview-iq-poc_omniview-net` created as a bridge network
- Volumes created: `mosquitto_data`, `mosquitto_log`, `tsdb_data`

---

## Step 2 — Database Migrations

**Command:** `python -m omniview.ingest.migrations`

### Captured Output
```
2026-08-11 17:57:25,138  INFO      __main__  Running OI-54 migrations…
2026-08-11 17:57:25,538  INFO      omniview.ingest.db  Created TSDB engine → localhost:5432/omniview
2026-08-11 17:57:25,589  INFO      __main__  Connected to: PostgreSQL 16.14 on x86_64-pc-linux-musl,
                                              compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
2026-08-11 17:57:25,592  INFO      omniview.ingest.db  TimescaleDB extension ensured
2026-08-11 17:57:25,613  INFO      omniview.ingest.db  Created hypertable: readings_ambient (chunk=7 days)
2026-08-11 17:57:25,628  INFO      omniview.ingest.db  Created hypertable: readings_electrical (chunk=7 days)
2026-08-11 17:57:25,646  INFO      omniview.ingest.db  Created hypertable: readings_gas (chunk=7 days)
2026-08-11 17:57:25,664  INFO      omniview.ingest.db  Created hypertable: readings_pressure (chunk=7 days)
2026-08-11 17:57:25,681  INFO      omniview.ingest.db  Created hypertable: readings_stroke (chunk=7 days)
2026-08-11 17:57:25,697  INFO      omniview.ingest.db  Created hypertable: readings_thermal (chunk=7 days)
2026-08-11 17:57:25,712  INFO      omniview.ingest.db  Created hypertable: readings_vibration (chunk=7 days)
2026-08-11 17:57:25,716  INFO      omniview.ingest.db  Hypertable setup complete: 7 created, 0 already existed
2026-08-11 17:57:25,716  INFO      __main__  Migration complete — created tables: readings_ambient,
                                              readings_electrical, readings_gas, readings_pressure,
                                              readings_stroke, readings_thermal, readings_vibration
```

### 7 Hypertables Created

| # | Table Name | Sensor Family | Chunk Interval |
|---|-----------|---------------|----------------|
| 1 | `readings_ambient` | Shop floor temp + humidity (Schneider TH110) | 7 days |
| 2 | `readings_electrical` | kVA, kW, PF, THD, per-phase I/V (Selec MFM384) | 7 days |
| 3 | `readings_gas` | Micro-particle / overheating (Schneider HeatTag) | 7 days |
| 4 | `readings_pressure` | 0-40 bar pneumatic line (WIKA A-10) | 7 days |
| 5 | `readings_stroke` | Production cycle / OEE (Pulse counter) | 7 days |
| 6 | `readings_thermal` | Surface / barrel temp (RTD / Q45VT) | 7 days |
| 7 | `readings_vibration` | ISO 10816-3 RMS velocity (Banner Q45VT) | 7 days |

---

## Step 3 — MQTT Smoke Test

**Command:** `python -m omniview.edge.smoke_test_mqtt`

### Captured Output
```
============================================================
  OmniView IQ — MQTT Smoke Test
  Broker: localhost:1883
============================================================

1. Connecting to broker...
   ✅ Connected
2. Subscribing to omniview/pune-isbm/#
   ✅ Subscribed
3. Publishing to omniview/pune-isbm/compressor-01/electrical
   ✅ Published
4. Waiting for message round-trip...
   ✅ Message received and payload verified
5. Disconnecting...
   ✅ Disconnected

============================================================
  ✅  ALL CHECKS PASSED — MQTT path is working
============================================================
```

### Supporting Log Lines
```
2026-08-11 17:58:10,807  INFO  omniview.edge.mqtt_client  Connecting to MQTT broker at localhost:1883
                                                           (client_id=omniview-smoke-test)
2026-08-11 17:58:10,817  INFO  omniview.edge.mqtt_client  MQTT broker connection established
2026-08-11 17:58:10,817  INFO  omniview.edge.mqtt_client  MQTT connected successfully
2026-08-11 17:58:10,817  INFO  omniview.edge.mqtt_client  Subscribed to omniview/pune-isbm/# (qos=1)
2026-08-11 17:58:11,321  INFO  omniview.edge.mqtt_client  Disconnecting from MQTT broker
2026-08-11 17:58:12,323  INFO  omniview.edge.mqtt_client  MQTT disconnected cleanly
```

---

## Step 4 — Start Subscriber (Background)

**Command:** `python -m omniview.ingest.subscriber`

### Captured Output
```
2026-08-11 18:09:30,504  INFO  omniview.ingest.migrations  Running OI-54 migrations…
2026-08-11 18:09:30,542  INFO  omniview.ingest.db  Created TSDB engine → localhost:5432/omniview
2026-08-11 18:09:30,577  INFO  omniview.ingest.migrations  Connected to: PostgreSQL 16.14 on
                                x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
2026-08-11 18:09:30,580  INFO  omniview.ingest.db  TimescaleDB extension ensured
2026-08-11 18:09:30,613  INFO  omniview.ingest.db  Hypertable setup complete: 0 created, 7 already existed
2026-08-11 18:09:30,613  INFO  omniview.ingest.migrations  Migration complete — all tables already existed
2026-08-11 18:09:30,613  INFO  __main__  Starting MQTT→TSDB subscriber for site 'pune-isbm'
2026-08-11 18:09:30,613  INFO  __main__  Subscribing to: omniview/pune-isbm/#
2026-08-11 18:09:30,613  INFO  omniview.edge.mqtt_client  Connecting to MQTT broker at localhost:1883
                                                           (client_id=omniview-subscriber-01)
2026-08-11 18:09:30,637  INFO  omniview.edge.mqtt_client  MQTT broker connection established
2026-08-11 18:09:30,637  INFO  omniview.edge.mqtt_client  MQTT connected successfully
2026-08-11 18:09:30,638  INFO  omniview.edge.mqtt_client  Subscribed to omniview/pune-isbm/# (qos=1)
2026-08-11 18:09:30,638  INFO  __main__  Subscriber running — press Ctrl+C to stop
```

---

## Step 5 — Injector: 20 Synthetic Readings

**Command:** `python -m omniview.edge.injector --synthetic --max 20 --burst`

### Captured Output
```
2026-08-11 18:09:58,061  INFO  omniview.edge.mqtt_client  Connecting to MQTT broker at localhost:1883
                                                           (client_id=omniview-injector-01)
2026-08-11 18:09:58,069  INFO  omniview.edge.mqtt_client  MQTT broker connection established
2026-08-11 18:09:58,069  INFO  omniview.edge.mqtt_client  MQTT connected successfully
2026-08-11 18:09:58,069  INFO  __main__  Starting synthetic replay →
                                omniview/pune-isbm/compressor-01/electrical
                                (interval=15.0s, speed=1.0x, max=20)
2026-08-11 18:09:58,069  INFO  __main__  [1] Published →
                                omniview/pune-isbm/compressor-01/electrical |
                                kVA=323.829 kW=272.768 PF=0.8423
2026-08-11 18:09:58,073  INFO  __main__  Synthetic replay finished: 20 messages published
2026-08-11 18:09:58,073  INFO  omniview.edge.mqtt_client  Disconnecting from MQTT broker
2026-08-11 18:09:58,118  INFO  omniview.edge.mqtt_client  MQTT disconnected cleanly
```

**Time to publish 20 messages (burst):** ~4ms (18:09:58,069 → 18:09:58,073)

---

## Step 6 — Subscriber Final Counts

### Captured Output
```
2026-08-11 18:10:00,643  INFO  __main__  Subscriber stats: received=20 inserted=20 duplicates=0 errors=0 skipped=0
2026-08-11 18:10:30,653  INFO  __main__  Subscriber stats: received=20 inserted=20 duplicates=0 errors=0 skipped=0
```

### Final Counters

| Metric | Expected | Actual | Match |
|--------|----------|--------|-------|
| Received | 20 | **20** | ✅ |
| Inserted | 20 | **20** | ✅ |
| Duplicates | 0 | **0** | ✅ |
| Errors | 0 | **0** | ✅ |
| Skipped (system) | 0 | **0** | ✅ |

---

## Step 7 — TimescaleDB Row Count Verification

**Command:** `SELECT count(*) FROM readings_electrical;`

### Captured Output
```
 count
-------
    20
(1 row)
```

**Result:** 20 rows confirmed in `readings_electrical` — matches exactly the 20 injected readings.

---

## Bug Found & Fixed During Testing

> **Issue:** SQLAlchemy parameter binding conflict in `db.py`
>
> The SQL statement used `:data::jsonb` which is ambiguous — SQLAlchemy
> interprets `:data` as a named parameter, but PostgreSQL's `::` cast operator
> creates a parsing conflict. The subscriber received all 20 messages but
> failed to insert any of them (errors=20) on the first attempt.
>
> **Fix applied:** Changed `:data::jsonb` to `CAST(:data AS jsonb)` in both
> `insert_reading()` and `insert_readings_batch()` functions in
> `src/omniview/ingest/db.py`.
>
> **Verification:** After the fix, the re-run produced a clean
> received=20, inserted=20, errors=0 result.

---

## What This Test Proves

This Phase 3 integration test proves that the OmniView IQ data pipeline works end-to-end as a connected system, not just as isolated components. Starting from raw sensor readings generated at the edge, data travels through the MQTT message broker (Mosquitto), gets picked up by the subscriber bridge service, and lands correctly in the TimescaleDB time-series database — all with zero data loss.

Specifically, this test demonstrates that:

1. **Infrastructure is reliable.** Both Docker containers (Mosquitto and TimescaleDB) boot to a healthy state and stay stable throughout the test.
2. **The database schema is sound.** All 7 sensor-family hypertables are created idempotently, meaning the system is safe to restart without breaking anything.
3. **The MQTT path works.** Messages published to the broker are received back by subscribers within milliseconds, confirming the message bus is functioning correctly.
4. **The full pipeline delivers data without loss.** 20 synthetic electrical readings were injected, all 20 were received by the subscriber, all 20 were inserted into TimescaleDB, and a direct database query confirmed all 20 rows exist. Zero duplicates, zero errors.
5. **The system handles concurrent processes correctly.** The subscriber and injector ran as separate processes with distinct MQTT client identities, proving the architecture supports the multi-process deployment model described in the PRD.

For a tech lead: this means the Day-1 data collection pipeline is ready for integration with the real Modbus hardware polling layer (OI-8). The synthetic data generator can continue to serve as a testing and demo tool while hardware comes online.

---

*Report generated: 2026-08-11T18:10:00+05:30*  
*Test executed by: Antigravity Agent*  
*Project: OmniView IQ POC (omniview-iq-poc)*
