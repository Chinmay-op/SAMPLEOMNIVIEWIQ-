# Branch and merge workflow

**Status:** Active  
**Date:** 2026-08-17  
**Repo:** `Mightium/omniview-iq-poc`

DevB, DevC, and Lead each keep a **stable working branch**. Integration happens on a dedicated branch. Do not dump edge/Owner merges onto someone else’s only working tree.

## 1. Stable branches (do not overwrite)

| Branch | Owner | Frozen meaning |
|--------|-------|----------------|
| `Vib_branch` | DevB (Vibhanshu) | Schemas, bots, parsers, synthetic generators |
| `chinmay` / `main` | DevC (Chinmay) | MQTT, Timescale, injector, subscriber. DevC tip = `main` + chinmay UUID `client_id` fix |
| `yash` | Lead | Owner-dashboard, HD/Idle/Pressure composition, SiteProfile, Lead rules |

**Forbidden:** force-push to `main`, `yash`, `Vib_branch`, or `chinmay`.  
**Forbidden:** merging DevB∪DevC∪Owner onto `yash` as the daily target until integration is proven.

## 2. Integration home

| Home | Use |
|------|-----|
| `integration/live-spine` | **Default** — same repo; only place DevB ∪ DevC ∪ yash merges and live-Owner work |
| Second GitHub repo | Optional later: mirror the three frozen branches, merge only there |

Optional local worktrees: `wt-yash`, `wt-vib`, `wt-devc` on frozen tips so daily work continues.

## 3. Freeze tags (before any merge)

Create annotated tags on the tips you intend to keep:

```text
stable/yash-YYYYMMDD
stable/vib-YYYYMMDD
stable/devc-YYYYMMDD
```

`stable/devc-*` should point at DevC tip (`origin/chinmay` if it is main+UUID, else `origin/main`).

Do not move these tags. New work on stables is new commits; retag only with a new date suffix.

## 4. Merge sequence

```text
1. Tag freeze
2. Create integration/live-spine from DevC tip (main + UUID)
3. Merge tagged Vib_branch into integration  (P0a — expect schema/bot conflicts)
4. Smoke MQTT → TSDB
5. Merge tagged yash into integration        (P0b — keep Owner AND edge)
6. Live Owner work (P1+) stays on integration
7. Optional later: PR slices back to each stable (never force-push)
```

## 5. Conflict source of truth

When files collide, resolve in this order:

1. [`DevB_DevC_Model_Plug_Requirements.md`](DevB_DevC_Model_Plug_Requirements.md) — wire envelope, short topic ↔ long `sensor_type`, adapter field map.
2. Lead rules for math — never rewrite `projected_demand_kva`, OI-57, OI-59, ISO bands, Stage A PdM.
3. DevB owns `schemas/*.json` field names; DevC owns MQTT topics / hypertables; Lead owns adapters.
4. **Keep** `layer-3:1.ipynb` (Windows rename on chinmay must not drop the notebook).
5. **Keep** `Owner-dashboard/` from yash and `src/omniview/edge/` + `src/omniview/ingest/` from DevC.

Do not “fix” topic short types to match schema consts — map explicitly.

## 6. Who merges what

| Step | Who | Onto |
|------|-----|------|
| Freeze tags | Lead (or designated integrator) | tags only |
| P0a DevB ∪ DevC | Integrator | `integration/live-spine` |
| P0b + yash | Integrator | `integration/live-spine` |
| Daily DevB | Vibhanshu | `Vib_branch` |
| Daily DevC | Chinmay | `chinmay` / PRs to `main` |
| Daily Lead Owner/rules | Lead | `yash` until they pull from integration |

## 7. Agent rules

Agents and humans:

- Default merge target is **`integration/live-spine`**, not `yash` / `Vib_branch` / `chinmay`.
- Do not invent MD / leak / ISO math.
- Do not commit secrets. Do not force-push `main`.
- Record slices in [`DEVELOPMENT_EXECUTION_LOG.md`](DEVELOPMENT_EXECUTION_LOG.md).
