# OI-55 — Seed Script: Load Day-1 Hybrid Datasets into TSDB: Session Worklog

**Date:** 19 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Epic:** [OI-34](https://mightium.atlassian.net/browse/OI-34) (Cloud / TSDB)  
**Branch:** `chinmay`  
**Depends on:** OI-54 (hypertables) ✅, OI-15 (idempotent inserts) ✅, OI-52 (edge config) ✅

---

## What Was the Task?

The POC needed a **one-command way** to populate TimescaleDB with a demo-ready dataset — without running 7 bots, MQTT, or live hardware. The dashboard (OI-68), rule engine (OI-56), and PdM module (OI-62) all need queryable time-series data from Day 1.

**Acceptance Criteria (all met ✅):**

- [x] One command seeds demo dataset (`python -m omniview.ingest.seed`)
- [x] Dashboard/rules can query seeded data (same `readings_*` hypertables)
- [x] Real electrical + public/dummy streams (uses DevB bot generators)
- [x] Injected scenarios (MD near-miss, lazy-idle, leak proxy)
- [x] Idempotent re-runnable (ON CONFLICT DO NOTHING)

---

## What Was Built

### 1. `src/omniview/ingest/seed.py` — Day-1 Seed Script

| Component | Purpose |
|-----------|---------|
| `SeedResult` / `FamilySeedResult` | Result dataclasses with per-family counts and summary() |
| `generate_timeline()` | Generates chronological readings for one device using DevB bots |
| `seed_sensor_family()` | Seeds one sensor type across all devices via `backfill_insert()` |
| `seed_all()` | Main entry point — seeds all 7 families with scenario injection |
| CLI (`__main__`) | `--hours`, `--start`, `--no-scenarios`, `--families`, `--dry-run` |

**Device coverage (from edge_nodes.json):**

| Node | device_id | sensor_type | poll_interval_s | Readings/24h |
|------|-----------|-------------|:---:|:---:|
| compressor-01 | `pune-comp-mfm384` | electrical | 15 | 5,760 |
| compressor-01 | `pune-comp-vib01` | vibration | 60 | 1,440 |
| compressor-01 | `pune-comp-wika01` | pressure | 60 | 1,440 |
| compressor-01 | `pune-comp-therm01` | thermal | 60 | 1,440 |
| compressor-01 | `pune-comp-gas01` | gas | 60 | 1,440 |
| isbm-01 | `pune-isbm-mfm384` | electrical | 15 | 5,760 |
| isbm-01 | `pune-isbm-therm01` | thermal | 60 | 1,440 |
| isbm-01 | `pune-isbm-stroke01` | stroke | 15 | 5,760 |
| floor | `pune-floor-ambient01` | ambient | 60 | 1,440 |
| | | | **Total** | **25,920** |

**Scenario injection (3 labeled scenarios):**

| Scenario | Time window | Device | What changes | Label |
|----------|-------------|--------|--------------|-------|
| MD near-miss | 10:15–10:45 | All electrical | kVA ramps 350→480→350 | `md_nearmiss` |
| Lazy-idle | 14:00–14:20 | ISBM electrical + thermal | Current drops, barrel temp stays high | `lazy_idle` |
| Leak proxy | 16:00–16:10 | Compressor pressure | Pressure decays 33→22 bar | `leak_proxy` |

Each injected reading gets a `"scenario_label"` key in the `data` JSONB for testability.

---

## Files Created/Modified (3 total)

```
 NEW  src/omniview/ingest/seed.py            — Day-1 seed script (396 lines)
 MOD  src/omniview/ingest/__init__.py        — Export seed_all, SeedResult
 NEW  tests/test_seed.py                     — 36 unit tests
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_seed.py -v` | ✅ 36/36 passed |
| `pytest tests/ -v` (full suite) | ✅ 304/304 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.ingest import seed_all, SeedResult` |
| 24h reading count verified | ✅ 25,920 total readings (matches expected) |
| Scenario labels verified | ✅ md_nearmiss, lazy_idle, leak_proxy present at correct times |
| Dry run mode | ✅ Generates without DB writes |
| Device mapping from edge_nodes.json | ✅ All 9 devices, 3 nodes, 7 families |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| **Direct `backfill_insert()` — no MQTT** | Seed bypasses the edge→MQTT→subscriber pipeline. Goes straight to TSDB. Faster, simpler, no broker dependency for seeding. |
| **DevB bot generators for data** | Reuses existing `generate_reading()` functions. Same data shapes the live system will produce — no divergence between seed and real. |
| **Device manifest from edge_nodes.json** | Uses OI-52's `load_edge_config()` for device_id, poll_interval_s, and node mapping. Single source of truth — adding a device to the config auto-includes it in seed. |
| **Scenario injection as data overrides** | Scenarios modify the bot's base output rather than generating from scratch. Keeps all non-scenario fields realistic. |
| **`scenario_label` in data JSONB** | Enables `data->>'scenario_label' = 'md_nearmiss'` queries for rule testing. Doesn't add columns or change schema. |
| **Bell curve kVA ramp (sin)** | MD near-miss peaks at the midpoint of the window — more realistic than a step function. Creates a smooth trajectory the rolling kVA rule (OI-56) can detect. |
| **CLI with `--dry-run`** | Allows generation + counting without a DB. Useful for CI, development, and quick verification. |
| **IST timezone default** | The Pune site operates in IST. All timestamps are timezone-aware. Matches MSEDCL billing window alignment. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-68 | Live dashboard | Seeded data available for time-series charts ✅ |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert rule | Seeded electrical data with MD scenario ✅ |
| **Dnyandev** | OI-57 | Lazy-idle detection rule | Seeded ISBM data with lazy_idle scenario ✅ |
| **Dnyandev** | OI-58 | Pressure-decay leak proxy rule | Seeded compressor data with leak_proxy scenario ✅ |

---

*Session completed: 19 August 2026, 12:07 PM IST*
