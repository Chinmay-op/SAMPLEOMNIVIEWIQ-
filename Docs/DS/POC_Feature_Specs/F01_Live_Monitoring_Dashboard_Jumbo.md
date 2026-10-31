# F01 — Live monitoring of two nodes + dashboard / jumbo

**POC stance:** Must  
**HITL:** Display and alerts only — no auto-actuation  
**Nodes:** `isbm-main-feed`, `hp-compressor`

## Problem

The bottle plant has no live digital view of the POC assets. Energy and machine health appear only after the monthly bill or a breakdown. Operators and the plant manager cannot see current kVA, warnings, or node health at a glance.

## Solution

Non-invasive sensors on the two POC nodes stream into edge → MQTT → TSDB. A live dashboard (and shop-floor jumbo) shows hero metrics and active warnings for those nodes only — not the whole factory.

## What

- Continuous poll of electrical (≤15 s) and physical (≤60 s) signals on the two nodes  
- Live dashboard with PRD hero metrics (live kVA vs contract, waste signals, action cards)  
- Optional jumbo LED feed of live kVA / active warnings near the panel  

## Why

Without a live surface, `md_risk` and other events never reach a human in time. FR8 requires a demo-able dashboard and at least one action card during the pilot.

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| MCC / feeder panels | Selec MFM + CTs on ISBM feed and compressor |
| Shop floor near panel | Jumbo display (glanceable) |
| Cloud / local UI | Plant-manager dashboard |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-68](https://mightium.atlassian.net/browse/OI-68) | Live dashboard shell |
| [OI-72](https://mightium.atlassian.net/browse/OI-72) | Jumbo Modbus feed stub |
| [OI-41](https://mightium.atlassian.net/browse/OI-41) | Repo / stack scaffold |
| [OI-51](https://mightium.atlassian.net/browse/OI-51) | MQTT |
| [OI-54](https://mightium.atlassian.net/browse/OI-54) | TSDB |
| [OI-23](https://mightium.atlassian.net/browse/OI-23) | Electrical schema |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Selec MFM384 + split-core CTs; vib/temp/pressure as other features need |
| Functions | Ingest, latest-by-`machine_id` queries, dashboard widgets, jumbo register map |
| Algorithms | None beyond display of live values + subscribed Layer3 events |

## Benefits

- Operators see MD proximity without opening a bill  
- Plant manager has one place for POC proof  
- Same pipe feeds F02–F09 events  

## End goal (done when)

- Both nodes show live readings on dashboard  
- Jumbo (or stub) can show live kVA / warning  
- At least one Layer3-driven action card visible in the pilot window  

## Code / doc pointers

- PRD FR1–FR2, FR8, §2.6 heroes — `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`  
- Architecture HLA/LLA — `Docs/architeture/OmniView_IQ_POC_Architecture_High_and_Low_Level.md`  
- Sensors — `Docs/OmniView_IQ_Sensor_Summary_CEO.md`
