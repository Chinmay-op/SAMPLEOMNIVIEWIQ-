# F05 — Compressor pressure leak proxy

**POC stance:** Must  
**HITL:** Leak recommendation card — no auto compressor trip  
**Nodes:** `hp-compressor`

## Problem

Compressed-air leaks and “fighting the leak” can waste a large share of compressor electrical energy. Gauge checks are intermittent; continuous decay while loaded is easy to miss.

## Solution

Monitor receiver/manifold pressure. If pressure **decays while the compressor remains loaded**, treat as a **leak proxy** and alert (FR6). Detailed build/hold cycle analytics can come later on the same signal.

## What

- Continuous pressure (bar) from existing gauge port tap
- Correlate with compressor loaded state (electrical or run signal)
- Emit pressure-leak style Layer3 event for HITL

## Why

POC must prove a measured path to compressor phantom-run / leak waste (PRD goals).

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| Compressor output receiver / gauge port | WIKA (or equiv.) 0–40 bar transmitter |
| Electrical on compressor feed | Loaded vs unloaded context |
| Dashboard | Leak alert / waste narrative |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-59](https://mightium.atlassian.net/browse/OI-59) | Pressure-decay leak proxy |
| [OI-50](https://mightium.atlassian.net/browse/OI-50) | Pressure-leak scenario injector |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | WIKA A-10 (0–40 bar) or equivalent; compressor electrical |
| Functions | Decay-rate while loaded detector |
| Algorithms | Slope/threshold on pressure under load; site-tuned |

## Benefits

- Early leak visibility without full pneumatic audit
- Supports ₹ waste story for compressor
- Non-invasive gauge-port install

## End goal (done when)

- Injected or real decay-while-loaded triggers alert
- Event honest about proxy (not full leak localization)
- Linked to `hp-compressor` `machine_id`

## Code / doc pointers

- Data pack (contract, MetroPT map, fixtures) — [`Pressure-graph/`](../../../Pressure-graph/)
- Adapter — `src/omniview/pressure/ingest.py`
- Rules — `src/omniview/rules/pressure_leak.py`, `pressure_live.py` (OI-59)
- Demo — `scripts/demo_pressure_leak.py`
- PRD FR6 — `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`
- Sensor summary — `Docs/OmniView_IQ_Sensor_Summary_CEO.md`
- Layer3 `pressure_leak` — `Docs/architeture/Layer3_Model_Layer_Technical_Architecture.md` §4.3
