# OI Sprint 5

**Board:** [OI board](https://mightium.atlassian.net/jira/software/projects/OI/boards/267)  
**Sprint:** OI Sprint 5 (id 906) on the [OI board](https://mightium.atlassian.net/jira/software/projects/OI/boards/267), state active  
**Window:** 27 October 2026 00:30 IST through 7 November 2026 18:00 IST  
**Deadline:** before Diwali, Sunday 8 November 2026  
**Specs:** [PRD](PRD_Four_Core_Features.md) · [HLD](HLD_Four_Core_Features.md) · [LLD](LLD_Four_Core_Features.md)

Sprint 5 holds **18** open issues after the duplicate pass. The sprint is active.

## Goal

Before Diwali: four attached features as suggestions only. Site safety, instrument health (Stage A, no new formula), 96-slot demand from the HD-graph engine, and the waste schedule. No actuation. External rules, edge-to-edge, sandbox, and the twin stay out.

## Epics

| Feature | Epic |
|---|---|
| Environment and Site Safety | [OI-132](https://mightium.atlassian.net/browse/OI-132) |
| Instrument Health / Wear and Tear | [OI-135](https://mightium.atlassian.net/browse/OI-135) |
| Maximum Demand | [OI-136](https://mightium.atlassian.net/browse/OI-136) |
| Consumption, Production, and Waste | [OI-133](https://mightium.atlassian.net/browse/OI-133) |
| Platform after the four features | [OI-134](https://mightium.atlassian.net/browse/OI-134) |

## In Sprint 5

| Epic | Issues |
|---|---|
| OI-132 Site safety | OI-93, OI-137, OI-138 |
| OI-135 Instrument health | OI-25, OI-58, OI-63, OI-64, OI-65, OI-67, OI-145 |
| OI-136 Maximum demand | OI-56, OI-96, OI-146, OI-147 |
| OI-133 Consumption and waste | OI-57, OI-59, OI-98, OI-139 |

## Backlog, parented, not in this sprint

| Epic | Issues | Why they wait |
|---|---|---|
| OI-135 | OI-66 | CUSUM retune on real history |
| OI-136 | OI-43, OI-70 | Site tariff still unconfirmed. Fines stay placeholder. |
| OI-134 | OI-14, OI-15, OI-60, OI-78, OI-81, OI-82, OI-95 | Communication line and alert priority |
| OI-134 | OI-140, OI-141, OI-142, OI-143, OI-144 | JSON rules, edge suggestion, edge-to-edge, sandbox, digital twin |
| Gas, one of each | OI-48, OI-106, OI-110, OI-115, OI-128 | The copies were closed |
| Other open | OI-26, OI-44, OI-50, OI-61, OI-79, OI-80, OI-97, OI-99, OI-125 | Not the same output as a sprint ticket |

## Closed as the same task or the same output

| Closed | Kept | Why |
|---|---|---|
| OI-116, OI-118, OI-119, OI-120, OI-121 | OI-137 | Spike, ambient-power correlation, surroundings correlation, and the ambient architecture / input-output pair are the site-safety suggestion. |
| OI-1 | OI-65, OI-67 | Umbrella only. The health number and the `maintenance_risk` event are the two remaining tasks. |
| OI-122, OI-123 | OI-106 | Three gas-architecture stories. |
| OI-124 | OI-110 | Two gas input-output stories. |
| OI-129, OI-130, OI-131 | OI-128 | Four gas-algorithm tests. |
| OI-126 | OI-125 | The same audit-report text. |
| OI-127 | OI-137 and the other new tasks | “Make the tasks from the audit” is done. |
| OI-49 | OI-98, OI-93 | Stroke-and-ambient bots. Stroke end-to-end is OI-98. Ambient replay is OI-93. |
| OI-94 | OI-99 | Anomaly identified and shown, and the anomaly integration test. |

Each closed issue is Done and linked Duplicate to the one that was kept, except OI-127, which Relates to OI-137.
