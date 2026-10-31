# Owner live system design

**Status:** Active — D0 SoT for the live Owner path  
**Date:** 2026-08-17  
**Does not change:** HD live-window MD math, OI-57 / OI-59 / OI-58 rule formulas, HITL-only POC

Owner-dashboard is the **operator composition shell**. Family packs (`HD-graph/`, `Pressure-graph/`, `Idle-graph/`, `Vibration-graph/`) stay deep labs. The product path is always:

```text
DevB bots / site sensors
  → MQTT (Mosquitto)
  → DevC subscriber + TimescaleDB hypertables
  → Lead adapters (wire envelope → *.v1 / MD samples)
  → Layer3 detectors (Lead rules)
  → Owner BFF
  → Owner UI (HITL action cards)
```

CSV / correlated / master-timeline feeds are **offline / CI fallback only** after P1. They are not the product path.

## 1. System diagram

```text
[DevB] schemas/*.json + edge/bots + synthetic_data
              │ envelope: device_id, timestamp, sensor_type, schema_version, data, synthetic
              ▼
[DevC] omniview/{site_id}/{node_id}/{short_type}
              │ MQTT QoS 1
              ▼
[DevC] ingest/subscriber → Timescale hypertables
              │
              ▼
[Lead] adapters (DevB_DevC_Model_Plug_Requirements.md field map)
              │ idle.v1 | pressure.v1 | vibration.v1 | MD kva/kw+var
              ▼
[Lead] md_risk | lazy_idle | pressure_leak | vibration_zone | maintenance_risk
              │ Layer3 events (synthetic flag preserved)
              ▼
[Owner BFF :8020] OWNER_FEED=tsdb
              ▼
[Owner UI :5175] Overview / Power / Air / Idle / Vibration / Motor / Correlation / Events
```

Alerts Lead → DevC (later): `omniview/{site_id}/_alerts/{event_type}`.

## 2. Kernel vs plug-in

See [`Base_Core_Site_Profile_ADR.md`](Base_Core_Site_Profile_ADR.md). Site retarget is YAML (`profiles/bottle_factory_poc.yaml`), not a dashboard fork.

| Layer | Kernel | Plug-in |
|-------|--------|---------|
| Event envelope | Layer3 schema | Which `event_type`s SiteProfile enables |
| Wire | 7 family schemas + short↔long type map | Which sensors exist on the node |
| Detectors | `src/omniview/rules/*` | Thresholds / bands / promotion ADR |
| Owner screens | Shell + alert rail | `ui.owner_dashboard_screens` |

## 3. Honesty

| Source | Flag |
|--------|------|
| DevB bots, injectors, public datasets (MetroPT, ziya07, campus HD) | `synthetic: true` |
| Organic bottle-factory capture (`isbm-main-feed`, `hp-compressor`) | `synthetic: false` only when DevC marks site feed |

Never present campus Hospital/College/Hostel CSVs as client truth.

## 4. Layer3 vs lab ML

| Family | Layer3 SoT (Owner alerts) | Lab only until human ADR |
|--------|---------------------------|--------------------------|
| Electrical / MD | `demand_window` + `md_risk` | HD xgboost day-ahead in pack |
| Idle | `lazy_idle` (OI-57) | `idle_lazy_ml.json` |
| Pressure | `pressure_leak` (OI-59) | leak ML JSON |
| Vibration | ISO 10816-3 Class II `vibration_zone` (OI-58) | future pack ML |
| Motor / PdM | `predict_maintenance_risk` Stage A (OI-62) | Colab extras not extracted |

Code never auto-sets `promote_to_layer3: true`.

## 5. Owner feed modes

| `OWNER_FEED` | When |
|--------------|------|
| `tsdb` | **Product default** after P1 — Timescale hypertables |
| `correlated` / `master` | CI / demo without Docker — labeled synthetic, not live |

## 6. HITL

Recommendations and action cards only. No auto-actuation, no FMI twin in this system.

## Related

- [`BRANCH_AND_MERGE_WORKFLOW.md`](BRANCH_AND_MERGE_WORKFLOW.md)
- [`LIVE_PIPELINE_RUNBOOK.md`](LIVE_PIPELINE_RUNBOOK.md)
- [`DETECTOR_ATTACH_MATRIX.md`](DETECTOR_ATTACH_MATRIX.md)
- [`DevB_DevC_Model_Plug_Requirements.md`](DevB_DevC_Model_Plug_Requirements.md)
