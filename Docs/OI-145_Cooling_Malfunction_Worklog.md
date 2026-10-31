# OI-145 Worklog — `cooling_malfunction` Rule Evaluator & Action Card Integration

**Epic:** [OI-135](https://mightium.atlassian.net/browse/OI-135) (Instrument Health / Wear and Tear)  
**Task:** [OI-145](https://mightium.atlassian.net/browse/OI-145) (Cooling Malfunction from High Energy and Low Cooling Temperature)  
**Status:** ✅ Complete  
**Date:** 2026-10-30  
**Spec Reference:** [`Docs/DS/LLD_Four_Core_Features.md`](DS/LLD_Four_Core_Features.md) §3 (lines 57, 63–65) · Jira Sprint 5  

---

## 1. Specification Requirements & Compliance

From `LLD_Four_Core_Features.md` §3 and Jira issue [OI-145](https://mightium.atlassian.net/browse/OI-145):

| Requirement | Spec Source | Implementation Details |
|---|---|---|
| Emit `cooling_malfunction` when energy is high and cooling temp is low | LLD §3 line 63 | Threshold comparison (`power_kw > 50 kW` and `cooling_temp_c < 100 °C`). |
| Suggestion only — does NOT stop the machine | LLD §3 line 63 | Card recommends "service or inspect"; `do_not` prohibits stopping machine; event sets `stop_machine=False`. |
| Does NOT add a second health index | Jira description | Retains existing Stage A `predict_maintenance_risk`; no new index created. |
| Pure comparison / no ML | LLD §3 Table row 5 | `evaluate_cooling_malfunction` is a stateless pure comparison function. |
| Existing tests stay green | LLD §3 line 65 | All 171 tests across all modules pass with 0 failures. |
| One new test case for synthetic pair of rows | LLD §3 line 65 | Added `test_cooling_malfunction_synthetic_pair_of_rows` in `tests/test_predictive_maintenance.py`. |
| Dedicated test suite | Quality bar | 16 comprehensive unit tests in `tests/test_cooling_malfunction.py`. |

---

## 2. Architecture & Design

### Physical Rationale
In an injection stretch blow molding (ISBM) machine:
- The barrel heaters are regulated by PID controllers to maintain ~255 °C during normal production.
- When electrical power is high (>50 kW) but the barrel/cooling temperature is cold (<100 °C), it signals:
  1. **Cooling system stuck ON:** Chiller valve open, continuously fighting active heaters and wasting energy (~₹1,500–₹4,500/day).
  2. **Heater element burnout:** Drawing abnormal motor/auxiliary load while heating circuits fail.
  3. **Sensor failure:** RTD/PT100 probe disconnected or open-circuit.

### Module Structure
1. **Config Constants ([`src/omniview/config.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/config.py)):**
   - `COOLING_POWER_THRESHOLD_KW = 50.0` (with env override `COOLING_POWER_THRESHOLD_KW`)
   - `COOLING_TEMP_LOW_C = 100.0` (with env override `COOLING_TEMP_LOW_C`)
   - Clearly marked as `COOLING_IS_PLACEHOLDER = True` until site calibration.

2. **Core Evaluator & Detector ([`src/omniview/rules/cooling_malfunction.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/cooling_malfunction.py)):**
   - `evaluate_cooling_malfunction(...)`: Pure function handling direct float inputs, synthetic pairs of rows (LLD §3 line 65), or composite dictionaries with automatic field extraction (raw bot payloads and wire-adapted keys).
   - `CoolingMalfunctionEvent`: Frozen dataclass conforming to Layer 3 event contract.
   - `CoolingMalfunctionDetector`: Stateful detector implementing the `Detector` protocol (`evaluate(sample) -> Event | None`), handling cross-family sensor ingestion (`electrical`, `thermal`, `cooling`) with time-correlation caching and alert cooldown suppression.

3. **Action Card Template ([`src/omniview/rules/action_cards.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/action_cards.py)):**
   - Registered `_cooling_malfunction_fields` in `CARD_TEMPLATES` and `_SCENARIO_TO_EVENT`.
   - Title: `🧊 Cooling Malfunction — High Energy Draw with Low Barrel Temperature`.
   - Recommended action: "Service or inspect the cooling circuit, barrel heaters, and RTD temperature sensors during the next maintenance window or shift transition."
   - Do Not: "Do NOT stop the machine — this is a service/inspection advisory for thermal efficiency, not an immediate safety trip."
   - Target role: `maintenance_engineer`.
   - Rupee impact: "Energy waste: ~₹1,500–₹4,500/day from concurrent heating and cooling or unmetered losses".

4. **Live Runner Registration ([`src/omniview/rules/detectors_live.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/detectors_live.py)):**
   - Registered in `build_default_registry()` consuming `["electrical", "thermal", "cooling"]` sensor streams.

5. **Namespace Re-exports:**
   - Available via [`omniview.rules`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/__init__.py) and [`omniview.rules.predictive_maintenance`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/predictive_maintenance.py).

---

## 3. Files Changed & Created

| Status | File Path | Description |
|---|---|---|
| **NEW** | `src/omniview/rules/cooling_malfunction.py` | Core evaluator function, event dataclass, and streaming detector. |
| **MODIFIED** | `src/omniview/config.py` | Added `COOLING_POWER_THRESHOLD_KW` and `COOLING_TEMP_LOW_C` constants. |
| **MODIFIED** | `src/omniview/rules/action_cards.py` | Added `cooling_malfunction` template to `CARD_TEMPLATES` and `_SCENARIO_TO_EVENT`. |
| **MODIFIED** | `src/omniview/rules/predictive_maintenance.py` | Re-exported `evaluate_cooling_malfunction`, `CoolingMalfunctionEvent`, and `CoolingMalfunctionDetector`. |
| **MODIFIED** | `src/omniview/rules/__init__.py` | Exported cooling malfunction utilities under `omniview.rules`. |
| **MODIFIED** | `src/omniview/rules/detectors_live.py` | Added `cooling_malfunction` detector entry into default detector registry. |
| **MODIFIED** | `tests/test_predictive_maintenance.py` | Added LLD §3 line 65 synthetic pair of rows test. |
| **MODIFIED** | `tests/test_action_cards.py` | Updated template coverage tests to validate all 9 registered templates. |
| **NEW** | `tests/test_cooling_malfunction.py` | 16 dedicated unit tests covering pure comparison, streaming detector, and card generation. |
| **NEW** | `Docs/OI-145_Cooling_Malfunction_Worklog.md` | This technical worklog. |

---

## 4. Verification & Test Results

```
collected 171 items

tests\test_cooling_malfunction.py ................ [16 passed]
tests\test_predictive_maintenance.py ......         [6 passed]
tests\test_action_cards.py ................................... [35 passed]
tests\test_detectors.py .......................... [26 passed]
tests\test_adapters_wire.py ................................... [35 passed]
tests\test_predictive.py ..................................................... [53 passed]

============================= 171 passed in 0.45s =============================
```

All 171 tests passed with zero failures and zero regressions.
