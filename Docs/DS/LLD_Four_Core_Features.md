# LLD — Four core features

**Status:** Accepted for Sprint 5  
**Date:** 26 October 2026  
**PRD:** [PRD_Four_Core_Features.md](PRD_Four_Core_Features.md)  
**HLD:** [HLD_Four_Core_Features.md](HLD_Four_Core_Features.md)

This is the implementation cut. It names modules that exist in this repo and the Jira issues that carry the work. It does not add formulas.

## 1. Shared types

A feature result is a Layer 3 style dict the action-card generator already accepts.

| Field | Meaning |
|---|---|
| `event_type` | Which suggestion this is |
| `machine_id` / `device_id` | POC node: `isbm-main-feed` or `hp-compressor` |
| `timestamp` | Event time |
| `synthetic` | True for bots, replay, campus history, public datasets |
| `recommended_action` | What the person should do |
| `do_not` | What they should not do, including any actuation |

`ActionCardGenerator.generate_card` in `src/omniview/rules/action_cards.py` turns that dict into the card. Sprint 5 adds event types. It does not add a second card type.

Sensor payloads keep the envelope in [DevB_DevC_Model_Plug_Requirements.md](DevB_DevC_Model_Plug_Requirements.md): `device_id`, `timestamp`, `sensor_type`, `schema_version`, `data`. Short topic type and long `sensor_type` stay a map.

## 2. Feature 1 — Site safety

**Read.**

| Stream | Module | Fields used |
|---|---|---|
| Ambient | `src/omniview/edge/bots/ambient_bot.py` | ambient temperature |
| Electrical | `src/omniview/edge/bots/electrical_bot.py` | voltage, current, consumption |
| Gas reading | `src/omniview/edge/bots/gas_bot.py` | fumes / gas reading already in `schemas/gas_schema.json` |
| Thermal state | `src/omniview/edge/bots/thermal_bot.py` | barrel or box temperature |
| Production rate | feature 4 stroke count | consumption per stroke |

SSR and MCB status is an input on the electrical payload. The bot may emit it as a synthetic status. The card must say the status is synthetic.

**Emit.** `event_type` one of `electrical_waste`, `fire_indication`, `unnecessary_thermal`, `temperature_spike`, `insulation_break`.

**Do not call.** The gas-model stories on the board. They are not this feature.

**Tests.** A synthetic triple (ambient + electrical + gas) that yields one of the five event types, and a quiet triple that yields none. Card text contains a human action and no actuation.

## 3. Feature 2 — Instrument health

**Read.**

| Input | Module | Call |
|---|---|---|
| Vibration pattern | `src/omniview/rules/vibration_zone.py` | `evaluate_vibration_zone` |
| Health prediction | `src/omniview/rules/predictive_maintenance.py` | `run_stage_a_pipeline`, `predict_maintenance_risk` |
| Running hours, daily output | stroke bot count and electrical energy over the day | composed, not a new index |
| Last maintenance | OI-64 log, when that log exists | until then the fixture timestamp is explicit |
| Cooling vs energy | electrical power and the cooling temperature from feature 4 | comparison only |

`ZONE_EDGES_MMS` is a placeholder (`ZONE_IS_PLACEHOLDER = True`). Do not replace it with a class table in this sprint.

Stage A inputs and outputs stay the OI-62 PRD. `DEMO_PRIORS` stays labeled.

**Emit.** Existing `maintenance_risk`, plus `cooling_malfunction` when energy is high and cooling temperature is low. The card says service or inspect. It does not stop the machine.

**Tests.** Existing `tests/test_predictive_maintenance.py` stay green. One new case for `cooling_malfunction` on a synthetic pair of rows.

## 4. Feature 3 — Maximum demand

**Now, already specified.**

| Piece | Call |
|---|---|
| 15-minute window | `DemandWindowState.update` in `demand_window.py` |
| Instant kVA | `instant_kva` |
| Minute-11 alert | `evaluate_md_risk` in `md_risk.py` |
| Contract kVA | `get_contract_demand_kva` — placeholder until OI-43 |

**Tomorrow.** Call the HD-graph day-ahead engine. Entry points named by the blueprint:

- `HD-graph/webapp/backend/energy_model.py`
- `HD-graph/webapp/backend/features_service.py`

96 slots, same formulation, `synthetic: true` when the history is not this plant. Do not add a model under `src/omniview/predictive/` that reimplements it.

**Health attachment.** If feature 2 reports a machine down for service, drop that machine’s labeled share from the affected slots. The share is an input value on the machine record. It is not a new demand equation.

**Fine line.** The card’s rupee string stays the placeholder already used by `ActionCardGenerator` until OI-43. The numbered suggestions are text actions (shift a run, cut auxiliary load). They are not executed.

**Tests.** Existing minute-11 tests stay. One test that a 96-slot call returns 96 slots and carries `synthetic: true` on campus history. One test that a “machine in maintenance” flag reduces the labeled share and does not change the HD-graph function.

## 5. Feature 4 — Consumption, production, and waste

**Read.**

| Input | Call |
|---|---|
| Lazy-idle waste | `evaluate_lazy_idle` in `lazy_idle.py` |
| Loaded pressure | `evaluate_pressure_leak` in `pressure_leak.py` |
| Production rate | `src/omniview/edge/bots/stroke_bot.py` stroke count |
| Demand plan | feature 3 slot report |
| Health | feature 2 service flag |
| Thresholds | `get_idle_current_threshold_a`, `get_idle_temp_threshold_c` — placeholders |

