# F01 connector — dashboard / jumbo consumption map

**Companion to:** [`F01_Live_Monitoring_Dashboard_Jumbo.md`](F01_Live_Monitoring_Dashboard_Jumbo.md)
**Purpose:** Name every upstream engine F01 reads from and what shape it expects, so the dashboard/jumbo layer has one place to check instead of re-deriving source lists per screen. This is a **consumption map**, not a dataset pack — F01 owns no raw sensor data of its own.

## 1. Sources

| Engine / pack | Event or data it emits | What F01 does with it |
|---|---|---|
| Demand supply layer ([`Demand_Supply_Layer_Plan.md`](../Demand_Supply_Layer_Plan.md)) | Live `kva`/`projected_demand_kva`/`T_minutes` + `md_risk` event | Hero "live kVA vs contract" metric; MD action card |
| Demand supply layer (day-ahead) | `demand_forecast` (96 slots) | Optional forecast chart |
| [`Idle-graph/`](../../../Idle-graph/) rule output (OI-57, planned) | idle/waste event | Waste % hero, idle card |
| [`Pressure-graph/`](../../../Pressure-graph/) rule output (OI-59, planned) | leak-proxy event | Leak card / waste narrative |
| [`Vibration-graph/`](../../../Vibration-graph/) rule output (OI-58, planned) | vibration-zone event | Zone badge |
| Stage-A PdM ([`predictive_maintenance.py`](../../../src/omniview/rules/predictive_maintenance.py)) | `maintenance_risk` | HI trend, optional card |

## 2. Aggregation logic

F01 does **latest-by-`machine_id` + active-alerts join**: for each of the two POC nodes (`isbm-main-feed`, `hp-compressor`), show the most recent value from each source above, plus any currently-active event from that source. No cross-source math happens in F01 itself — that's F07 (union) and F09 (arbitration). F01 is a straight fan-in display layer.

## 3. Current status

| Source | Live/coded | Planned |
|---|---|---|
| Demand supply layer (live) | F02 rule extracted (`md_risk.py`); supply-layer wrapper not yet built | Phase 2 of `Demand_Supply_Layer_Plan.md` |
| Demand supply layer (forecast) | Not extracted from `HD-graph/` | Phase 1 of `Demand_Supply_Layer_Plan.md` |
| Idle-graph | Docs-first only; no rule code | OI-57, after dataset chosen |
| Pressure-graph | Docs + OI-59 offline rules + MetroPT fixtures | MQTT/UI bind still open |
| Vibration-graph | Docs-first only; no rule code | OI-58, after dataset chosen |
| Stage-A PdM | Coded, fixture-proven | Wired to F01 not yet done |
| Dashboard shell itself | Not built (OI-68) | DevC |

## 4. Future: orchestration layer

Once F02, F04 (Idle-graph), F05 (Pressure-graph), F06 (Vibration-graph), and Stage-A PdM all emit real Layer3 events (live or replay), a single orchestration/connector service should replace F01 fetching each source independently — this doc, along with `F07_CONNECTOR.md`/`F08_CONNECTOR.md`/`F09_CONNECTOR.md`, becomes that service's spec input. Not built in this slice; see `INTEGRATION_MODULE_MAP.md` §7.
