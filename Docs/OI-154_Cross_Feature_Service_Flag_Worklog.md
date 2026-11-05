# OI-154 Worklog — Cross-Feature Maintenance Service Flag Attachment

**Epic:** [OI-135](https://mightium.atlassian.net/browse/OI-135) (Instrument Health / Wear and Tear)  
**Task:** [OI-154](https://mightium.atlassian.net/browse/OI-154) (Cross-Feature Maintenance Service Flag Attachment)  
**Status:** ✅ Complete  
**Date:** 2026-11-04  
**Spec References:**  
- [`Docs/DS/LLD_Four_Core_Features.md`](DS/LLD_Four_Core_Features.md) §3 (line 85) & §5 (line 101)  
- [`Docs/DS/PRD_Four_Core_Features.md`](DS/PRD_Four_Core_Features.md) §5  

---

## 1. Summary of Work Executed

This task delivers the cross-feature service flag attachment bridging **Feature 2 (Instrument Health)**, **Feature 3 (Maximum Demand Plan)**, and **Feature 4 (Consumption, Production & Waste)**:

1. **Service Flag API & Registry (Feature 2):**
   - Implemented `MachineServiceRegistry`, `get_machine_service_status()`, `set_machine_service_status()`, and `clear_machine_service_registry()` in [`src/omniview/rules/predictive_maintenance.py`](../src/omniview/rules/predictive_maintenance.py).
   - Resolves machine status from:
     - Health Index critical risk tier (`risk_tier == "high"` or $\text{HI} < 40$).
     - Active maintenance events in `MaintenanceLogger` (`data/maintenance_events.jsonl`).
     - In-memory scheduled maintenance windows.
     - Explicit manual overrides.
   - Automatically registers degrading machines when `run_stage_a_pipeline()` or `predict_maintenance_risk()` executes.

2. **96-Slot Demand Aggregator with Labeled Share Curtailment (Feature 3):**
   - Built [`src/omniview/rules/demand_slots.py`](../src/omniview/rules/demand_slots.py) conforming to LLD §4 lines 85 & 89.
   - Computes 96 fifteen-minute demand intervals (24-hour day-ahead forecast).
   - Automatically queries `get_machine_service_status()` for each equipment record and drops its `labeled_share_kw` from affected slots without altering baseline equations.
   - Carries `synthetic: True` on campus historical baselines.

3. **Lazy-Idle & Waste Schedule Maintenance Exclusion (Feature 4):**
   - Updated [`LazyIdleDetector`](../src/omniview/rules/lazy_idle.py) and added standalone [`evaluate_lazy_idle()`](../src/omniview/rules/lazy_idle.py) to check `get_machine_service_status()`. Suppresses false lazy-idle waste alerts while technicians work on or test machine heaters/pumps during maintenance.
   - Built [`src/omniview/rules/waste_schedule.py`](../src/omniview/rules/waste_schedule.py) per LLD §5 lines 104–111. Sets `waste_where = "none"` with `maintenance_suppressed = True` when the target machine is down for service.

4. **Integration Test Suite:**
   - 16 comprehensive unit and end-to-end integration tests in [`tests/test_cross_feature_service_flag.py`](../tests/test_cross_feature_service_flag.py).
   - Full regression suite verified (187/187 tests passing across the codebase).

---

## 2. Specification Compliance Matrix

| Requirement | Spec Reference | Implementation Details | Status |
|---|---|---|:---:|
| Expose `get_machine_service_status(machine_id)` | Task Criterion 1 / LLD §3 line 85 | Callable function in `predictive_maintenance.py` and exported in `omniview.rules` | ✅ |
| Returns True if high-risk tier or scheduled maintenance | Task Criterion 2 / LLD §3 line 85 | Checks `risk_tier == 'high'` (or $\text{HI} < 40$), in-memory windows, and `MaintenanceLogger` records | ✅ |
| Feature 3 96-slot demand aggregator checks flag & excludes share | Task Criterion 3 / LLD §4 lines 85, 89 | `aggregate_96_slot_demand()` in `demand_slots.py` deducts `machine.labeled_share_kw` from affected slots | ✅ |
| Feature 4 waste_schedule verifies flag before flagging waste | Task Criterion 4 / LLD §5 line 101 | `compose_waste_schedule()` in `waste_schedule.py` excludes machines in maintenance | ✅ |
| Integration test verifying maintenance suppresses false waste alerts | Task Criterion 5 / LLD §5 line 115 | `test_cross_feature_service_flag.py` verifies both streaming detector and waste schedule | ✅ |

---

## 3. Files Changed & Created

| Status | File Path | Description |
|---|---|---|
| **MODIFIED** | `src/omniview/rules/predictive_maintenance.py` | Added `MachineServiceRegistry`, `get_machine_service_status`, `set_machine_service_status`, `clear_machine_service_registry`. |
| **NEW** | `src/omniview/rules/demand_slots.py` | 96-slot day-ahead demand plan engine with machine labeled share exclusion. |
| **MODIFIED** | `src/omniview/rules/lazy_idle.py` | Added maintenance check suppression in `LazyIdleDetector` and standalone `evaluate_lazy_idle()`. |
| **NEW** | `src/omniview/rules/waste_schedule.py` | Feature 4 waste schedule composer verifying the Feature 2 service flag. |
| **MODIFIED** | `src/omniview/rules/__init__.py` | Exported all new cross-feature types and functions under `omniview.rules`. |
| **NEW** | `tests/test_cross_feature_service_flag.py` | 16 dedicated unit and integration tests covering all acceptance criteria. |
| **NEW** | `Docs/OI-154_Cross_Feature_Service_Flag_Worklog.md` | This technical worklog. |

---

## 4. Verification Evidence

```bash
python -m pytest tests/test_cross_feature_service_flag.py tests/test_cooling_malfunction.py tests/test_predictive_maintenance.py tests/test_action_cards.py tests/test_detectors.py tests/test_predictive.py tests/test_adapters_wire.py -v
```

**Results:**
```
============================= 187 passed in 1.30s =============================
```
187/187 tests passing with zero failures and zero regressions.