**Emit.** `waste_schedule` with:

- `machine_id`
- `best_run_hour`
- `stop_hour`
- `waste_where` (`lazy_idle` or `pressure_loaded` or `cooling`)
- `production_rate`
- `synthetic`

The hour choice is a ranking of the existing signals inside the demand plan. It is not a new optimizer.

**Tests.** Existing `tests/test_lazy_idle.py` and `tests/test_pressure_leak.py` stay green. One test that a synthetic day with a lazy-idle stretch produces a `waste_schedule` naming that stretch.

## 6. Jira

Epics created for this cut. Children are reparented onto them. Old epics A–H stay on the board. They are the earlier workstreams, not the product.

Sprint 5 (id 906) receives only the rows marked Sprint 5. Platform rows stay in the backlog.

### Sprint 5 — existing issues

| Epic | Keys |
|---|---|
| Site safety | OI-93. OI-116, OI-118, OI-119, OI-120, and OI-121 were closed as duplicates of OI-137. |
| Instrument health | OI-25, OI-58, OI-63, OI-64, OI-65, OI-67. OI-1 was closed as a duplicate of OI-65. |
| Maximum demand | OI-56, OI-96 |
| Consumption, production, waste | OI-57, OI-59, OI-98 |

Epic keys: site safety **OI-132**, instrument health **OI-135**, maximum demand **OI-136**, consumption and waste **OI-133**, platform **OI-134**.

### Sprint 5 — issues added with this LLD

| Epic | Issue | Work |
|---|---|---|
| OI-132 | [OI-137](https://mightium.atlassian.net/browse/OI-137) | Emit `electrical_waste`, `fire_indication`, `unnecessary_thermal`, `temperature_spike`, `insulation_break` |
| OI-132 | [OI-138](https://mightium.atlassian.net/browse/OI-138) | Gas reading as an input through `gas_bot` and `schemas/gas_schema.json` |
| OI-135 | [OI-145](https://mightium.atlassian.net/browse/OI-145) | `cooling_malfunction` from high energy and low cooling temperature |
| OI-136 | [OI-146](https://mightium.atlassian.net/browse/OI-146) | 96-slot call into the HD-graph day-ahead engine |
| OI-136 | [OI-147](https://mightium.atlassian.net/browse/OI-147) | Numbered suggestions on the card. Fines remain placeholder. |
| OI-133 | [OI-139](https://mightium.atlassian.net/browse/OI-139) | `waste_schedule` from lazy-idle, pressure, stroke rate, health, and the demand plan |

### Backlog — parented, not in Sprint 5

| Epic | Keys or new issue | Why it waits |
|---|---|---|
| Site safety | OI-119 closed | Same correlation goal as OI-137. |
| Instrument health | OI-66 | CUSUM retune on real plant history. Stage A already runs. |
| Maximum demand | OI-43, OI-70 | Site tariff and contract kVA. Placeholder until OI-43. |
| Consumption, production, waste | OI-49 closed | Same stroke-bot goal as OI-98. Ambient replay stays OI-93. |
| Platform | OI-14, OI-15, OI-81, OI-82, OI-95, OI-78 | Communication line, after the features. OI-78 is live Modbus. |
| Platform | OI-60 | Priority among cards. Not the JSON rule pack. |
| OI-134 | [OI-140](https://mightium.atlassian.net/browse/OI-140) | External JSON rules, one pack for electrical and one for production |
| OI-134 | [OI-141](https://mightium.atlassian.net/browse/OI-141) | Edge suggestion within seconds, forwarded to people |
| OI-134 | [OI-142](https://mightium.atlassian.net/browse/OI-142) | Edge-to-edge between blocks |
| OI-134 | [OI-143](https://mightium.atlassian.net/browse/OI-143) | Sandbox for one suggestion on a snapshot |
| OI-134 | [OI-144](https://mightium.atlassian.net/browse/OI-144) | Digital twin of the four features, updated from the sandbox |

### Left where they are

Gas-model build, one of each: OI-48, OI-106, OI-110, OI-115, OI-128. Closed copies: OI-122, OI-123, OI-124, OI-129, OI-130, OI-131.  
Audit: OI-125 remains. OI-126 was the same report. OI-127 is Done because the tasks now exist.  
Anomaly: OI-94 was closed as the same goal as OI-99. OI-97 and OI-99 stay open.  
Docs and site capture: OI-44, OI-79, OI-80.  
Scenario injector OI-50 and the three-scenario test OI-61 stay on their current parents. They are useful later. They are not the feature contract.

## 7. Build order inside the sprint

1. Parent the existing rows onto the four epics.
2. Feature 3 live path is already `evaluate_md_risk`. Land the 96-slot bridge next to it, without a new model.
3. Feature 4 `waste_schedule` uses lazy-idle, pressure, and stroke. Those three already have modules.
4. Feature 2 adds only `cooling_malfunction` beside `predict_maintenance_risk`.
5. Feature 1 composes ambient, electrical, gas, and thermal into the five event types.
6. Each new event type gets one card template in `CARD_TEMPLATES`. Rupee text stays placeholder.
7. `pytest` for the existing modules plus the four new cases. No MQTT in this sprint.
