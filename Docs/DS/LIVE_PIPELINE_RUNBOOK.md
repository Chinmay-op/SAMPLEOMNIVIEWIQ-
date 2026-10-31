# Live pipeline runbook

**Status:** Active (compose + TSDB exist on DevC/`main`; Owner TSDB feed lands on `integration/live-spine` after P1)  
**Date:** 2026-08-17

Bring-up order: broker + DB → subscriber → bots/injector → Owner BFF (`OWNER_FEED=tsdb`) → UI.

## 1. Prerequisites

- Docker Desktop (Mosquitto + TimescaleDB via `docker-compose.yml` on DevC/`integration`)
- Python env: repo `.venv` (`uv sync` / project requirements)
- Node for Owner UI (`Owner-dashboard/frontend`)
- `.env` copied from `.env.example` — **no secrets in git**

Typical env keys (schema only; values local):

```text
MQTT_HOST=
MQTT_PORT=
MQTT_CLIENT_ID=
MQTT_QOS=
SITE_ID=
TIMESCALE_DSN=
OWNER_FEED=tsdb
OMNIVIEW_SITE_PROFILE=bottle_factory_poc
```

## 2. Compose up (DevC spine)

From repo root **on a branch that contains `docker-compose.yml`** (`main`, `chinmay`, or `integration/live-spine`):

```bash
docker compose up -d
# Mosquitto + TimescaleDB
```

Apply hypertables / migrations (DevC ingest):

```bash
# as documented on that branch, typically:
.venv/bin/python -m omniview.ingest.migrations
```

## 3. Subscriber then publishers

```bash
.venv/bin/python -m omniview.ingest.subscriber
# then bots or injector (synthetic: true)
.venv/bin/python -m omniview.edge.smoke_test_mqtt
```

Topic pattern: `omniview/{site_id}/{node_id}/{short_type}`  
Payload `sensor_type` is the **long** schema const (`electrical_meter`, …). Map; do not collapse.

## 4. Smoke: MQTT → TSDB

Expect at least one row each for electrical, pressure, thermal after a short bot run. Query via DevC `omniview.ingest.db` helpers or `psql` against hypertables.

Round-trip checklist:

- [ ] Broker accepting connections
- [ ] Subscriber inserting JSONB / typed columns
- [ ] `synthetic` preserved
- [ ] `device_id` + UTC timestamp present

## 5. Owner live (after P1 on integration)

```bash
export OWNER_FEED=tsdb
cd Owner-dashboard/backend
PYTHONPATH=../../src ../../.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8020

cd ../frontend
npm install && npm run dev
# http://127.0.0.1:5175
```

Fallback without Docker (CI / laptop): `OWNER_FEED=correlated` or master CSV — UI must keep the synthetic honesty banner.

## 6. Detectors on DB windows (P2)

Workers (or on-demand BFF) run Lead rules only:

| Window | Rule |
|--------|------|
| Electrical 15-min | `md_risk` / `demand_window` |
| Thermal + current | `lazy_idle` |
| Pressure loaded | `pressure_leak` |
| Vibration RMS | `vibration_zone` (when pack exists) |
| PdM features | `predict_maintenance_risk` |

Lab ML scores may display labeled **lab-only**. They are not Layer3 alerts.

## 7. Honesty and HITL

Bots and public replay stay `synthetic: true`. Action cards recommend only — no actuation.

## 8. Troubleshooting

| Symptom | Check |
|---------|--------|
| Owner empty | `OWNER_FEED`, DSN, subscriber running |
| Topic vs schema mismatch | short type vs long `sensor_type` map |
| MD numbers “wrong” | Do not change formula — check adapter `kva` / `kw`+`var` mapping |
| yash has no compose | You are on Lead stable; use `integration/live-spine` or DevC branch |
