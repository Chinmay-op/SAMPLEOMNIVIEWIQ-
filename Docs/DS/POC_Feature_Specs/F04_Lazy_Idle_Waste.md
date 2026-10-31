# F04 — Idle / lazy-idle waste detection

**POC stance:** Must (detection); full idle/working/cooldown/stop timeline matures later  
**HITL:** Waste alert / action card — no auto heater control  
**Nodes:** ISBM thermal + electrical (`isbm-main-feed` correlated)

## Problem

Heaters/barrel can stay hot while the machine is not producing (“lazy idle”) — energy waste and restart scrap risk. Without sensors, this is invisible until quality or the bill suffers.

## Solution

Detect **lazy idle**: elevated barrel/zone temperature while current indicates idle/low load, for ≥15 minutes; emit a Layer3-style idle/waste event for HITL.

## What

- Correlate surface/process temp with electrical current on the ISBM node
- Flag onset within ~15 minutes (FR5)
- Capture idle/changeover windows for ₹ waste baseline
- Timeline of richer states (working / cooldown / stop) = later maturity on same data

## Why

Proves phantom thermal/idle waste with site-captured data — core POC goal.

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| ISBM barrel / hot-runner zone | Temp probe |
| ISBM electrical feed | Current / kW for idle vs load |
| Dashboard | Waste % / action card |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-57](https://mightium.atlassian.net/browse/OI-57) | Lazy-idle detector |
| [OI-50](https://mightium.atlassian.net/browse/OI-50) | Lazy-idle scenario injector |
| [OI-79](https://mightium.atlassian.net/browse/OI-79) | Capture/validate real idle + lazy-idle on site |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Banner surface/RTD temp; MFM current/kW |
| Functions | Rule: temp high AND current idle for duration ≥ threshold |
| Algorithms | Threshold / duration heuristic (site-calibrated); not ML RUL |

## Benefits

- Quantifiable idle waste for plant manager
- Ties to hero “high-waste idling motor load %”
- Feeds monetize (OI-70) once tariff known

## End goal (done when)

- Injected or real lazy-idle flagged within ~15 min of onset
- Event carries `synthetic` when test-injected
- At least one captured window usable for ₹ narrative

## Code / doc pointers

- Data pack (contract, ziya07 map, fixtures) — [`Idle-graph/`](../../../Idle-graph/)
- Adapter — `src/omniview/idle/ingest.py`
- Rule — `src/omniview/rules/lazy_idle.py` (OI-57)
- Demo — `scripts/demo_lazy_idle.py`
- PRD FR5, goals §2.2 — `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`
- Layer3 idle event contracts
- Sensor placement — `Docs/sesnor-fetures.md`
