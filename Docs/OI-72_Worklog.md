# OI-72 Worklog — Jumbo-Display Modbus Register Feed Stub

**Epic:** [OI-36](https://mightium.atlassian.net/browse/OI-36) (Dashboard / Alerts)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-21  
**Depends on:** OI-68 (dashboard queries ✅), OI-69 (action cards ✅)

---

## Summary

Implemented a Modbus holding-register feed stub for the jumbo LED floor display.
The register bank mirrors the cloud dashboard's live metrics — **same source of
truth** (`queries.py`). Includes IEEE 754 float↔register encoding, a heartbeat
counter, and a drift-check function comparing register values against dashboard
values.

**Design philosophy:** The operator on the floor needs a single glanceable number
they can react to in seconds — no login, no scrolling. The jumbo display is a
different interface for a different audience on a different timescale
(Architecture §2.2, §3.3).

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/dashboard/jumbo_display.py` | Register map (16 regs), `JumboDisplayFeed` with mock/dashboard data sources, `check_drift()`, float↔register encoding |
| **MOD** | `src/omniview/dashboard/__init__.py` | Export `JumboDisplayFeed`, `RegisterSnapshot` |
| **MOD** | `src/omniview/dashboard/app.py` | Added "📺 Jumbo Floor Display" section with register bank viewer |
| **NEW** | `tests/test_jumbo_display.py` | 37 unit tests — all self-contained, no DB needed |
| **NEW** | `Docs/OI-72_Worklog.md` | This file |

---

## Register Map (Documented Contract)

| Address | Name | Type | Unit | Dashboard Source |
|---------|------|------|------|-----------------|
| 0–1 | live_kva | FLOAT32 | kVA | `get_latest_kva()` |
| 2–3 | contract_kva | FLOAT32 | kVA | `config.CONTRACTED_DEMAND_KVA` |
| 4–5 | md_proximity_pct | FLOAT32 | % | `get_latest_kva()` |
| 6–7 | penalty_avoided_inr | FLOAT32 | ₹ | `get_penalty_avoided()` |
| 8–9 | idle_load_pct | FLOAT32 | % | `get_idle_load_percent()` |
| 10 | warning_count | UINT16 | count | `get_alerts()` |
| 11 | critical_count | UINT16 | count | `get_alerts()` |
| 12 | active_severity | UINT16 | enum | 0=NONE 1=INFO 2=WARNING 3=CRITICAL |
| 13 | heartbeat | UINT16 | counter | Incrementing — proves feed alive |
| 14–15 | peak_kva_24h | FLOAT32 | kVA | `get_peak_kva_24h()` |

**Total: 16 holding registers** (6 FLOAT32 × 2 regs + 4 UINT16 × 1 reg)

---

## Drift Check Mechanism

The `check_drift()` method compares current register values against a fresh
dashboard query to verify the "same source of truth" acceptance criterion:

```python
feed = JumboDisplayFeed()
feed.update()                # writes registers from dashboard queries
result = feed.check_drift()  # compares registers ↔ fresh dashboard values

if result.drifted:
    print(f"DRIFT DETECTED: max {result.max_drift_pct:.2f}%")
    for field, info in result.field_drifts.items():
        if info["drifted"]:
            print(f"  {field}: register={info['register_value']} "
                  f"dashboard={info['dashboard_value']} "
                  f"drift={info['drift_pct']:.2f}%")
```

**Tolerance:** 0.1% for floats (covers IEEE 754 rounding), exact match for integers.

**Why drift can occur in production:**
- Network delay between register write and dashboard refresh
- Concurrent updates from different consumers
- Float precision loss in Modbus 16-bit encoding

---

## Architecture Fit

```
Dashboard queries.py (OI-68)    ← same source of truth
        │
        ├──→ Streamlit UI (Plant Manager)
        │
        └──→ JumboDisplayFeed (OI-72)  ← NEW
                    │
                    ▼
             ┌──────────────────┐
             │ Register Bank    │  16 holding registers
             │ (in-memory dict) │  IEEE 754 FLOAT32 + UINT16
             └──────────────────┘
                    │
                    ▼ (production: pymodbus TCP slave)
             ┌──────────────────┐
             │ Jumbo LED Display│  Modbus RTU/TCP master
             │ (floor-level)    │  polls registers every 1s
             └──────────────────┘
```

---

## Production Swap Path

| POC (now) | Production | Change needed |
|-----------|-----------|---------------|
| In-memory dict | pymodbus `ModbusTcpServer` | Replace `_write_float`/`_write_uint16` with pymodbus register writes |
| Mock data source | Dashboard data source | Change `data_source="dashboard"` (already supported) |
| Logged output | Physical LED display | Display polls the pymodbus server — no code change needed |

---

## Test Results

```
37 passed in 0.83s (test_jumbo_display.py)
464 passed in 6.62s (full regression)
```

Test groups:
- `TestFloatRegisterConversion` (6 tests: round-trip, zero, negative, uint16 bounds)
- `TestRegisterAddress` (4 tests: sequential, total, specific addresses)
- `TestJumboDisplayFeedMock` (7 tests: update, values, read-back, snapshot, copy)
- `TestHeartbeat` (3 tests: increment, register value, wrap at 65536)
- `TestDriftCheck` (5 tests: no-drift, tampered, tolerance, integer, all-fields)
- `TestSerialization` (4 tests: snapshot dict, drift dict, JSON-safe)
- `TestSeverityMapping` (5 tests: enum values, ordering)
- `TestRegisterMapDocumentation` (3 tests: header, registers, sources)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Stub writes registers matching dashboard values | ✅ | `JumboDisplayFeed.update()` reads from same `queries.py` functions as Streamlit UI |
| Drift check documented | ✅ | `check_drift()` method + this worklog section + 5 drift tests |
| Modbus register feed stub for live kVA / warnings | ✅ | 16-register map with float encoding, kVA, alerts, severity |
| Same source of truth as dashboard | ✅ | Both consume `get_latest_kva()`, `get_alerts()`, etc. from `queries.py` |

---

## How to Run

```bash
# Run jumbo display tests
pytest tests/test_jumbo_display.py -v

# Launch dashboard — jumbo display section shows register bank
streamlit run src/omniview/dashboard/app.py

# Full regression
pytest tests/ -v
```

---

## Dependencies

- **OI-68** (dashboard queries) ✅
- **OI-69** (action cards — alert data) ✅
- **OI-55** (seed script) ✅

## What's Unblocked Next

| Person | Ticket | Work | How OI-72 Helps |
|--------|--------|------|-----------------|
| **Chinmay** | OI-73–77 | Hardware track | Register map defines the physical display's polling contract |
| **Dnyandev** | OI-78–80 | Live cutover | Jumbo display can show real kVA during live Modbus verification |

---

*Session completed: 21 August 2026, 11:08 PM IST*
