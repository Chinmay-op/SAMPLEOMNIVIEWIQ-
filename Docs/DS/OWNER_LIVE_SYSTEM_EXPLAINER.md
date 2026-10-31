# Owner live system — working model explainer

**Audience:** operators and engineers bringing up Owner on `integration/live-spine`.  
**Date:** 2026-08-17  
**Extends:** [`OWNER_LIVE_SYSTEM_DESIGN.md`](OWNER_LIVE_SYSTEM_DESIGN.md), [`LIVE_PIPELINE_RUNBOOK.md`](LIVE_PIPELINE_RUNBOOK.md)

## What is running

```text
DevB bots (synthetic: true) or site sensors
  → Mosquitto topic omniview/{site}/{node}/{short_type}
  → DevC subscriber → readings_{family} hypertables
  → Lead adapters (wire.py) → idle.v1 / pressure.v1 / vibration.v1 / MD samples
  → Layer3: md_risk | lazy_idle | pressure_leak | vibration_zone | maintenance_risk
  → Owner BFF :8020 (OMNIVIEW_OWNER_FEED=tsdb)
  → Owner UI :5175  HITL action cards only
```

Stable branches `yash`, `Vib_branch`, `chinmay` stay as daily working trees. Merges happen on `integration/live-spine`. Freeze tags: `stable/*-20260817`.

## What the operator sees

| Screen | SoT |
|--------|-----|
| Overview | Heroes + severity-ranked alerts |
| Power | Electrical / MD |
| Compressed air | OI-59 leak / hold / health |
| Idle | OI-57 lazy_idle / waste |
| Vibration | OI-58 ISO Class II zones |
| Motor health | Hold + heat + current + Stage A PdM |
| Correlation | Shared-clock join |
| Events | HITL recommendations, no JSON dumps as primary |

Lab ML (idle/leak pack scores) is labeled **not Layer3**.

## How to run (integration branch)

See [`LIVE_PIPELINE_RUNBOOK.md`](LIVE_PIPELINE_RUNBOOK.md). Short path:

1. `docker compose up -d` (Mosquitto + Timescale)
2. `python -m omniview.ingest.migrations`
3. subscriber + bots
4. `OMNIVIEW_OWNER_FEED=tsdb` uvicorn Owner BFF `:8020`
5. Vite `:5175`

Without Docker: omit `tsdb` feed; CSV/correlated still works and stays `synthetic: true`.

## Honesty

Bots, MetroPT, ziya07, campus HD are never bottle-factory organic truth.
