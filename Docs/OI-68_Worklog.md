# OI-68 Worklog — Live Dashboard: kVA vs Contract, Alerts, HI Trend

**Epic:** OI-36 (Dashboard / Alerts)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-19

---

## Summary

Implemented the Streamlit live dashboard fulfilling PRD FR8 §2.6 hero metrics.
The dashboard reads seeded/live TSDB data with zero "TBD" placeholders — all
4 hero metrics compute real values from the OI-55 seed data.

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/dashboard/app.py` | Streamlit dashboard — 4 hero metrics, kVA chart, alert feed, HI trend |
| **NEW** | `src/omniview/dashboard/queries.py` | Data access layer — 8 query functions → pandas DataFrames |
| **MOD** | `src/omniview/dashboard/__init__.py` | Updated docstring and exports |
| **MOD** | `src/omniview/config.py` | Added `DASHBOARD_REFRESH_S`, `MD_PENALTY_RATE_PER_KVA`, `IDLE_CURRENT_THRESHOLD_A`, `IDLE_TEMP_THRESHOLD_C` |
| **NEW** | `tests/test_dashboard_queries.py` | 32 unit tests — all mocked, no DB required |
| **NEW** | `Docs/OI-68_Worklog.md` | This file |

---

## Hero Metrics Implemented

| # | Hero Metric | Data Source | Status |
|---|-------------|-------------|:------:|
| 1 | **Live kVA vs. Contracted Demand** | `readings_electrical` → `apparent_power_kva_total` / 500 kVA | ✅ |
| 2 | **Projected Penalty Avoided (₹)** | Peak kVA × ₹350/kVA MSEDCL rate | ✅ |
| 3 | **SEC (kWh/1,000 bottles)** | `readings_electrical` kWh + `readings_stroke` cycles | ✅ |
| 4 | **Idle Load %** | Low current + elevated thermal (lazy_idle scenario) | ✅ |

---

## Dashboard Layout

```
┌──────────────────────────────────────────────────────┐
│  ⚡ OmniView IQ — ISBM-PET Pune Live Dashboard       │
├──────────┬──────────┬──────────┬─────────────────────┤
│ Hero 1   │ Hero 2   │ Hero 3   │ Hero 4              │
│ kVA/500  │ ₹ Saved  │ SEC      │ Idle Load %         │
├──────────┴──────────┴──────────┴─────────────────────┤
│  📊 kVA vs Contracted Demand (24h time-series)        │
│  [line chart: Compressor + ISBM + 500 kVA red line]   │
├────────────────────────┬─────────────────────────────┤
│  🔔 Alert Feed          │  📈 Health Index Trend       │
│  [table with severity]  │  [line chart: HI over time] │
└────────────────────────┴─────────────────────────────┘
```

---

## Query Functions (queries.py)

| Function | Returns |
|----------|---------|
| `get_latest_kva(device_id)` | Latest kVA + MD proximity % |
| `get_kva_timeseries(device_id, hours)` | DataFrame: time, kva, kw, pf |
| `get_peak_kva_24h()` | Peak kVA across all electrical devices |
| `get_penalty_avoided(peak_kva)` | ₹ penalty avoided + headroom |
| `get_energy_and_strokes(hours)` | SEC, total kWh, total strokes |
| `get_idle_load_percent(hours)` | Idle %, idle minutes, total minutes |
| `get_alerts(hours)` | DataFrame of scenario-labeled alerts |
| `get_health_index_trend(device_id, hours)` | DataFrame: time, hi_score, iso_zone |

---

## Alert Feed Design

Since Lead's rule engine (OI-56–61) doesn't exist yet, alerts are extracted
from `scenario_label` in the JSONB data column:

| Scenario | Severity | Description |
|----------|----------|-------------|
| `md_nearmiss` | CRITICAL | kVA approaching 500 kVA contract limit |
| `lazy_idle` | WARNING | Machine idle but barrel temp elevated |
| `leak_proxy` | WARNING | Pressure decaying — possible leak |

Alerts are deduplicated per-minute per-scenario per-device and sorted newest-first.

---

## Test Results

```
32 passed in 1.25s (test_dashboard_queries.py)
336 passed in 7.03s (full regression)
```

Test groups:
- `_extract_data_field` helper (6 tests)
- Hero 1: Latest kVA (3 tests)
- kVA timeseries (2 tests)
- Peak kVA (2 tests)
- Hero 2: Penalty avoided (4 tests)
- Hero 3: SEC computation (2 tests)
- Hero 4: Idle load % (3 tests)
- Alert extraction (4 tests)
- HI trend / ISO zone mapping (6 tests)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Hero metrics populate from seeded/live data | ✅ | All 4 heroes query `readings_*` hypertables directly |
| No TBD in demo view once seeded | ✅ | Every metric computes real values — no placeholders |
| Streamlit dashboard reading TSDB | ✅ | `queries.py` uses `query_by_time_range()` / `query_latest()` |
| Show alerts from rule engine / PdM | ✅ | Reads `scenario_label` from JSONB; plug-in ready for rule events |

---

## How to Run

```bash
# Ensure TSDB has data (seed if needed)
python -m omniview.ingest.seed

# Launch dashboard
streamlit run src/omniview/dashboard/app.py
```

---

## Dependencies

- **OI-54** (TSDB hypertables) ✅
- **OI-15** (time-range queries) ✅
- **OI-55** (seed script) ✅

## Next Steps

- **OI-56–61**: When Lead ships rule engine, switch alert feed from TSDB-computed to rule-engine events
- **OI-62–67**: When Lead ships PdM Stage 0/A, replace ISO zone HI with real HI score
