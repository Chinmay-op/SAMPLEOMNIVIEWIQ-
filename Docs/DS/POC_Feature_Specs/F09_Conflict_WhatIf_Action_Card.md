# F09 — Conflict what-if → one HITL action card

**POC stance:** Should — thin arbitration sandbox  
**HITL:** **Recommend only** — never auto-actuate  
**Nodes:** Conflicts among alerts on POC assets (e.g. vib critical + MD near limit)

## Problem

Two correct isolated actions can fight (e.g. hard stop for vib vs keep load under MD). Firing two competing alerts leaves the plant manager to reconcile under time pressure.

## Solution

Layer 4 **conflict arbitration**: when competing goals fire, evaluate a **small set of pre-authored playbooks** against a **read-only telemetry snapshot** (seconds, not a general physics solver). Priority: **Safety > Compliance > Cost**. Output **one** action card.

This is **not** the FMI “simulate any scenario” sandbox from marketing docs.

## What

- Detect concurrent conflicting event types
- Run playbook candidates in <2–5 s budget (leave minutes for human inside MD window)
- Emit single consolidated recommendation for dashboard / push (OI-69)

## Why

POC architecture requires believable HITL under dual faults; credibility comes from bounded playbooks, not open-ended simulation claims.

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| Cloud intelligence / arbitration unit | Playbook eval |
| Dashboard action-card UI | Human ack / decision |
| Docs | What-If feasibility note |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-60](https://mightium.atlassian.net/browse/OI-60) | Conflict arbitration / priority |
| [OI-69](https://mightium.atlassian.net/browse/OI-69) | Action-card UI |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Indirect — consumes events from F02/F04/F05/F06 (+ Stage A) |
| Functions | Conflict detector, playbook scorer, action-card composer |
| Algorithms | Priority ordering + arithmetic checks on snapshot (e.g. does shed X kW bring projected MD under contract) |

## Benefits

- One clear instruction under stress
- Safety never overruled by cost
- Defensible POC claim vs “simulate anything”

## End goal (done when)

- At least one authored conflict class (vib critical vs MD risk) produces a single card
- Latency budget documented and met in demo
- Explicit non-claim: not FMI general sandbox

## Code / doc pointers

- `Docs/architeture/OmniView_IQ_WhatIf_Sandbox_and_EdgeCloud_Split.md`
- PRD / architecture LLA arbitration
- Layer3 consumers: action cards
