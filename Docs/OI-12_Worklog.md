# OI-12 — CSV→MQTT Electrical Injector: Session Worklog

**Date:** 10 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Ticket:** [OI-12](https://mightium.atlassian.net/browse/OI-12)  
**Branch:** `chinmay`  
**Depends on:** OI-41 (scaffold) ✅, OI-51 (MQTT topics + client) ✅

---

## What Was the Task?

The `injector.py` stub from OI-41 only had a placeholder docstring. The goal was to build a full CSV→MQTT electrical replay injector that can seed the pipeline with either real transformer CSV data (from DevB's OI-8 replay bot) or built-in synthetic data, without requiring live Modbus hardware.

**Acceptance Criteria (all met ✅):**

- [x] Reads electrical CSV files and publishes rows as JSON to MQTT
- [x] Auto-detects column names (handles aliases and non-standard headers)
- [x] Built-in synthetic data generator for demo/testing
- [x] Configurable replay speed, burst mode, and looping
- [x] Matches CLI interface documented in README
- [x] Unit tests (28 new tests, all passing)
- [x] Zero regressions (79/79 total tests pass)

---

## What Was Built

### 1. `src/omniview/edge/injector.py` — Full Implementation

| Component | Purpose |
|-----------|---------|
| `ELECTRICAL_FIELDS` | 23 canonical field names matching Selec MFM384 Modbus register map |
| `_COLUMN_ALIASES` | 80+ aliases for auto-detecting CSV column names (handles UCI Steel, DevB formats, etc.) |
| `_map_csv_columns()` | Maps arbitrary CSV headers → canonical fields (case-insensitive) |
| `read_csv_rows()` | Generator yielding mapped rows from CSV (supports looping) |
| `generate_synthetic_readings()` | Infinite generator producing realistic factory load profiles |
| `build_payload()` | Wraps data in standard OmniView envelope (timestamp, schema_version, sensor_type) |
| `ElectricalInjector` | Orchestrator class: CSV or synthetic → MQTT publish with interval/speed/burst control |
| `main()` / CLI | Full argparse CLI matching README documentation |

### Synthetic Generator Features

The synthetic generator produces physically plausible data:
- **Base load:** 65% of contracted demand (500 kVA)
- **Diurnal pattern:** sinusoidal 24-hour cycle
- **Random noise:** ±2.5% Gaussian
- **Machine start ramps:** occasional 10-25% spikes
- **MD near-miss spikes:** periodic pushes to 90-105% contracted demand (for testing OI-56 rule engine)
- **Derived parameters:** voltage, current, PF, kVAR, THD, frequency all physically consistent
- **Deterministic:** seeded RNG for reproducible testing

### CLI Modes

```bash
python -m omniview.edge.injector --csv FILE     # Replay from CSV
python -m omniview.edge.injector --synthetic    # Generate synthetic data
                                 --speed N      # N× faster
                                 --burst        # No delay
                                 --loop         # Repeat CSV
                                 --node ID      # Target node
                                 --max N        # Limit readings
```

### 2. Updated `edge/__init__.py`

Added `ElectricalInjector` to public API.

### 3. Updated `README.md`

Replaced placeholder "Coming in OI-12" section with full CLI documentation.

---

## Files Created/Modified (4 total)

```
 MOD  src/omniview/edge/injector.py     — Full implementation (was stub)
 MOD  src/omniview/edge/__init__.py     — Added ElectricalInjector export
 MOD  README.md                         — Updated Day-1 Replay section
 NEW  tests/test_injector.py            — 28 unit tests
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_injector.py -v` | ✅ 28/28 passed |
| `pytest tests/ -v` (full suite) | ✅ 79/79 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.edge import ElectricalInjector` |
| CLI --help | ✅ All options documented and functional |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| Auto-detect CSV columns via alias mapping | DevB's OI-8 format isn't finalized yet. Also handles UCI Steel dataset columns for early testing. |
| Built-in synthetic generator | DevB OI-8 hasn't shipped yet — we can demo Day-1 pipeline independently. |
| Deterministic RNG (seed=42) | Reproducible tests and demos. Same synthetic data on every run. |
| MD spikes every ~400 steps | Gives OI-56 rule engine realistic test data with near-miss events roughly every 100 minutes. |
| Physically derived parameters | kVA → PF → kW → kVAR → I → V chain ensures consistency. Dashboard won't show impossible combinations. |
| Burst mode | Enables fast TSDB seeding. Combined with subscriber (OI-54), can populate weeks of data in seconds. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-55 | Payload validation + Day-1 seed script | Injector ✅ + TSDB ✅ |
| **Chinmay** | OI-68 | Live dashboard | Injector ✅ → data in TSDB |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert rule | Synthetic data with MD spikes ✅ |

---

*Session completed: 10 August 2026, 12:42 PM IST*
