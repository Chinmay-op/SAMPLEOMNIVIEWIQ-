# F07 — Anomaly detection bundle (MD, idle, pressure, vib ± HI Stage A)

**POC stance:** Must as **composed** detectors; PdM Stage A = optional next wave  
**HITL:** Unified anomaly/action presentation — no closed-loop control  
**Nodes:** `isbm-main-feed`, `hp-compressor`

## Problem

“Anomaly detection” sounds like one AI box. In this POC it is several **named** detectors. Clients also ask about predictive maintenance; Stage A Health Index is the honest first step — not RUL.

## Solution

Treat anomalies as the **union** of F02/F04/F05/F06 outputs, plus optional electrical **PdM Stage A** (HI + slopes + CUSUM → `maintenance_risk`). Do **not** claim generation/radiation anomalies or registry carbon. Scenario unit tests (OI-61) prove detectors on labeled injectors.

## What

| Signal family | Detector | Event |
|---------------|----------|-------|
| MD trajectory | F02 | `md_risk` |
| Lazy-idle | F04 | idle/waste event |
| Pressure decay | F05 | leak proxy event |
| Vib zones | F06 | vibration zone event |
| Electrical HI (optional) | Stage A module | `maintenance_risk` |

## Why

Keeps scope honest: each anomaly has a sensor path and a Jira ticket. Stage A reuses notebook math without promising failure dates.

## Where (site / nodes / UI surface)

Same instrumented nodes as F02–F06; dashboard anomaly list / action cards; Stage A batch may run daily offline first.

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-56](https://mightium.atlassian.net/browse/OI-56) / [OI-57](https://mightium.atlassian.net/browse/OI-57) / [OI-58](https://mightium.atlassian.net/browse/OI-58) / [OI-59](https://mightium.atlassian.net/browse/OI-59) | Core anomaly detectors |
| [OI-62](https://mightium.atlassian.net/browse/OI-62) | PdM Stage A module |
| [OI-61](https://mightium.atlassian.net/browse/OI-61) | Unit tests against injected scenarios |
| [OI-1](https://mightium.atlassian.net/browse/OI-1) | PdM Stage 0/A umbrella |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Electrical + temp + pressure + vib (POC set) |
| Functions | Each F0x rule module; `predict_maintenance_risk` for Stage A |
| Algorithms | Window projection; temp+current heuristic; pressure slope; ISO bands; HI vs priors + CUSUM (Stage A) |

## Benefits

- Clear accountability per anomaly type
- Testable with OI-50 injectors
- Stage A upgrade path without fake RUL claims

## End goal (done when)

- Each Must detector can fire from fixture or live
- OI-61 covers MD + lazy-idle + leak at minimum
- Stage A demo optional but labeled unsupervised Stage A

## Code / doc pointers

- `src/omniview/rules/md_risk.py`, `predictive_maintenance.py`
- `Docs/DS/OI-62_Predictive_Maintenance_Module_PRD.md`
- Specs F02, F04, F05, F06
