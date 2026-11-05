# OI-153: Action Card Templates for Feature 2 Events — Worklog

**Parent Issue:** [OI-135 Instrument Health / Wear and Tear](https://mightium.atlassian.net/browse/OI-135)  
**Ticket:** [OI-153](https://mightium.atlassian.net/browse/OI-153)  
**Sprint:** Sprint 5  
**Assignee:** Chinmay Wadettiwar  

---

## 1. Objectives & Scope
Transform Feature 2 Layer 3 events (`maintenance_risk` and `cooling_malfunction`) into rich, actionable, and strictly Human-in-the-Loop (HITL) operator action cards. Replace generic placeholder cards with specific templates adhering to plant safety guardrails.

---

## 2. Acceptance Criteria & Implementation Verification

| Acceptance Criterion | Status | Implementation Details |
|---|---|---|
| **`_maintenance_risk_fields(event)` Title** | ✅ Complete | `🛠️ Maintenance Risk — Equipment Health Index Degraded` |
| **`_maintenance_risk_fields(event)` Summary** | ✅ Complete | Reports Health Index score (`{hi_score}/100`), risk tier (`high`/`medium`), and primary drifting features (e.g. 7-day vibration slope). |
| **`_maintenance_risk_fields(event)` Action** | ✅ Complete | `"Schedule bearing lubrication and shaft alignment check at shift end. Verify mechanical couplings and motor electrical connections."` |
| **`_maintenance_risk_fields(event)` Do Not** | ✅ Complete | `"Do NOT trigger emergency stop mid-cycle unless vibration exceeds ISO Zone D trip threshold — allow controlled cycle finish to prevent mechanical shock and preform spoilage."` |
| **`_cooling_malfunction_fields(event)` Title** | ✅ Complete | `❄️ Cooling Malfunction — Thermal/Energy Mismatch Detected` |
| **`_cooling_malfunction_fields(event)` Summary** | ✅ Complete | Explains active electrical work (`{power_kw} kW`) alongside cold coolant/barrel stream (`{temp_c} °C`). |
| **`_cooling_malfunction_fields(event)` Action** | ✅ Complete | `"Inspect chiller circulation pump, inlet valves, and temperature probe wiring. Service or inspect the cooling circuit and barrel heaters during the next maintenance window."` |
| **`_cooling_malfunction_fields(event)` Do Not** | ✅ Complete | `"Do NOT restart machine under load until coolant circulation is verified. Do NOT stop the machine mid-cycle — this is a service/inspection advisory for thermal efficiency, not an immediate safety trip."` |
| **Unit tests in `tests/test_action_cards.py`** | ✅ Complete | Added `TestFeature2ActionCardTemplates` testing required fields, exact copy, Layer 3 event integration, and verifying no automated actuation commands. |

---

## 3. Key Safety & Architecture Highlights
- **Zero Automated Actuation:** Both cards are strictly advisory and human-in-the-loop (HITL), explicitly directing operators *not* to trip breakers or perform emergency stops mid-cycle unless severe vibration safety trips (ISO Zone D) are triggered.
- **Backward Compatibility:** All existing tests in `test_action_cards.py` (39/39 passing) and `test_cooling_malfunction.py` (16/16 passing) continue to pass without breaks.
- **Robust Field Extraction:** Handles both flat legacy test dicts and structured Layer 3 event envelopes with nested `payload`, `contributing_features`, and metadata.

