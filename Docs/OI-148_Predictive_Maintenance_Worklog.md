# OI-148 Worklog — Predictive Maintenance LLD Facade Module & Feature 2 Architecture

**Epic:** [OI-135](https://mightium.atlassian.net/browse/OI-135) (Instrument Health / Wear and Tear)  
**Task:** OI-148 (Follow-up to OI-62, OI-65, OI-67)  
**Status:** ✅ Complete  
**Date:** 2026-10-28  
**Specs:** [LLD_Four_Core_Features.md](DS/LLD_Four_Core_Features.md) §3 Table 3 · [OI-62 PRD](DS/OI-62_Predictive_Maintenance_Module_PRD.md) §6  

---

## 1. Summary of Work Executed

This work accomplished three major objectives for **OmniView IQ — Feature 2 (Instrument Health)**:

1. **System & Sub-Feature Architecture Analysis:**
   - Performed deep-dive analysis of Feature 2 and Feature 4 against [`LLD_Four_Core_Features.md`](DS/LLD_Four_Core_Features.md).
   - Resolved the hardware discrepancy regarding cooling: confirmed through the Bill of Materials ([`src/omniview/edge/bom.py`](../src/omniview/edge/bom.py)) that there is **no physical cooling sensor**; the system correlates active electrical power against the **Surface Thermal Probe** (RTD/PT100 on the barrel) or ambient baseline.
   - Designed and compiled three standalone, interactive Archify HTML architecture diagrams with zero-crossing topological routing, passing all quality gates (`showcase` profile).

2. **Jira Sprint 5 Task Planning:**
   - Created detailed specifications and definitions of done for 4 sprint tickets:
     - **OI-148**: LLD Facade Module (`predictive_maintenance.py`)
     - **OI-145**: `cooling_malfunction` rule evaluator
     - **OI-149**: Action Card templates for Feature 2
     - **OI-150**: Cross-feature `machine_in_maintenance` service flag integration

3. **Implementation of the LLD Facade Module:**
   - Built and registered [`src/omniview/rules/predictive_maintenance.py`](../src/omniview/rules/predictive_maintenance.py).
   - Unified distributed Stage A algorithms under standard LLD entry points.
   - Wrote comprehensive unit tests in [`tests/test_predictive_maintenance.py`](../tests/test_predictive_maintenance.py).
   - Verified zero regressions across the entire test suite (119/119 tests passing).

---

## 2. Files Changed & Created

| Action | File Path | Description |
|---|---|---|
| **NEW** | `src/omniview/rules/predictive_maintenance.py` | LLD facade module exporting `run_stage_a_pipeline`, `predict_maintenance_risk`, and `DEMO_PRIORS`. |
| **MODIFIED** | `src/omniview/rules/__init__.py` | Registered and exported facade functions under the root `omniview.rules` namespace. |
| **NEW** | `tests/test_predictive_maintenance.py` | Unit test suite covering empty runs, synthetic multi-day batch pipeline, and dual-contract risk predictions. |
| **NEW** | `.archify/architecture-f2-subfeatures-20261028-214900/f2-subfeatures.html` | Interactive Archify architecture diagram detailing all 6 sub-features of Feature 2. |
| **NEW** | `.archify/architecture-instrument-health-20261028-172800/instrument-health.html` | Interactive Archify architecture diagram for Feature 2 instrument health. |
| **NEW** | `.archify/architecture-consumption-waste-20261028-172800/consumption-waste.html` | Interactive Archify architecture diagram for Feature 4 consumption, production & waste. |
| **NEW** | `Docs/OI-148_Predictive_Maintenance_Worklog.md` | This delivery report and execution log. |

---

## 3. What Outputs This Work Produces

### Output A: Standardized Callable Python API
Callers and downstream engines can now consume Feature 2 using clean, high-level functions without needing to know internal pipeline details:

```python
from omniview.rules.predictive_maintenance import (
    run_stage_a_pipeline,
    predict_maintenance_risk,
    DEMO_PRIORS,
)

# 1. Run the Stage A batch pipeline for a machine
batch_result = run_stage_a_pipeline(
    readings=raw_tsdb_readings,
    machine_id="isbm-main-feed",
    synthetic=True,
)

# 2. Extract results
print(batch_result.latest_hi.health_index)  # e.g., 34.2 (0–100 score)
print(batch_result.latest_hi.risk_tier)     # e.g., "high"

# 3. Generate Layer 3 maintenance_risk event
event = predict_maintenance_risk(batch_result.latest_hi)
```

### Output B: Layer 3 Event Envelope (`maintenance_risk`)
When an equipment component degrades or breaches risk thresholds, the module outputs a structured Layer 3 dictionary:

```json
{
  "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "machine_id": "isbm-main-feed",
  "device_id": "isbm-main-feed",
  "timestamp": "2026-10-28T22:05:00.000Z",
  "source_unit": "predictive_maintenance_stage_a",
  "event_type": "maintenance_risk",
  "severity": "critical",
  "confidence_stage": "stage_a_unsupervised",
  "synthetic": true,
  "payload": {
    "health_index": 34.2,
    "risk_tier": "high",
    "confidence_stage": "stage_a_unsupervised",
    "avg_z_score": 5.48,
    "signal_count": 8,
    "gap_flagged": false,
    "contributing_features": {
      "z_rms_velocity_mm_sec": {
        "slope_7d": 0.0821,
        "z_score": 6.84,
        "direction": "rising",
        "prior_mean": 1.2,
        "prior_std": 0.4
      },
      "current_a_avg": {
        "slope_7d": 1.45,
        "z_score": 3.62,
        "direction": "rising",
        "prior_mean": 205.0,
        "prior_std": 15.0
      }
    },
    "cusum_alerts": [],
    "cusum_alert_count": 0
  }
}
```

### Output C: Upstream & Downstream System Connections

1. **Layer 3 Action Card Generator ([`action_cards.py`](../src/omniview/rules/action_cards.py)):**
   - Consumes the `maintenance_risk` event dict.
   - Formats a human-readable card for plant personnel:
     - `title`: *"🛠️ Maintenance Risk — Equipment Health Index Degraded"*
     - `recommended_action`: *"Schedule bearing lubrication and check motor shaft alignment."*
     - `do_not`: *"Do NOT trigger emergency stop mid-cycle — allow controlled cycle finish."*

2. **Feature 3 (Maximum Demand Plan):**
   - When a machine is flagged as `risk_tier == "high"` or is scheduled for maintenance, it sets `machine_in_maintenance = True`.
   - Feature 3 automatically subtracts that machine’s labeled load share from the upcoming 96 demand slots, preventing overestimation of grid demand.

3. **Feature 4 (Consumption, Production & Waste Scheduler):**
   - Uses the `machine_in_maintenance` flag to exclude the machine from production scheduling.
   - Prevents false "lazy-idle" alerts while technicians test heaters or calibrate pumps during maintenance.

4. **Operator Dashboard / Plant Manager UI:**
   - Displays real-time 0–100 Health Index trends.
   - Visualizes the top drifting signals (e.g., $+0.08\text{ mm/s/day}$ vibration climb).
   - Shows ISO 10816-3 severity status (Zone A, B, C, or D).

---

## 4. Verification & Testing Evidence

Full test execution across all related modules:
```bash
python -m pytest tests/test_predictive_maintenance.py tests/test_predictive.py tests/test_detectors.py tests/test_action_cards.py
```

**Results:**
```
============================= 119 passed in 0.41s =============================
```
- `tests/test_predictive_maintenance.py`: **5 passed** (New facade tests)
- `tests/test_predictive.py`: **53 passed** (Priors, daily aggregation, slopes, HI, CUSUM)
- `tests/test_detectors.py`: **26 passed** (Vibration zone, lazy idle, pressure leak)
- `tests/test_action_cards.py`: **35 passed** (Card generation & templates)

---

## 5. Next Steps

With the facade module (OI-148) complete and green, the next tasks in Sprint 5 under Epic OI-135 are:
1. **[OI-145](https://mightium.atlassian.net/browse/OI-145):** Implement `cooling_malfunction` rule comparator (high electrical power + low cooling/barrel temp).
2. **OI-149:** Add card templates for `maintenance_risk` and `cooling_malfunction` in `action_cards.py`.
3. **OI-150:** Wire `machine_in_maintenance` flag propagation to Feature 3 and Feature 4.
