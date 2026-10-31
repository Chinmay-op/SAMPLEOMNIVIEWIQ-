# POC Feature Specs — Bottle Factory (truth pack)

**Site:** ISBM-PET bottle manufacturing, Pune  
**Nodes:** `isbm-main-feed`, `hp-compressor`  
**Mode:** Human-in-the-Loop only — recommendations / action cards; **no auto-actuation**  
**Not in this pack:** full-plant twin, campus generators, carbon/blockchain, enterprise RBAC as POC headline  

This folder is the **POC-truth** feature list. Marketing blur in [`Docs/POC-fetures.md`](../POC-fetures.md) may overclaim; prefer these specs for build and client scope.

## Index

| ID | Document | Stance | Companion doc |
|----|----------|--------|---------------|
| F01 | [Live monitoring + dashboard / jumbo](F01_Live_Monitoring_Dashboard_Jumbo.md) | Must | [Connector](F01_CONNECTOR.md) — consumption map |
| F02 | [Live 15‑min MD + `md_risk`](F02_Live_MD_Risk.md) | Must — hero | [Demand supply layer](../Demand_Supply_Layer_Plan.md) — HD-graph fetch boundary |
| F03 | [Day-ahead 96-slot forecast](F03_DayAhead_96_Slot_Forecast.md) | Should / demo | [Demand supply layer](../Demand_Supply_Layer_Plan.md) — same fetch boundary as F02 |
| F04 | [Lazy-idle waste](F04_Lazy_Idle_Waste.md) | Must | [Idle-graph](../../../Idle-graph/) — data pack, ziya07/sensor-maintenance-dataset |
| F05 | [Compressor pressure leak](F05_Compressor_Pressure_Leak.md) | Must | [Pressure-graph](../../../Pressure-graph/) — data pack, MetroPT-3 only |
| F06 | [Vibration ISO zones](F06_Vibration_ISO_Zones.md) | Must | [Vibration-graph](../../../Vibration-graph/) — data pack, dataset TBD |
| F07 | [Anomaly bundle ± HI Stage A](F07_Anomaly_Detection_Bundle.md) | Must (composed) / Stage A optional wave | [Connector](F07_CONNECTOR.md) — composition map |
| F08 | [Thin live twin](F08_Thin_Live_Twin.md) | Must (dashboard status) | [Connector](F08_CONNECTOR.md) — status-source map |
| F09 | [Conflict what-if → action card](F09_Conflict_WhatIf_Action_Card.md) | Should | [Connector](F09_CONNECTOR.md) — event-source + playbook map |
| — | [**Integration module map**](INTEGRATION_MODULE_MAP.md) | How modules plug together | §7 — future orchestration layer |

## Template (every F0N file)

Problem → Solution → What → Why → Where → Jira → Sensors/functions/algorithms → Benefits → End goal → Code/doc pointers

## Build order (summary)

See [INTEGRATION_MODULE_MAP.md](INTEGRATION_MODULE_MAP.md): **F02 → F01/F08 pipe → F04/F05/F06 → F07 → F09 → F03**.
