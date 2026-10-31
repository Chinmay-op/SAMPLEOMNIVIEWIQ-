# Demand supply layer — F02 + F03 fetch interface

**Status:** Plan (Phase 0 doc). No code in this slice.
**Owns no math.** Reuses [`HD_graph_Master_Demand_Blueprint.md`](HD_graph_Master_Demand_Blueprint.md) formulations verbatim. This doc defines the **fetch boundary**, not a third demand engine.

---

## 1. Why a supply layer

F02 (live MD) and F03 (day-ahead forecast) are **one engine, two outputs** per the blueprint §3 ("dual engines, reuse both"). Today they are asymmetric:

| Engine | State |
|--------|-------|
| F02 live window | Extracted already — [`src/omniview/rules/demand_window.py`](../../src/omniview/rules/demand_window.py) + [`md_risk.py`](../../src/omniview/rules/md_risk.py), fixture-proven (T=11 alert) |
| F03 day-ahead 96-slot | **Still lives inside `HD-graph/`** — [`energy_model.py`](../../HD-graph/webapp/backend/energy_model.py), [`features_service.py`](../../HD-graph/webapp/backend/features_service.py) — no `omniview` module yet |

Without a shared fetch boundary, F03 would either (a) get re-derived from scratch inside `omniview` — risking a second, drifting MD formula, which [`AGENTS.md`](../../AGENTS.md) hard rule 1 forbids — or (b) get called ad hoc from `HD-graph/` by whichever consumer needs it, with no frozen contract. The supply layer is the single place F01/F07/F08/F09 (see their `F0N_CONNECTOR.md` docs) and any future dashboard code go to ask "what's the demand picture right now / tomorrow" — same pattern as `fixtures/demand/INGEST_CONTRACT.md` already uses for ingest, applied to the *output* side.

## 2. Interface contract

Two functions, both keyed on `machine_id` (bottle: `isbm-main-feed`, `hp-compressor`) and both returning Layer3-shaped payloads — no new field names beyond the blueprint's §4 terminology dictionary.

```python
# src/omniview/services/demand_supply.py (planned — not built this slice)

def get_live_window_state(machine_id: str) -> DemandWindowState:
    """Current 15-min window state for machine_id.
    Delegates to demand_window.DemandWindowState / run_series — no reimplementation.
    Returns: kva, accumulated_kva_minutes, projected_demand_kva, T_minutes, contract_demand.
    """

def evaluate_md_risk(machine_id: str) -> dict | None:
    """Thin passthrough to md_risk.evaluate_md_risk — supply layer does not
    re-gate the T>=11 / projected>=contract condition itself."""

def get_day_ahead_forecast(machine_id: str, date: str) -> list[dict]:
    """96 slots for `date`. Each slot: slot_of_day, predicted_max_kvah,
    contributing feature summary (lag_1d, lag_7d, is_holiday), synthetic flag.
    Delegates to the extracted F03 module (§3 Phase 1) — no direct HD-graph import
    from consumers.
    """
```

Both functions read the same `fixtures/demand/INGEST_CONTRACT.md` sample shape underneath; whether that data is CSV/fixture-backed (today) or MQTT/TSDB-backed (post OI-78) is invisible to the caller — this is the same "pluggable ingest, orchestration stays put" pattern already locked for F02.

## 3. Phases

### Phase 0 — this slice (docs only)
- Write this plan; freeze the two function signatures and return shapes above against Layer3 `md_risk` (§4.1) and `demand_forecast` (§4.1b) event fields.
- No code, no `HD-graph/` changes.

### Phase 1 — extract F03
- Port `HD-graph/energy_model.py` (96× XGBoost quantile α=0.75, ×1.02 buffer, direct multi-step) and `HD-graph/features_service.py` (lags, holiday, weather features) into `src/omniview/rules/demand_forecast.py`, following `demand_window.py`'s module conventions (pure functions, no framework coupling).
- No new math — direct port per blueprint §3.2 and §9 ("Implementation order" item 1: "Extract pure functions... into pluggable `omniview` demand package").
- Reuse `HD-graph/preprocessing.py`'s `aggregate_to_15min` slot prep (§3.3) rather than re-deriving `avg_kva`/`kvah_consumption`.

### Phase 2 — wire the supply layer
- Implement `src/omniview/services/demand_supply.py` calling the now-uniform F02 (`md_risk.py`, already done) and F03 (`demand_forecast.py`, from Phase 1) modules.
- CSV/fixture-backed now; MQTT/TSDB-backed after OI-78 — the supply layer's callers never change, only what backs the two module calls underneath.
- F01/F07/F08/F09 connector docs (see `Docs/DS/POC_Feature_Specs/F0N_CONNECTOR.md`) reference `demand_supply.py` as their sole demand data source instead of describing `HD-graph/` internals or `demand_window.py` directly.

## 4. Prerequisites

| Prerequisite | State |
|---|---|
| `HD_graph_Master_Demand_Blueprint.md` §3.2 (day-ahead formulation) | Read, referenced above |
| `fixtures/demand/INGEST_CONTRACT.md` (sample shape) | Already frozen |
| Layer3 `md_risk` / `demand_forecast` field freeze | Already in `Docs/architeture/Layer3_Model_Layer_Technical_Architecture.md` §4.1 |
| OI-43 sanctioned `contract_demand` | Still placeholder (`CONTRACT_DEMAND_KVA`) — supply layer surfaces the same placeholder honesty, does not resolve it |
| `demand_window.py` / `md_risk.py` (F02 extraction) | Already done — Phase 2 wraps, does not modify |

## 5. End goal

- F02 and F03 both resolve through one supply module (`demand_supply.py`); no consumer imports `HD-graph/` directly.
- F01, F07, F08, F09 connector docs cite this module as their demand source, keeping the demand contract in exactly one place.
- Live cutover (OI-78) swaps the data backing `get_live_window_state`/`get_day_ahead_forecast` without touching any caller — same "no rewrite on live cutover" property F02 already has today.

## 6. Out of scope this slice

- Writing `src/omniview/rules/demand_forecast.py` or `src/omniview/services/demand_supply.py` (Phase 1/2 — next steps, not this doc)
- Retraining 96-slot models on bottle history (blueprint §9 item 5 — after OI-43 + real history)
- Resolving `CONTRACT_DEMAND_KVA` placeholder (OI-43, unrelated to the fetch boundary)

## 7. Source index

Same as blueprint §10 — this doc adds no new sources, only a fetch boundary in front of them:

| Path | Role |
|------|------|
| `HD-graph/webapp/backend/power_monitor.py` | Live window math (already ported to `demand_window.py`) |
| `HD-graph/webapp/backend/energy_model.py` | 96-slot train/predict — Phase 1 extraction source |
| `HD-graph/webapp/backend/features_service.py` | Lags/holiday/weather — Phase 1 extraction source |
| `HD-graph/preprocessing.py` | Slot aggregation — reused, not reimplemented |
| `src/omniview/rules/demand_window.py`, `md_risk.py` | F02, already extracted |
| `fixtures/demand/INGEST_CONTRACT.md` | Sample shape both engines read |
