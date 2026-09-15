# OI-77 Worklog — Gas / Switchboard Overheating Rule (S1 "Fire Forecast")

**Epic:** [OI-36](https://mightium.atlassian.net/browse/OI-36) (Dashboard / Alerts)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-09-15  
**Depends on:** DevB gas_bot.py + gas_schema.json ✅, OI-69 (action cards) ✅

---

## Summary

Implemented the **S1 gas / switchboard overheating detection rule** — a
deterministic thermal-rise-before-smoke detector for electrical panel
switchboards. Consumes `gas` family readings from `readings_gas` (TSDB) or
a live MQTT stream and emits a `gas_overheat` Layer 3 event when pre-fire
conditions are detected. Includes an action card template for fire-priority
alerts routed to the plant manager.

**Design philosophy:** Deterministic rule, not ML — fire-precursor physics
is unambiguous (gas + particles + thermal rise = insulation degradation).
A model would only add opacity to a safety-critical detection. Safety
priority outranks all other alerts per PRD §5.7 (Safety > Compliance > Cost).

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------| 
| **NEW** | `src/omniview/rules/gas_overheat.py` | Core rule: `GasOverheatDetector` (stateful per-device) + `GasOverheatEvent` dataclass with 3-tier detection |
| **MOD** | `src/omniview/rules/action_cards.py` | Added `_gas_overheat_fields()` template — CRITICAL (fire precursor) and WARNING (panel overheat) action cards |
| **MOD** | `src/omniview/rules/__init__.py` | Export `GasOverheatDetector`, `GasOverheatEvent` |
| **NEW** | `tests/test_gas_overheat.py` | 21 unit tests — all self-contained, no DB/MQTT needed |
| **MOD** | `tests/test_action_cards.py` | Updated template coverage test (5 → 6 templates) |
| **NEW** | `Docs/OI-77_Worklog.md` | This file |

---

## Detection Tiers

| Tier | Condition | Severity | Duration Gate | Rationale |
|------|-----------|----------|:---:|-----------|
| **Fire precursor** | `rate_of_thermal_rise ≥ 3.0 °C/min` AND (`gas ≥ 25 ppm` OR `particles ≥ 40`) | CRITICAL | **None — immediate** | Safety-critical: no delay on a fire precursor |
| **Panel overheat** | `panel_temp ≥ 65 °C`, or (`gas ≥ 15 ppm` AND `particles ≥ 20`) | WARNING | 120 s sustained | Filters transient spikes and sensor glitches |
| **Watch** | `panel_temp ≥ 50 °C` AND `rise ≥ 1.0 °C/min` | INFO | 120 s sustained | Early monitoring — panel warming trend |

All thresholds are labelled **PLACEHOLDER** — calibrated against DevB's `gas_bot.py` physics model (smoldering triggers at 65 °C). Pending validation against real Schneider HeatTag datasheet during Phase 0 site data collection.

---

## Action Card Templates Added

| Event Type | Severity | Target Role | Card Summary |
|------------|----------|-------------|-------------|
| `gas_overheat` (CRITICAL) | CRITICAL | Plant Manager | "🔥 FIRE PRECURSOR — isolate panel power within 5 min; Do NOT open panel door (arc flash)" |
| `gas_overheat` (WARNING) | WARNING | Plant Manager | "⚠️ Panel Overheat — schedule thermal imaging inspection this shift; Do NOT increase panel load" |

Both cards include:
- ₹ impact (₹2–5 lakh for panel failure)
- Physical rationale (PVC/XLPE outgassing at ~80 °C, Schneider HeatTag detection window)
- Safety > Compliance > Cost priority flagging per PRD §5.7

---

## Architecture Fit

```
DevB's gas_bot.py                    OI-77 (this ticket)               OI-69 / OI-71
────────────────                     ────────────────────               ─────────────
gas_schema.json ─┐                                                     
gas_bot.py ──────┤    MQTT → TSDB    ┌──────────────────────┐         ┌──────────────┐
(I²R + smoldering│──→ readings_gas ─→│ GasOverheatDetector  │──event─→│ ActionCard   │
 + glitch sim)   │                   │ .evaluate(sample)    │         │ Generator    │
                 │                   └──────────────────────┘         └──────┬───────┘
                                              │                              │
                                     gas_overheat event             ┌───────▼───────┐
                                     (Layer 3)                      │ AlertRouter   │
                                                                    │ (OI-71)       │
                                                                    └───────────────┘
```

**Standalone today; plug-in ready for `detectors_live.py` (Phase C/D)** —
same pattern as OI-69 action cards (work without OI-60 conflict arbitration).

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| **Deterministic rule, not ML** | Fire precursor physics is unambiguous — gas + particles + thermal rise = insulation degradation. ML adds opacity to safety-critical detection. |
| **CRITICAL has no duration gate** | Safety-first: a fire precursor must alert immediately. Sustained gate only on WARNING/INFO. |
| **2-minute sustained gate for WARNING/INFO** | DevB's gas_bot.py has 0.1% benign glitch (1000 ppm spike). Sustained gate filters transient spikes without missing real events. |
| **Per-device state tracking** | Each `device_id` has independent `condition_since` timer. Two panels don't interfere with each other. |
| **5-minute stale-stream reset** | If no reading arrives for > 300 s, detector resets state for that device. Prevents stale timers from firing on reconnect. |
| **Thresholds labelled PLACEHOLDER** | Following OI-55/OI-69 pattern — pending Phase 0 site data calibration. All threshold values documented in module constants. |
| **Standalone + plug-in ready** | Following OI-69 pattern — works without `detectors_live.py`. When Lead builds the live spine runner, `detector.evaluate(sample)` is the integration point. |

---

## Test Results

```
21 passed in 0.09s (test_gas_overheat.py)
56 passed in 0.11s (test_gas_overheat.py + test_action_cards.py)
733 passed in 195s (full regression — 0 failures, 0 regressions)
```

Test groups:
- `GasOverheatEvent` dataclass (4 tests: creation, immutability, serialization, field coverage)
- Normal readings (2 tests: baseline → no event)
- CRITICAL fire precursor (3 tests: gas path, particle path, rise-only-no-fire)
- WARNING sustained gate (4 tests: first sample blocked, fires after 120 s, gas+particle combo, reset on normal)
- INFO watch tier (1 test: temp+rise after sustained)
- Benign glitch filter (1 test: 1000 ppm spike without thermal rise → no event)
- Multi-device independence (1 test: two devices tracked separately)
- Stale stream reset (1 test: 5-min gap resets timer)
- Action card integration (4 tests: template registered, CRITICAL card, WARNING card, ₹ impact)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Detects fire-precursor condition from gas readings | ✅ | CRITICAL tier fires immediately on thermal rise + gas/particles |
| Filters transient sensor glitches | ✅ | Sustained gate for WARNING/INFO; benign 1000 ppm spike test passes |
| Action card generated with fire-specific recommendations | ✅ | Two card variants (CRITICAL/WARNING) with ₹ impact + physical rationale |
| Safety priority flagged per PRD §5.7 | ✅ | Card explicitly states Safety > Compliance > Cost |
| No auto-actuation (human decides) | ✅ | Card recommends action; "Do NOT" anti-action included |
| Plug-in ready for live spine | ✅ | `detector.evaluate(sample)` API; no dependency on detectors_live.py |
| Zero test regressions | ✅ | 733/733 passed (full suite) |

---

## How to Run

```bash
# Run gas overheat tests only
pytest tests/test_gas_overheat.py -v

# Run gas overheat + action card tests
pytest tests/test_gas_overheat.py tests/test_action_cards.py -v

# Full regression
pytest tests/ -v

# Usage in code
from omniview.rules import GasOverheatDetector, GasOverheatEvent
detector = GasOverheatDetector()
event = detector.evaluate(gas_reading_dict)
```

---

## Dependencies

- **DevB gas_bot.py + gas_schema.json** ✅ (sensor simulation + schema)
- **OI-69** (action card generator) ✅
- **OI-51** (MQTT topics — `"gas"` in `SENSOR_TYPES`) ✅
- **OI-54** (TSDB hypertables — `readings_gas` table) ✅

## What's Unblocked Next

| Person | Ticket | Work | How OI-77 Helps |
|--------|--------|------|----------------|
| **Dnyandev** | Phase C/D | `detectors_live.py` — live spine runner | Gas rule ready to wire via `detector.evaluate(sample)` |
| **Dnyandev** | Phase H | H1 unified anomaly bundle | `gas_overheat` events are a new event source for the bundle |
| **Chinmay** | Phase C | Live spine end-to-end smoke test | Gas bot → MQTT → subscriber → TSDB → detector pipeline testable |
| **Chinmay** | Phase G | Hero wiring / predictive panel | Gas events feed into Owner Events anomaly list |

---

*Session completed: 15 September 2026, 4:47 PM IST*
