# ADR — Base Core Site Profile

**Status:** Accepted  
**Date:** 2026-08-14  
**Scope:** OmniView platform kernel vs site / vertical plug-ins  
**Does not change:** HD live-window MD math, OI-59 leak rules, HITL-only POC

## Decision

OmniView’s **Base** is not one trained model for every compound. It is:

```text
SiteProfile → family adapters → *.v1 samples → Layer3 detectors → typed events → demo / packs
```

Hospital vs bottle factory differ by **profile + adapters**, not by forking `src/omniview/` or copying HD-graph’s day-ahead XGBoost onto leak / idle / vibration.

## Kernel vs plug-in

| Layer | Stable across sites (kernel) | Tuned per site / compound (plug-in) |
|-------|------------------------------|-------------------------------------|
| Event envelope | Layer3 schema ([`../architeture/Layer3_Model_Layer_Technical_Architecture.md`](../architeture/Layer3_Model_Layer_Technical_Architecture.md)) | Which `event_type`s are enabled |
| Telemetry families | `electrical` / `pressure` / `thermal` / `vibration` / `stroke` / `ambient` | Which sensors exist on this site |
| Detectors | Rule engines in `src/omniview/rules/` + optional **lab** ML per family | Thresholds, bands, priors, promotion ADR |
| SiteProfile | Schema `site_profile.v1` | Asset list, KPIs, contract demand, chiller count vs bottle rate |
| Demo / packs | Aligned-window harness + HD-graph *layout* | Fixtures + heroes for that vertical |

**Packs are family plug-ins.** HD-graph layout is the pack *pattern* (preprocess → train/serve → scrubber UI), not a hospital product. Campus Hospital/College/Hostel CSVs remain **engine-dev**, never client truth.

| Pack | Kernel or plug-in | Family |
|------|-------------------|--------|
| `src/omniview/` + Layer3 envelope | Kernel | All enabled detectors |
| `HD-graph/` | Demand-engine source + pack pattern | `electrical` / `md_risk` / `demand_forecast` |
| `Pressure-graph/` | Family plug-in | `pressure` / `pressure_leak` |
| `Idle-graph/` | Family plug-in | `thermal` + current / `lazy_idle` |
| `Vibration-graph/` | Family plug-in | `vibration` / `vibration_zone` |
| `Owner-dashboard/` | Composition shell | Screens from `enabled_detectors` |
| Root `webapp/` | Lead fixture lab | POC explorer |

## SiteProfile fields (`site_profile.v1`)

Examples: [`profiles/bottle_factory_poc.yaml`](../../profiles/bottle_factory_poc.yaml), [`profiles/hospital_campus_dev.yaml`](../../profiles/hospital_campus_dev.yaml). Loader: `omniview.site.profile`.

| Field | Role |
|-------|------|
| `schema_version` | `site_profile.v1` |
| `site_id` | Stable id (`pune-isbm-poc`, `campus-hospital-dev`) |
| `vertical` | `bottle_factory` \| `hospital` \| later verticals |
| `client_claim` | `true` only for the contracted client site |
| `engine_dev` | `true` = corpus for engine work, not a sold hospital solution |
| `nodes[]` | `{id, role, pressure_min_bar?, pressure_max_bar?}` |
| `enabled_families[]` | Telemetry families present |
| `enabled_detectors[]` | Layer3 `event_type`s (and `demand_forecast`) to run / show |
| `kpis` | Vertical metrics: `contract_demand_kva`, `bottle_rate_per_hour`, `chiller_count`, … |
| `thresholds` | Idle / decay placeholders until OI-43 / site tune |
| `placeholder_flags` | Which numbers are still labeled placeholders |
| `honesty.synthetic_engines` | MetroPT / heta / campus replay stay `synthetic: true` |
| `ui.owner_dashboard_screens` | Composition screens allowed for this profile |

### Bottle factory (POC client)

Nodes `isbm-main-feed`, `hp-compressor` (+ sandbox `metropt3-apu`). Detectors: `md_risk`, `demand_forecast`, `lazy_idle`, `pressure_leak`, `vibration_zone`, `maintenance_risk`. KPIs include bottle rate / pressure hold (placeholders until site confirm).

### Hospital (engine-dev profile, not client claim)

Transformers, chillers, consumption. Detectors: `md_risk`, `demand_forecast` (and thermal/ambient as present). **Do not** enable `pressure_leak` unless that site has a pneumatic compressor node. Do not run bottle leak rules on chillers.

## Knob resolution

Order (matches existing pressure-band pattern):

1. Explicit function arguments  
2. Environment (`OMNIVIEW_CONTRACT_DEMAND_KVA`, `OMNIVIEW_PRESSURE_MIN_BAR` / `_MAX_BAR`, `OMNIVIEW_SITE_PROFILE`)  
3. Loaded SiteProfile  
4. Module defaults in [`src/omniview/config.py`](../../src/omniview/config.py)

Default profile name: `bottle_factory_poc` (values equal today’s module constants so the bottle POC does not change). Switch with `OMNIVIEW_SITE_PROFILE=hospital_campus_dev` or a file path.

## Honesty invariants

- Heta / campus / MetroPT / ziya replay → `synthetic: true`. Never present as bottle-factory or hospital organic capture.
- `CONTRACT_DEMAND_KVA`, pressure band, idle thresholds, `DEMO_PRIORS` stay labeled placeholders until OI-43 / OI-63 / site survey confirm.
- Human-in-the-loop only — no auto-actuation.

## Promotion invariant (lab ML)

Family lab ML (Pressure-graph leak score, Idle-graph, HD day-ahead, …) is **parallel evidence**. It does not emit Layer3 events until a **human ADR** sets that family primary.

- `promote_to_layer3` stays `false` in code helpers.  
- Missing gate report → `gate_evaluated: false`, never a passing default.  
- No universal XGBoost/LSTM that predicts “everything” across verticals.

Live detection SoT remains rules (HD live MD window, OI-59 decay-while-loaded, OI-57 idle). Trained models belong where the question is **forecast** (96-slot demand) or a **promotion-gated** score.

## Explicit non-goals

- One runtime model for all physics / all verticals  
- Auto-actuation  
- Presenting campus HD UI as a hospital product  
- Inventing alternate max-demand math  
- Enabling bottle `pressure_leak` on a hospital profile that has no air compressor

## Demo / UI contract

Owner-dashboard and Lead explorer **light panels from `enabled_detectors`** (see [`Owner-dashboard/docs/SCREEN_MAP.md`](../../Owner-dashboard/docs/SCREEN_MAP.md) and [`POC_Feature_Specs/INTEGRATION_MODULE_MAP.md`](POC_Feature_Specs/INTEGRATION_MODULE_MAP.md) §8). Family pack UIs remain the deep lab for that detector.

## Consequences

- Retargeting a compound = new YAML + adapters + fixtures, not a platform fork.  
- Agents read this ADR to answer: what is Base, what retunes per vertical, where ML sits.  
- Bottle POC keeps running on the default profile.
