# F09 connector — conflict what-if event-source + playbook map

**Companion to:** [`F09_Conflict_WhatIf_Action_Card.md`](F09_Conflict_WhatIf_Action_Card.md)
**Purpose:** Name every event source F09 arbitrates over, and define the playbook data shape referenced but not specified in F09's existing spec.

## 1. Sources

| Engine / pack | Event it emits | Role in arbitration |
|---|---|---|
| Demand supply layer / F02 | `md_risk` | Compliance-class trigger (MD near-limit) |
| Idle-graph / F04 (OI-57, planned) | idle/waste event | Cost-class trigger |
| Pressure-graph / F05 (OI-59, planned) | leak-proxy event | Cost-class trigger |
| Vibration-graph / F06 (OI-58, planned) | vibration-zone event (zone D = critical) | Safety-class trigger |
| Stage-A PdM | `maintenance_risk` | Cost/maintenance-class trigger |

## 2. Aggregation logic — conflict detection → playbook → one card

1. **Detect concurrency:** two or more events above active on overlapping `machine_id`/time window.
2. **Classify each by priority tier:** Safety > Compliance > Cost (per F09's existing spec) — e.g. vibration zone D = Safety, `md_risk` = Compliance, idle/leak/PdM = Cost.
3. **Playbook lookup:** match the concurrent-event-type pair against a small pre-authored playbook table (not a general solver). Reference conflict class from `Vibration-graph/docs/MODEL_AND_RULES_BLUEPRINT.md`: vibration zone D + `md_risk` near-limit.
4. **Snapshot arithmetic check:** e.g. does the candidate action (shed X kW) bring `projected_demand_kva` under `contract_demand`, evaluated on a read-only telemetry snapshot within the <2–5s budget.
5. **Emit one action card** — never two competing cards for the same concurrency window.

### Playbook data shape (not defined elsewhere — captured here)

```text
Playbook {
  id: string
  trigger_pair: (event_type_a, event_type_b)   # e.g. (vibration_zone, md_risk)
  priority_class: Safety | Compliance | Cost     # of the winning trigger
  snapshot_checks: list[arithmetic check against current telemetry]
  recommended_action: string                     # human-readable, HITL — never auto-executed
  synthetic: bool                                # true if authored/tested against fixture events only
}
```

## 3. Current status

No playbooks authored yet (OI-60 not started); no conflict has ever fired since F04/F05/F06 have no live rule code yet. This doc's playbook shape is ready so OI-60 has a fixed target once at least two of the source detectors are coded.

## 4. Future: orchestration layer

Once F02/F04/F05/F06 (+Stage A) all emit real events, F09's conflict detection becomes a stage inside the orchestration/connector service rather than a standalone poller — see `INTEGRATION_MODULE_MAP.md` §7. Safety > Compliance > Cost ordering does not change when that happens.
