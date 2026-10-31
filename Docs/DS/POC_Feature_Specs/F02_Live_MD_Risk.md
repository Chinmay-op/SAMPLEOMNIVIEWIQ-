# F02 — Live 15‑min MD vs sanctioned + early warn (`md_risk`)

**POC stance:** Must — **hero**  
**HITL:** Alert / action card only — no auto load-shed  
**Nodes:** `isbm-main-feed` (primary), `hp-compressor` as applicable

## Problem

MSEDCL max demand is settled on a **15‑minute** window. A breach can lock a monthly penalty. Today the plant learns this from the bill — after the cost is locked.

## Solution

Reuse HD-graph live-window math: accumulate apparent power over the open 15‑min window, project end-of-window kVA, and emit `md_risk` when trajectory vs **sanctioned** `contract_demand` warrants alert with ≥4 min lead (target ~minute 11).

## What

- Rolling window: `kva`, `accumulated_kva_minutes`, `projected_demand_kva`, `T_minutes`
- Compare to site `contract_demand` (OI-43; placeholder until bills confirmed)
- Layer3 event `md_risk` with HD field names + `synthetic` when fixture/replay

## Why

POC goal #1: prove MD-penalty risk is detectable and avoidable before the window closes — with this site’s (or labeled demo) data.

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| Electrical feed of POC nodes | Source ticks |
| Edge / cloud rule engine | `DemandWindowState` + `evaluate_md_risk` |
| Dashboard / jumbo / action card | Human sees projected vs sanctioned |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-56](https://mightium.atlassian.net/browse/OI-56) | Rolling 15‑min kVA + MD trajectory alert |
| [OI-43](https://mightium.atlassian.net/browse/OI-43) | Confirm sanctioned MD / bills / nameplates |
| [OI-50](https://mightium.atlassian.net/browse/OI-50) | MD near-miss fixture (partial) |
| [OI-42](https://mightium.atlassian.net/browse/OI-42) | Layer3 contracts including `md_risk` |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Selec MFM384 + CTs (kW/VAR/kVA ≤15 s) |
| Functions | `instant_kva`, `DemandWindowState.update`, `run_series`, `evaluate_md_risk` |
| Algorithms | HD PowerMonitor: `projected = (accum + kva×remaining) / 15`; alert gate T≥11 and projected≥contract |

## Benefits

- Lead time to act inside the billing window
- Honest link to sanctioned MD once OI-43 filled
- Pluggable ingest: CSV today, MQTT later — same sample shape

## End goal (done when)

- Near-miss fixture/CSV alerts by ~min 11; quiet stays quiet
- Payload uses HD / Layer3 field names; `contract_demand` labeled if placeholder
- Live or replay path can feed dashboard action card

## Code / doc pointers

- `src/omniview/rules/demand_window.py`, `md_risk.py`
- `fixtures/demand/INGEST_CONTRACT.md`, `MD_POC_DEMO_SCRIPT.md`
- `Docs/DS/HD_graph_Master_Demand_Blueprint.md` §3.1
- Layer3 §4.1 `md_risk`
