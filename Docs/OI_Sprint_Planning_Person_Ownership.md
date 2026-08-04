# OmniView IQ — Sprint Planning: Person Ownership & Aims

**Purpose:** Use this in sprint planning and task walkthroughs. One page per person: what they own, what “done” looks like, why it matters, and how it improves the product.

**Team model:** Lead defines contracts + product intelligence. DevB and DevC ship plug-in units that satisfy those contracts (schemas/bots → MQTT/TSDB → rules/PdM → dashboard).

**Board filters:** `labels = owner-lead` | `owner-devb` | `owner-devc`  
**Project:** [OI (Omniview-IQ)](https://mightium.atlassian.net/jira/software/projects/OI)  
**Active sprint:** OI Sprint 1

---

## At-a-glance

| Person | Role | Tasks | ~SP | System job in one line |
|--------|------|------:|----:|------------------------|
| **Dnyandev Sawarkar** | Lead — AI / rules / hard integration | 20 | ~37.5 | Turn telemetry into **proven alerts, HI risk, and ₹ math** |
| **vibhanshuinfo** | DevB — Data units | 15 | ~16.5 | Make every sensor **schema-valid and Day-1 feedable** |
| **Chinmay Wadettiwar** | DevC — Platform units | 21 | ~28.0 | Make the **pipe and UI real**: edge → MQTT → TSDB → dashboard |

```text
vibhanshuinfo (schemas + bots)
        │ schema-valid payloads
        ▼
Chinmay (scaffold, MQTT, TSDB, edge injectors, dashboard)
        │ live / seeded time-series + UI shell
        ▼
Dnyandev (rules, PdM Stage 0/A, scenarios, monetize, acceptance)
        │ action cards + hero metrics + POC proof
        ▼
Plant Manager / Operator value
```

---

# 1. Dnyandev Sawarkar — Lead (AI / Rules / Architecture)

## Aiming at
Prove the POC’s **intelligence layer**: MD near-miss detection, lazy-idle, leak proxy, vibration zones, Health Index Stage 0/A, tariff→₹ monetize, and final acceptance judgment. Own the hard problem-solving so DevB/DevC units plug into a clear contract.

## Assigned load
| Metric | Value |
|--------|------:|
| Task count | **20** |
| Story points | **~37.5** |
| Owner label | `owner-lead` |
| Sprint 1 Day-1 focus | [OI-62](https://mightium.atlassian.net/browse/OI-62) (+ start [OI-42](https://mightium.atlassian.net/browse/OI-42) contracts) |

**Keys:** OI-1, OI-42, OI-43, OI-50, OI-56–61, OI-62–67, OI-70, OI-78–80

## End output (what “done” delivers)
1. **Contracts:** Layer3 architecture / dangling refs resolved; Phase 0 MD/bills/nameplates checklist tracked.
2. **Rule engine:** Rolling 15‑min kVA + MD trajectory (~min 11); lazy-idle; ISO 10816‑3 vib zones; pressure-decay leak proxy; conflict arbitration; scenario unit tests.
3. **PdM Stage 0/A:** Notebook promoted to module; equipment-class priors; maintenance-event log schema; HI daily batch; CUSUM retune; `maintenance_risk` events.
4. **Business correctness:** Tariff→₹ monetize module (placeholder until site bills confirmed).
5. **Site proof:** Live Modbus cutover E2E verification; real idle + lazy-idle capture; PRD §7 acceptance checklist signed.

## Responsibility
| Owns | Does *not* own (consumes instead) |
|------|-----------------------------------|
| Rule math, scenario physics, arbitration priority | Sensor schema drafting (DevB) |
| HI / CUSUM / PdM Stage A event contract | MQTT broker, hypertables, dashboard shell (DevC) |
| Architecture contracts + acceptance criteria | Day-1 bot payload generation (DevB) |
| Monetize formula + client/site MD confirmation | Hardware BOM / install logistics (DevC) |
| Live cutover *verification* + POC acceptance | On-site clamp install execution (DevC) |

## Importance in the system
Without Lead, the stack is **plumbing with no product claim**. Edge + bots can move data; only this track converts data into:
- Avoidable **MD penalty** alerts before the 15‑min window closes  
- **Lazy-idle / leak** detection operators can act on  
- **Health Index** risk signals (`maintenance_risk`)  
- Believable **₹** figures for plant/finance personas  

## Key features by epic

| Epic | Tasks | Key features you are building |
|------|-------|-------------------------------|
| **A Foundation** | OI-42, OI-43 | Architecture truth; Phase 0 site inputs (MD, bills, nameplates) |
| **B Day-1 Data** | OI-50 | Scenario injector (MD near-miss / lazy-idle / leak) with synthetic labels |
| **E Rule Engine** | OI-56–61 | FR3–FR6 intelligence + arbitration + automated scenario tests |
| **F PdM Stage 0/A** | OI-1, OI-62–67 | Notebook → module → HI batch → CUSUM → `maintenance_risk` |
| **G Dashboard** | OI-70 | Tariff→₹ monetize (feeds hero “penalty avoided”) |
| **H Hardware** | OI-78–80 | Live cutover E2E, real event capture, PRD §7 acceptance |

## Outcome for product betterment
- Turns POC from “sensors online” into **client-demonstrable ROI** (MD avoid, waste ₹, action cards).
- Creates **testable truth** via labeled scenarios — rules don’t ship on vibes.
- Locks Stage A PdM path so later Stage B/C has a real HI + event log foundation.
- Final acceptance gate: only ship what passes PRD §7 (calibration, NTP, MD math, buffer, vib bands, dashboard, ₹ traceability).

---

# 2. vibhanshuinfo — DevB (Sensor Schemas + Day-1 Bots)

## Aiming at
Be the **data contract factory**: all 7 sensor families have schemas; Day-1 bots publish continuous, schema-valid streams (real electrical CSVs + public/synthetic for the rest) so rules and dashboard never wait on live hardware.

## Assigned load
| Metric | Value |
|--------|------:|
| Task count | **15** |
| Story points | **~16.5** |
| Owner label | `owner-devb` |
| Sprint 1 Day-1 focus | [OI-23](https://mightium.atlassian.net/browse/OI-23), [OI-5](https://mightium.atlassian.net/browse/OI-5), [OI-8](https://mightium.atlassian.net/browse/OI-8) (+ OI-6/7 in parallel) |

**Keys:** OI-2, OI-5–8, OI-23, OI-25–27, OI-44–49

## End output (what “done” delivers)
1. **Seven schemas:** Electrical (+ Modbus map), vibration, thermal, pressure, gas, stroke, ambient — each with `device_id`, `timestamp`, `sensor_type`, `schema_version`, `data`.
2. **Day-1 bots:** Electrical CSV replay; vib+CWRU; thermal+NAB; pressure+UCI shapes; gas dummy; stroke+ambient tied to electrical on/off.
3. **Research umbrella closed:** OI-2 done when all 7 schemas + Day-1 source choices exist.
4. **Doc hygiene:** Typos / placeholder ₹ flags (OI-44) so planning docs stay trustworthy.

## Responsibility
| Owns | Does *not* own |
|------|----------------|
| Sensor parameter lists & JSON schemas | Scenario injector physics (Lead OI-50) |
| Synthetic / public / CSV replay bots | MQTT topic design, TSDB inserts (DevC) |
| Labeling synthetic vs public samples | Rule thresholds / HI math (Lead) |
| Closing research umbrella OI-2 | Dashboard UI (DevC) |

## Importance in the system
DevB is the **only path to Day‑1 demo without full hardware**. Rules (Lead) and pipeline (DevC) both consume DevB payloads. Wrong schema = broken validation, empty dashboard, false rule tests.

## Key features by epic

| Epic | Tasks | Key features you are building |
|------|-------|-------------------------------|
| **A Foundation** | OI-44 | Doc typos; placeholder ₹ callouts |
| **B Sensor + Day-1** | OI-2, OI-5–8, OI-23, OI-25–27, OI-45–49 | Full multi-modal Day‑1 data surface (7 families) |

**Suggested sprint narrative for DevB**
1. Schemas first (OI-23, OI-5, OI-6, OI-7 → then OI-45/46/47).  
2. Electrical replay (OI-8) unlocks edge injector demos.  
3. Remaining bots (OI-25–27, OI-48–49) unlock FR5/FR6 and vib-zone tests.  
4. Close OI-2 when schemas + Day-1 sources are complete.

## Outcome for product betterment
- Enables **honest hybrid Day‑1**: real transformer CSVs + parameter-faithful synthetics — no fake “full plant” claims.
- Unlocks parallel work: Chinmay can wire MQTT/TSDB while Lead builds rules against labeled streams.
- Makes sensor taxonomy **reusable** for live Modbus cutover (same schema, new source).
- Reduces rework: one schema version contract prevents ad‑hoc payload drift between edge and cloud.

---

# 3. Chinmay Wadettiwar — DevC (Edge / Cloud / UI / Hardware Logistics)

## Aiming at
Be the **platform spine**: runnable repo scaffold, MQTT + TimescaleDB, edge injectors/pollers, offline buffer/backfill, live dashboard shell, alert routing / jumbo stubs, and hardware logistics through install.

## Assigned load
| Metric | Value |
|--------|------:|
| Task count | **21** |
| Story points | **~28.0** |
| Owner label | `owner-devc` |
| Sprint 1 Day-1 focus | [OI-41](https://mightium.atlassian.net/browse/OI-41) → [OI-51](https://mightium.atlassian.net/browse/OI-51) → [OI-54](https://mightium.atlassian.net/browse/OI-54) |

**Keys:** OI-12–15, OI-28–29, OI-41, OI-51–55, OI-68–69, OI-71–77

## End output (what “done” delivers)
1. **Runnable POC layout:** `src/`, requirements, docker-compose (Mosquitto + TimescaleDB), `.env.example`.
2. **Edge path:** MQTT topics; device_id/node map; NTP drift guard; electrical CSV→MQTT injector; physical sensor poller; offline buffer + chronological backfill.
3. **Cloud path:** Hypertables/migrations; payload validation + schema version; idempotent inserts; Day‑1 seed script.
4. **Operator surface:** Live dashboard (kVA vs contract, alerts, HI trend); action-card UI consuming Lead events; alert routing stub; jumbo Modbus feed stub.
5. **Site logistics:** BOM + lead times; walkthrough / Layer 0 profile; safety sign-off; non-invasive install; clamp-meter calibration log.

## Responsibility
| Owns | Does *not* own |
|------|----------------|
| Scaffold, MQTT, TSDB, edge injectors/pollers | Sensor schema contents (DevB) |
| Buffer / backfill reliability (FR7) | Rule engine / HI math (Lead) |
| Dashboard shell + routing/jumbo stubs | Monetize formula (Lead OI-70) |
| BOM, install, calibration execution | Live cutover *acceptance* (Lead OI-78–80) |

## Importance in the system
DevC is the **integration fabric**. Without it there is no local demo stack, no durable time-series, no shop-floor visibility, and no path from Day‑1 bots to live Modbus. Lead’s rules and DevB’s bots only become a product when this pipe works end-to-end.

## Key features by epic

| Epic | Tasks | Key features you are building |
|------|-------|-------------------------------|
| **A Foundation** | OI-41 | Repo scaffold + docker-compose |
| **C Edge Gateway** | OI-12, OI-13, OI-28, OI-29, OI-51–53 | MQTT, node map, NTP, injectors/pollers, offline resilience |
| **D Cloud / TSDB** | OI-14, OI-15, OI-54, OI-55 | Hypertables, validation, idempotent inserts, seed script |
| **G Dashboard / Alerts** | OI-68, OI-69, OI-71, OI-72 | Live UI, action cards, routing stub, jumbo feed |
| **H Hardware / Site** | OI-73–77 | BOM → walkthrough → safety → install → calibration |

**Suggested sprint narrative for DevC**
1. OI-41 scaffold unlocks everyone.  
2. OI-51 MQTT + OI-54 TSDB unlock ingest.  
3. Wire DevB bots via OI-12/OI-13 + OI-55 seed.  
4. Dashboard (OI-68) once data lands; hardware track in parallel as logistics allow.

## Outcome for product betterment
- Delivers **zero-downtime pilot story**: non-invasive install + offline buffer so factory internet blips don’t erase proof.
- Makes hero metrics **queryable** (live kVA, alerts, HI trend) for plant manager demos.
- Closes the last mile to operators: jumbo display stub + hierarchical alert routing.
- Turns Day‑1 software into Week‑2/3 **live site** by keeping Modbus swap as a config/path change, not a rewrite.

---

## OI Sprint 1 — ordered backlog (live on board)

**Total:** 15 Tasks · **~18.5 SP** · Sort board by **Priority** to match waves.

### Wave 1 — Start in parallel (Priority: Highest)

| Person | Order | Key | SP | Work |
|--------|------:|-----|---:|------|
| Dnyandev | 1a | [OI-42](https://mightium.atlassian.net/browse/OI-42) | 1.0 | Layer3 architecture contracts |
| Dnyandev | 1b | [OI-62](https://mightium.atlassian.net/browse/OI-62) | 2.0 | Promote notebook → PdM module |
| vibhanshuinfo | 1 | [OI-23](https://mightium.atlassian.net/browse/OI-23) | 1.0 | Electrical schema + Modbus map |
| vibhanshuinfo | 1 | [OI-5](https://mightium.atlassian.net/browse/OI-5) | 0.5 | Vibration schema |
| vibhanshuinfo | 1 | [OI-6](https://mightium.atlassian.net/browse/OI-6) | 0.5 | Thermal schema |
| vibhanshuinfo | 1 | [OI-7](https://mightium.atlassian.net/browse/OI-7) | 0.5 | Pressure schema |
| Chinmay | 1 | [OI-41](https://mightium.atlassian.net/browse/OI-41) | 1.5 | Scaffold `src/` + docker-compose |

### Wave 1b — Right after scaffold (Priority: High)

| Person | Order | Key | SP | Work |
|--------|------:|-----|---:|------|
| Chinmay | 2 | [OI-51](https://mightium.atlassian.net/browse/OI-51) | 1.0 | MQTT topics + Mosquitto |
| Chinmay | 3 | [OI-54](https://mightium.atlassian.net/browse/OI-54) | 1.5 | TimescaleDB hypertables |

### Wave 2 — After schemas / MQTT exist (Priority: High)

| Person | Order | Key | SP | Work |
|--------|------:|-----|---:|------|
| vibhanshuinfo | 2 | [OI-8](https://mightium.atlassian.net/browse/OI-8) | 1.5 | Electrical CSV replay bot |
| Chinmay | 4 | [OI-12](https://mightium.atlassian.net/browse/OI-12) | 2.0 | CSV→MQTT electrical injector |

### Wave 3 — Integration beat (Priority: Medium)

| Person | Order | Key | SP | Work |
|--------|------:|-----|---:|------|
| Dnyandev | 3 | [OI-50](https://mightium.atlassian.net/browse/OI-50) | 2.0 | Scenario injector (MD / lazy-idle / leak) |
| Dnyandev | 4 | [OI-56](https://mightium.atlassian.net/browse/OI-56) | 2.0 | Rolling 15‑min kVA + MD alert |

### Tracking umbrellas (Priority: Low — close when children done)

| Person | Key | SP |
|--------|-----|---:|
| Dnyandev | [OI-1](https://mightium.atlassian.net/browse/OI-1) | 0.5 |
| vibhanshuinfo | [OI-2](https://mightium.atlassian.net/browse/OI-2) | 0.5 |

**Hand-off rule:** Wave 2 needs Wave 1 schemas + MQTT. Wave 3 needs Wave 2 stream + Lead contracts.

---

## Related links

- PRD goals & FRs: `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`  
- POC feature summary: `Docs/POC-fetures.md`  
- Sensor parameters: `Docs/sesnor-fetures.md`
