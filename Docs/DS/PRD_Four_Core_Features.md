# PRD — Four core features

**Status:** Accepted for Sprint 5  
**Date:** 26 October 2026  
**Source:** Feature meeting the same day (Dnyandev Sawarkar)  
**Deadline:** before Diwali, Sunday 8 November 2026  
**Site:** ISBM-PET bottle factory, Pune (MSEDCL HT-I). POC nodes `isbm-main-feed` and `hp-compressor`.  
**Companions:** [HLD](HLD_Four_Core_Features.md) · [LLD](LLD_Four_Core_Features.md) · [Sprint plan](OI_Sprint_5_HLD_Feature_Plan.md)

This PRD replaces the six-hardware split (thermal, vibration, ambient, pressure, demand, stroke as separate products). Those signals still exist. They are inputs. The product is four features that attach to each other.

## 1. Problem

A plant manager cannot tell fire risk, machine health, tomorrow’s demand, and wasted energy apart, because each signal is shown on its own. A hot barrel, a high current, a gas reading, and a stopped stroke line are one situation. Treating them as six products hides the suggestion.

## 2. Users

| User | What they set | What they receive |
|---|---|---|
| Electrical owner | Rules about waste, insulation, short circuit, demand fines | A suggestion, not a trip |
| Production / upper management | Rules about which machine runs, when to stop, when to service | A suggestion tied to production rate and health |
| Shift operator | Nothing in this sprint | The same suggestion, worded for the floor |

Each role keeps its own rule set. That engine is **not** this sprint. This sprint emits one suggestion per feature from the built-in rules. The external JSON rule packs come after.

## 3. Product rule

Nothing is independent. A feature consumes another feature’s output.

```text
Site safety ──waste, fire, thermal spike──► Instrument health
Instrument health ──service / breakdown risk──► Maximum demand
Maximum demand ──tomorrow’s energy, fine, suggestions──► Consumption, production, waste
Consumption, production, waste ──production rate, idle waste──► Site safety and health
```

Sensors are not the feature list. The feature input is a rate, a health result, or a report.

Suggestions only. “Shut the machine” and “turn the other AC on” are told to people. No auto-actuation.

## 4. Feature 1 — Environment and Site Safety

**Goal.** Avoid fire, electrical waste, short circuit, open wires, and other dangerous conditions.

**Inputs.**

- Ambient temperature for the area
- Gas / fumes near that area (harmful gas and CO₂ as a reading, not a separate gas-model product)
- Electricity: voltage, current, consumption
- Consumption against the production rate
- SSR and MCB status, or incoming status

**Outputs, each as a suggestion.**

- Electricity is being wasted
- Fire indication
- Unnecessary thermal
- Temperature spike
- Insulation break on a wire

**Acceptance.** Given a synthetic trace that combines ambient, electrical, and a gas reading, the feature emits at most the suggestions above, each with the condition that fired and the human action. It does not open a breaker.

## 5. Feature 2 — Instrument Health / Wear and Tear

**Goal.** Avoid last-minute malfunction. Service on time. Keep the production rate up while the machine runs.

**Inputs.**

- Electric consumption
- Vibration pattern
- Production rate
- Maintenance record: when it was last serviced
- Running status and hours
- Daily output and daily consumption

**Outputs, each as a suggestion.**

- Health prediction: when to service
- When a breakdown can come
- Whether consumption is high for the output
- Malfunction when energy is high and cooling temperature is low

**Acceptance.** The health number and the `maintenance_risk` event come from the Stage A module already specified in [OI-62](OI-62_Predictive_Maintenance_Module_PRD.md). This PRD does not add a new health formula. Priors stay `DEMO_PRIORS` until OI-63. The malfunction case is a comparison of the existing energy reading and the cooling temperature, reported as a suggestion.

## 6. Feature 3 — Maximum Demand

**Goal.** Predict the next day’s energy in 96 slots of 15 minutes. Stay on that prediction.

**Inputs.**

- Historic slot energy
- Current, temperature, energy consumption
- Production rate against the last rate
- Machine health: if a machine is about to stop, or is already in maintenance, the predicted demand comes down

**Outputs.**

- Maximum-demand report: use now, daily use, tomorrow’s energy by slot
- Fine now, predicted fine, and the fine that can be avoided
- A numbered list of suggestions (run one machine more, raise production, cut the AC)

**Acceptance.** The 96-slot forecast is the HD-graph day-ahead engine named in [HD_graph_Master_Demand_Blueprint.md](HD_graph_Master_Demand_Blueprint.md). This PRD does not define a second forecast. The live 15-minute breach warning stays `evaluate_md_risk` (minute 11). `CONTRACT_DEMAND_KVA` and every rupee figure stay labeled placeholders until OI-43 confirms site truth. Replay of campus history is `synthetic: true`.

## 7. Feature 4 — Consumption, Production, and Waste

**Goal.** Cut lazy-idle waste and idle-machine waste while running. More output from less consumption.

**Inputs.**

- Current and electricity use
- Machine health
- Production rate (stroke count)
- The maximum-demand report from feature 3
- Cooling and line pressure, including cooling efficiency

Pressure is an input here. It is not a fifth product. Cooling efficiency sits in this feature.

**Outputs.**

- Best time to run each machine
- The hour when the production rate is higher
- The hour when machines should stop
- Where the waste is, with the time

**Acceptance.** Lazy-idle uses `evaluate_lazy_idle`. Pressure-while-loaded uses `evaluate_pressure_leak`. The schedule report names the machine, the hour, and the waste. It does not start or stop equipment.

## 8. In this sprint

Sprint 5, before 8 November, delivers the four features on synthetic or replay data, as suggestions.

| In | Out, next sprint |
|---|---|
| The four features and the attachments between them | External JSON rule engine, different packs per role |
| Built-in rules that already exist, plus the missing outputs named above | Edge prediction within seconds, and forwarding it |
| Action cards from `ActionCardGenerator` | Edge-to-edge between blocks |
| | Sandbox (“if you do this, what changes”) |
| | Digital twin |

Cloud ingest (payload check, Timescale insert, MQTT proof, `sensor_type` alignment, parse-and-label) is the communication line. The meeting placed that line after the features. Those tickets stay parented to the platform epic and stay out of Sprint 5.

## 9. Honesty

- Bots, injectors, and campus or public datasets are `synthetic: true`.
- Lab models do not promote themselves into Layer 3.
- Vibration zone edges in code are still a placeholder (`ZONE_IS_PLACEHOLDER`). Nameplate class is not confirmed.
- Idle current and temperature thresholds are placeholders in config.
- Gas-model tickets already on the board are a separate model build. Feature 1 uses the gas reading. It does not adopt that model build.
