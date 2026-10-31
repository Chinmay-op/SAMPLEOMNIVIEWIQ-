# F07 connector — anomaly bundle composition map

**Companion to:** [`F07_Anomaly_Detection_Bundle.md`](F07_Anomaly_Detection_Bundle.md)
**Purpose:** Name every detector F07 unions, event-only (no "live value" framing like F01). This is a composition map, not a dataset pack.

## 1. Sources

| Engine / pack | Event it emits | Role in the union |
|---|---|---|
| Demand supply layer / F02 | `md_risk` | MD trajectory anomaly |
| Idle-graph / F04 (OI-57, planned) | idle/waste event | Lazy-idle anomaly |
| Pressure-graph / F05 (OI-59, planned) | leak-proxy event | Pressure decay anomaly |
| Vibration-graph / F06 (OI-58, planned) | vibration-zone event | Mechanical zone anomaly |
| Stage-A PdM (`predictive_maintenance.py`) | `maintenance_risk` | Optional electrical Health Index anomaly |

## 2. Aggregation logic

**Union list, no arbitration.** F07 concatenates whatever events are currently active across the five sources above into one anomaly list — it does not rank, merge, or resolve conflicts between them (that is F09's job). Directly reuses the OI-61 scenario-test framing already in `F07_Anomaly_Detection_Bundle.md`: each detector must be independently provable on its own fixture set before F07's union test proves anything.

## 3. Current status

Matches `INTEGRATION_MODULE_MAP.md` §2 today: only F02 (`md_risk.py`) and Stage-A PdM (`predictive_maintenance.py`) have real code; F04/F06 are docs-first (dataset TBD); F05 Pressure-graph is docs-first with MetroPT-3 fixtures (`pressure.v1`). OI-61 (unit tests against injected scenarios) has not started — it needs at least F02 + one more detector coded to be meaningful.

## 4. Future: orchestration layer

Once all five sources emit real events, the union logic here is exactly what the future orchestration/connector service performs as its first step (fan-in), before F09 arbitrates. See `INTEGRATION_MODULE_MAP.md` §7.
