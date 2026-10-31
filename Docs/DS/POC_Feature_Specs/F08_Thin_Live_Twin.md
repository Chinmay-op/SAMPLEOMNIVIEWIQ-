# F08 — Thin live twin (instrumented asset status)

**POC stance:** Must as **dashboard live status** of two nodes — not FMI full-plant twin  
**HITL:** Visibility only  
**Nodes:** `isbm-main-feed`, `hp-compressor`

## Problem

Stakeholders ask for a “digital twin.” A full FMI multi-physics plant model is out of POC scope and not needed to prove MD/idle/leak/vib. They still need a **live status** of what is instrumented.

## Solution

**Thin twin:** latest telemetry + derived states for the two POC `machine_id`s (online/offline, last values, active alerts). Same TSDB/dashboard as F01 — no separate physics engine.

## What

- Per-node status card: last kVA/kW/PF, temp/pressure/vib if present, alert badges
- Topology = two nodes + panel, not whole factory graph
- Explicitly **not** FMI-compliant plant simulation (see marketing `Docs/POC-fetures.md`)

## Why

Gives “live factory status” language without overbuilding. Supports F09 snapshot inputs.

## Where (site / nodes / UI surface)

Dashboard asset pane; optional jumbo subset; data from TSDB latest points.

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-68](https://mightium.atlassian.net/browse/OI-68) | Live dashboard (status surfaces) |
| [OI-54](https://mightium.atlassian.net/browse/OI-54) | TSDB / hypertables for latest reads |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | All POC sensors feeding the two nodes |
| Functions | Latest-by-node query, status aggregation |
| Algorithms | None beyond last-value + alert join |

## Benefits

- Honest “twin” story for POC demos
- Single place to see instrumented asset health
- Avoids FMI delivery risk in 3-week pilot

## End goal (done when)

- Both nodes show live status + last readings
- Stale/offline detectable (timestamp freshness)
- Docs never equate this to full-plant FMI twin

## Code / doc pointers

- What-If doc §A.1 — `Docs/architeture/OmniView_IQ_WhatIf_Sandbox_and_EdgeCloud_Split.md`
- F01 dashboard
- Architecture HLA
