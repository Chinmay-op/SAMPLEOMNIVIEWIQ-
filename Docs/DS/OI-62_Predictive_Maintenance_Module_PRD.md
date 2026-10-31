# OI-62 — Predictive Maintenance Module PRD (Stage A)

**Jira:** [OI-62](https://mightium.atlassian.net/browse/OI-62) · **SP:** 2.0 · **Owner:** Lead  
**Status:** Active for implementation  
**Site framing:** Bottle factory POC — module is asset-agnostic; demos may use `hp-compressor` / electrical meter–shaped features.

---

## 1. Problem

Health Index, 7-day slopes, CUSUM flags, and `maintenance_risk` emission live in Colab notebook [`layer-3:1.ipynb`](../../layer-3:1.ipynb). That cannot be scheduled, unit-tested in CI, or consumed by Chinmay’s stack. Stage A must become a **library**.

## 2. Users

| User | Need |
|------|------|
| Lead / batch job | Call HI + risk from Python without notebooks |
| DevC dashboard | Later consume `maintenance_risk` events (OI-67) |
| Standup / demo | `scripts/demo_pdm.py` offline proof |

## 3. Scope

### In scope

- Extract Stage A building blocks from notebook cells **19, 20, 22, 25, 28**
- Callable API under `src/omniview/rules/predictive_maintenance.py`
- Hardcoded `DEMO_PRIORS` (placeholder for OI-63)
- Synthetic daily fixture + pytest + thin demo CLI
- Layer3-compatible `maintenance_risk` envelope (include `synthetic`)

### Out of scope

- OI-63 YAML Layer 0 priors config
- OI-64 maintenance-event log table
- OI-65 scheduled daily batch / TSDB pull
- OI-66 CUSUM retune on real bottle HI
- OI-67 MQTT `_alerts` publish
- Stage B/C supervised RUL claims
- Full heta multi-folder ETL in CI

## 4. Inputs

Daily (or daily-aggregated) rows with at least:

- `machine_id`, `date`
- `PF_Ave`, `Current_Total`
- `Current_R_phase`, `Current_Y_phase`, `Current_B_phase`
- `Current_R_Harm`, `Current_Y_Harm`, `Current_B_Harm`, `Neutral_current`

(Notebook `pipeline_cols` + derived imbalance / norms.)

## 5. Outputs

| Output | Description |
|--------|-------------|
| Enriched frame | `phase_imbalance_pct`, `*_norm` columns |
| Slopes | `*_slope_7d` per tracked signal |
| `health_index` | 0–100 vs population priors |
| `cusum_flags` | bool list aligned to HI series |
| `maintenance_risk` | Layer3 event dict |

## 6. API surface

```text
enrich_daily_features(df) -> DataFrame
add_trend_features(df, window=7) -> DataFrame
compute_health_index(row, priors=DEMO_PRIORS) -> float
attach_health_index(df, priors=...) -> DataFrame
cusum_flags(series, threshold=8, drift=0.5) -> list[bool]
predict_maintenance_risk(machine_id, latest_row, confidence_stage=..., synthetic=False) -> dict
```

**Risk tiers (notebook):** HI &lt; 40 → `high`; &lt; 65 → `medium`; else `low`.  
**HI formula:** `max(0, 100 - mean(|z|) * 12)` over prior feature set.

## 7. Non-functional

- Deterministic given priors + row values
- No network I/O at import
- Offline pytest (synthetic fixture only)
- Do not recompute fleet priors from heta on every import

## 8. Acceptance (Done when)

- [ ] Core notebook logic callable as a module
- [ ] Same-path smoke: fixture → slopes → HI → `maintenance_risk` with required keys
- [ ] `DEMO_PRIORS` listed for OI-63 handoff
- [ ] OI-1 umbrella stays open until Stage A chain (63–67) finishes
- [ ] Lead checklist OI-62 smoke box checked
- [ ] Execution log entry completed with pytest result

## 9. Test plan

1. Unit: `rolling_slope` NaN warmup; HI in [0, 100]; toy priors → known HI  
2. Integration: load `fixtures/pdm/*` → full path → envelope `event_type=maintenance_risk`  
3. Demo: `scripts/demo_pdm.py` prints one JSON event  

## 10. Traceability

| Artifact | Link |
|----------|------|
| Notebook | `layer-3:1.ipynb` cells 19/20/22/25/28 |
| Build Spec | `referance/Predictive_Maintenance_Build_Spec.md` §7 |
| Layer3 | `Docs/architeture/Layer3_Model_Layer_Technical_Architecture.md` §5 |
| Lead unit | `Docs/DS/OI_Lead_Dnyandev_Master_Checklist.md` Unit 1.1 |

## 11. Recording (on completion)

Update [`DEVELOPMENT_EXECUTION_LOG.md`](DEVELOPMENT_EXECUTION_LOG.md) with: files touched, `pytest` summary, DEMO_PRIORS source note, residual risks (CUSUM over-flag → OI-66), next tickets (OI-63).
