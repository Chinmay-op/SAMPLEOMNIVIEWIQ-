# F03 — Day-ahead 96-slot demand plan (`demand_forecast`)

**POC stance:** Should / demo (not the live-MD hero)  
**HITL:** Plan for humans — not closed-loop scheduling  
**Nodes:** Bottle feed history when available; heta/campus train only with `synthetic: true`

## Problem

Live `md_risk` answers “this window.” The plant also needs a **next-day** slot-by-slot demand outlook for planning. Building that from scratch would ignore the already-proven HD-graph 96-slot engine.

## Solution

Reuse HD-graph day-ahead path: aggregate history to 15‑min slots, train **96 slot-specific** quantile models (Q75) with ×1.02 safety buffer, emit Layer3 `demand_forecast`. Do **not** claim LSTM or auto peak-shaving from marketing blur.

## What

- 96 predictions for tomorrow (`slot_of_day` 0..95)
- Features: time, holiday (MH), lags, weather (retarget lat/lon to Pune later)
- Optional DSM-style deviation bands for **sim labeling only** — not MSEDCL MD surcharge table

## Why

Complements F02: day-ahead plan + live window. Can demo on labeled history before bottle has enough days; retrain on site data when available.

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| Historical electrical series | Train / predict input |
| Lead demand package (extract from HD-graph) | Train-slots + predict |
| Dashboard | Optional day-ahead chart |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-42](https://mightium.atlassian.net/browse/OI-42) | Layer3 includes `demand_forecast` contract |
| — | No dedicated day-ahead ticket; Lead **HD demand package** extract per blueprint §9 |
| [OI-43](https://mightium.atlassian.net/browse/OI-43) | Site contract / history for honest production use |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Same electrical stream, stored as history |
| Functions | Slot aggregate → feature builder → day-ahead predict API |
| Algorithms | 96× XGBoost `reg:quantileerror` α=0.75; ×1.02 buffer; direct multi-step. Progressive train = retrain-on-history, not online RUL |

## Benefits

- Tomorrow’s demand shape for planning
- Same HD terminology as live window
- Clear honesty when models are campus/synthetic

## End goal (done when)

- Offline demo emits Layer3-shaped `demand_forecast` (96 slots)
- Campus/heta runs marked `synthetic: true`
- Documented path to retrain on bottle history

## Code / doc pointers

- HD-graph: `energy_model.py`, `features_service.py`, `docs/MERC_Strategy_Blueprint.md`
- Blueprint §3.2 — `Docs/DS/HD_graph_Master_Demand_Blueprint.md`
- Layer3 §4.1b `demand_forecast`
