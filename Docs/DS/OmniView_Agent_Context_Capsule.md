# OmniView IQ — Agent Context Capsule

**Purpose:** Paste or point agents here for full-project context.  
**Target:** ISBM-PET **bottle factory**, Pune — not campus as client site.  
**Updated:** 2026-08-14

---

## One-liner

OmniView IQ = non-invasive IIoT + edge MQTT + cloud rules/ML that turns factory telemetry into **MD-penalty alerts, idle/leak waste signals, Health Index risk, and ₹ action cards** — Human-in-the-Loop only in POC.

---

## Site & POC scope

| Item | Value |
|------|--------|
| Site | ISBM-PET bottle plant, Pune (MSEDCL HT-I) |
| Constraint | Zero digital infra today (no PLC/SCADA) |
| Nodes | HP compressor + ISBM main feed (`hp-compressor`, `isbm-main-feed`) |
| Install | Non-invasive; zero production stoppage |
| Non-goals | RUL Stage B/C claims, full-line IIoT, closed-loop control, registry carbon |

**Heta / HD-graph:** built and proved the **demand engine** on campus transformer CSVs. Reuse formulation for bottle factory; label campus replay `synthetic`. Campus is **engine-dev**, not a hospital product — retarget via SiteProfile ([`Base_Core_Site_Profile_ADR.md`](Base_Core_Site_Profile_ADR.md)).

---

## Base core (site profiles)

Kernel = Layer3 event envelope + family ingest (`*.v1`) + rule detectors. Verticals (bottle factory vs hospital) are **YAML profiles** in `profiles/`, not a universal ML model. Lab family ML stays promotion-gated. See [`Base_Core_Site_Profile_ADR.md`](Base_Core_Site_Profile_ADR.md).

---

## Architecture (6 layers)

```text
Sensors → Edge (RUT956: Modbus, NTP, buffer, MQTT)
  → Ingest/TSDB → Features/Model → Arbitration → Monetize → Deliver
  → Dashboard + Jumbo display
```

| Layer | Job |
|------|-----|
| 1 Sensing | Dumb Modbus registers |
| 2 Edge | 15s electrical / 60s physical; offline backfill |
| 3 Model | Rules + PdM Stage A (this Lead track) |
| 4 Intelligence | Safety > Compliance > Cost; playbook What-If |
| 5 Monetize | Tariff → ₹ (placeholder until OI-43) |
| 6 Deliver | One stakeholder per event |

---

## Demand (HD-graph master blueprint)

Two engines, HD terminology:

1. **Live 15‑min window** → `md_risk` (~minute 11 vs `contract_demand`) — **OI-56 shipped offline** (`src/omniview/rules/demand_window.py`, `md_risk.py`)
2. **Day-ahead 96-slot** → `demand_forecast` (Q75 × 1.02) — later demo path

See [`HD_graph_Master_Demand_Blueprint.md`](HD_graph_Master_Demand_Blueprint.md).

---

## PdM cold start

| Stage | What | Status |
|-------|------|--------|
| **A** Health Index + `maintenance_risk` | Unsupervised vs priors; slopes + CUSUM | **OI-62** extracts notebook → module |
| B | Risk classifier | Needs maintenance logs |
| C | RUL | Later |

Do not claim supervised RUL in POC.

---

## Heroes & FRs (POC)

Heroes: live kVA vs contract; penalty avoided ₹; kWh/1000 bottles; high-waste idle %.  
FR3–FR4 MD; FR5 lazy-idle; FR6 leak; FR7 buffer; FR8 dashboard + action card.

**Feature specs (truth pack):** [`POC_Feature_Specs/`](POC_Feature_Specs/) — F01–F09 + [INTEGRATION_MODULE_MAP.md](POC_Feature_Specs/INTEGRATION_MODULE_MAP.md). Prefer over marketing `Docs/POC-fetures.md`.

---

## Team

| Role | Owns |
|------|------|
| Lead (Dnyandev) | Contracts, rules, PdM A, scenarios, ₹ honesty, acceptance |
| DevB | 7 sensor schemas + Day-1 bots |
| DevC | Scaffold, MQTT, TSDB, dashboard, hardware install |

**Plug requirements (what Lead needs from both):** [`DevB_DevC_Model_Plug_Requirements.md`](DevB_DevC_Model_Plug_Requirements.md).

Jira: project OI · labels `owner-lead` / `owner-devb` / `owner-devc`.

---

## Repo map

| Path | Role |
|------|------|
| `src/omniview/` | Orchestration + intelligence (rules) |
| `fixtures/demand/` | MD CSV/JSON + ingest contract + demo script |
| `webapp/` | MD-first explorer (not plant OI-68) |
| `scripts/` | Demo CLIs (`demo_md_risk.py`) |
| `HD-graph/` | Demand engine source (campus) |
| `Pressure-graph/` | F05 pressure/`pressure_leak` pack (MetroPT-3) |
| `Idle-graph/` | F04 lazy-idle pack (dataset TBD) |
| `Vibration-graph/` | F06 vib ISO pack (dataset TBD) |
| `heta xmer data for ai /` | Engine corpus (gitignored) |
| `layer-3:1.ipynb` | PdM Stage A exploration |
| `Docs/DS/` | Lead checklist, blueprints, PRDs, exec log, **POC_Feature_Specs**, DevB/DevC plug handoff, **Base_Core_Site_Profile_ADR** |
| `profiles/` | SiteProfile YAML (`bottle_factory_poc`, `hospital_campus_dev`) |
| `Docs/architeture/` | Layer3 + HLA/LLA |
| `AGENTS.md` | Agent operating rules |

---

## Current Lead status (2026-08-11)

- **POC hero = Max Demand** (pluggable ingest: CSV now, MQTT later; same `md_risk`)  
- OI-42 Layer3 contracts: Done  
- OI-56 live MD window + fixtures + CSV replay: Done (offline)  
- OI-62 PdM module: in tree, **parked** for next POC function wave  
- OI-50: MD fixture done; lazy-idle + leak open  
- OI-43: client-gated contract/bills  

---

## Agent working agreements

1. Prefer PRD + Layer3 + HD blueprint over marketing docs.  
2. Fixture-first while schemas/MQTT lag.  
3. Update [`DEVELOPMENT_EXECUTION_LOG.md`](DEVELOPMENT_EXECUTION_LOG.md) when a slice finishes.  
4. Bottle factory always the client target in demos and copy.
