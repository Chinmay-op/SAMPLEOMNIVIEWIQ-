# `integration/live-spine` — merge contents and operator map

**Branch:** `integration/live-spine`  
**Date:** 2026-08-17  
**Repo:** `Mightium/omniview-iq-poc`  
**Purpose:** Only place where DevB ∪ DevC ∪ Lead (`yash`) are merged for live Owner. Daily work stays on stable branches.

Related: [`BRANCH_AND_MERGE_WORKFLOW.md`](BRANCH_AND_MERGE_WORKFLOW.md), [`OWNER_LIVE_SYSTEM_DESIGN.md`](OWNER_LIVE_SYSTEM_DESIGN.md), [`OWNER_LIVE_SYSTEM_EXPLAINER.md`](OWNER_LIVE_SYSTEM_EXPLAINER.md), [`LIVE_PIPELINE_RUNBOOK.md`](LIVE_PIPELINE_RUNBOOK.md), [`STABLE_BRANCH_FREEZE.md`](STABLE_BRANCH_FREEZE.md).

## 1. Freeze tags (inputs)

| Tag | Meaning |
|-----|---------|
| `stable/devc-20260817` | DevC tip (`chinmay` / main + MQTT `client_id` UUID) — branch base |
| `stable/vib-20260817` | DevB `Vib_branch` tip — schemas / bots / generators |
| `stable/yash-20260817` | Lead `yash` tip at D0 docs freeze |

Do not move these tags. Do not force-push `main`, `yash`, `Vib_branch`, or `chinmay`.

## 2. Merge commits (already on this branch)

| Commit | Step | What landed |
|--------|------|-------------|
| `67fe15e` | P0a | DevB ∪ DevC — bots/schemas/simulators; DevB “theirs” for bot conflicts; union `.gitignore` |
| `ad5f9e3` | P0b | Frozen `yash` into live-spine — Owner + Lead rules; union `pyproject.toml`; Lead `config.py` **plus** MQTT/TSDB constants |

## 3. Post-merge live Owner slice (P1–P6 on this branch)

Product path (when Docker/TSDB is up):

```text
bots/sensors → MQTT → Timescale readings_{family}
  → adapters (wire.py short↔long) → Layer3 detectors → Owner BFF :8020 → UI :5175
```

| Area | Location |
|------|----------|
| Wire adapters | `src/omniview/adapters/wire.py` |
| TSDB window query | `src/omniview/ingest/db.py` → `query_window` |
| Owner TSDB feed | `Owner-dashboard/backend/tsdb_feed.py` (`OMNIVIEW_OWNER_FEED=tsdb`) |
| Live detectors | `src/omniview/rules/detectors_live.py` |
| Vibration OI-58 | `src/omniview/rules/vibration_zone.py` + fixture `Vibration-graph/fixtures/iso_zone_transition.csv` |
| Motor health | `GET /api/motor/health` — compose hold / heat / current / Stage A PdM (no new universal model) |
| Owner screens | Overview, Power, Air, Idle, **Vibration**, **Motor**, Correlation, Events |
| Honesty | `synthetic: true` for bots/public corpora; HITL only; lab ML never auto-promotes |

Offline / CI without Docker: leave feed unset (correlated/master CSV). Still labeled synthetic.

## 4. Owner BFF endpoints added for live

| Path | Role |
|------|------|
| `GET /api/vibration/replay` | OI-58 zone series (fixture or TSDB) |
| `GET /api/motor/health` | Hold + heat + current + `maintenance_risk` |
| `GET /api/detectors/live` | md / idle / leak / vib on window |
| Overview / Events | Include `vibration_zone` + Stage A PdM sideband |

Set `OMNIVIEW_OWNER_FEED=tsdb` only when hypertables + `omniview.ingest` are available on this branch.

## 5. What this branch is not

- Not a replacement for daily `yash` / `Vib_branch` / `chinmay` working trees.
- Not bottle-factory organic truth (bots, MetroPT, ziya07, campus HD are synthetic / engine-dev).
- Does not invent MD / OI-57 / OI-59 / ISO / Stage A PdM math — Lead rules only.
- MQTT short type and schema long `sensor_type` stay mapped, not collapsed.

## 6. Bring-up checklist

1. Worktree or checkout: `integration/live-spine`
2. `docker compose up -d` (Mosquitto + Timescale) — see runbook
3. Migrations / hypertables
4. Subscriber + DevB bots
5. Owner BFF: `OMNIVIEW_OWNER_FEED=tsdb` uvicorn `:8020`
6. Owner UI Vite `:5175`
7. Smoke: `Owner-dashboard/scripts/smoke_bff.py` (CSV path) or MQTT→TSDB insert then detectors/live

If Docker is unavailable, use correlated/master feed and still treat data as synthetic.

## 7. Pulling back to stables (later)

Optional PR slices from this branch → each stable. Never dump the full integration tree onto `yash` as the daily target. See [`BRANCH_AND_MERGE_WORKFLOW.md`](BRANCH_AND_MERGE_WORKFLOW.md).
