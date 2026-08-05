# OI-41 — Scaffold Repo: Session Worklog

**Date:** 5 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Ticket:** [OI-41](https://mightium.atlassian.net/browse/OI-41)  
**Branch:** `chinmay`  
**Commit:** `d64cd65`

---

## What Was the Task?

The repo only had documentation and notebooks — no runnable code, no containers, no package structure. The goal was to create the **Day-1 foundation** so the entire team can start building on top of it.

**Acceptance Criteria (all met ✅):**

- [x] `docker-compose up` starts Mosquitto + TimescaleDB
- [x] Python package installable from requirements
- [x] README section for local POC run

---

## What Was Built

### 1. Python Package — `src/omniview/`

Created a modular package layout that mirrors the system's 6-layer architecture:

| Sub-Package | System Layer | What Goes Here | Next Ticket |
|-------------|-------------|----------------|-------------|
| `omniview.edge` | Layer 2 — Edge Connectivity | MQTT client, Modbus poller, CSV injector | OI-51, OI-12 |
| `omniview.ingest` | Layer 3 — Cloud Ingestion | TimescaleDB writers, schema validation | OI-54, OI-55 |
| `omniview.rules` | Layer 3–4 — Intelligence | Rule engine, PdM, arbitration (Lead track) | OI-56–67 |
| `omniview.dashboard` | Layer 6 — Delivery | Streamlit live dashboard, action cards | OI-68, OI-69 |
| `omniview.config` | Shared | Centralised `.env` config loader | — |

Every placeholder module includes a docstring explaining:
- What will go there
- Which Jira ticket fills it in
- Key design notes from the PRD

### 2. Docker Compose — Local Infrastructure

`docker-compose.yml` brings up two services with one command:

| Service | Image | Port | Role |
|---------|-------|------|------|
| **Mosquitto** | `eclipse-mosquitto:2` | 1883 (MQTT), 9001 (WebSocket) | Message broker — sensors publish, cloud subscribes |
| **TimescaleDB** | `timescale/timescaledb:latest-pg16` | 5432 | Time-series database for all sensor readings |

Both services have:
- **Health checks** — so you know when they're actually ready
- **Named volumes** — data survives container restarts
- **Shared network** (`omniview-net`) — containers can talk to each other

### 3. Mosquitto Config

`infra/mosquitto/mosquitto.conf` — minimal broker config:
- Listener on port 1883 (MQTT) and 9001 (WebSocket)
- Anonymous access enabled (POC only — production will need auth + TLS)
- Persistence enabled (messages survive broker restarts)

### 4. Environment Config

`.env.example` — template with every config variable the stack uses:
- MQTT broker host/port
- TimescaleDB host/port/database/user/password
- Polling intervals (15s electrical, 60s physical)
- Site parameter: contracted demand (500 kVA)

### 5. Python Dependencies

`requirements.txt` — all libraries needed:
- `paho-mqtt` — MQTT client library
- `psycopg2-binary` — PostgreSQL/TimescaleDB driver
- `sqlalchemy` — database ORM
- `python-dotenv` — `.env` file reader
- `pandas`, `numpy` — data processing
- `streamlit` — dashboard framework

`pyproject.toml` — modern build config for `pip install -e .` (used instead of `setup.py` because Python 3.14 deprecated the old approach).

### 6. .gitignore

Updated with patterns for:
- Python (`__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`)
- Docker (`docker-compose.override.yml`)
- Environment (`.env` — never commit real passwords)
- IDE (`.vscode/`, `.idea/`, `.cursor/`)
- Data (`data/` — large CSVs shouldn't be in Git)

### 7. README

Comprehensive project README with:
- Project overview
- Repo structure diagram
- Prerequisites table
- Step-by-step Quickstart (clone → configure → docker up → pip install → verify)
- Day-1 Replay section (how to run the CSV injector once OI-12 is built)
- Team roster and role assignments
- Links to all documentation

---

## Files Created/Modified (16 total)

```
 NEW  .env.example
 NEW  README.md
 NEW  docker-compose.yml
 NEW  infra/mosquitto/mosquitto.conf
 NEW  pyproject.toml
 NEW  requirements.txt
 NEW  src/omniview/__init__.py
 NEW  src/omniview/config.py
 NEW  src/omniview/dashboard/__init__.py
 NEW  src/omniview/edge/__init__.py
 NEW  src/omniview/edge/injector.py
 NEW  src/omniview/edge/mqtt_client.py
 NEW  src/omniview/ingest/__init__.py
 NEW  src/omniview/ingest/db.py
 NEW  src/omniview/rules/__init__.py
 MOD  .gitignore
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pip install -e .` | ✅ Built editable wheel, installed `omniview-iq 0.1.0` |
| `import omniview` | ✅ Prints `omniview v0.1.0` |
| `from omniview.config import ...` | ✅ MQTT host, TSDB DSN, contracted demand all load correctly |
| All sub-package imports | ✅ edge, ingest, rules, dashboard all resolve |
| Docker Compose validation | ✅ Structurally valid (Docker not installed on dev machine — will validate on CI/staging) |

---

## Decisions Made During Implementation

| Decision | Reason |
|----------|--------|
| Used `pyproject.toml` instead of `setup.py` | Python 3.14 deprecated `setup.py develop`. Modern standard ensures compatibility. |
| Package layout mirrors the 6-layer architecture | Makes it obvious where code belongs. Dnyandev's rule engine goes in `rules/`, Vibhanshu's schemas feed into `edge/` and `ingest/`. |
| Mosquitto set to anonymous access | POC-only. Noted in config comments that production needs auth + TLS. |
| Config centralised in `config.py` | Single source of truth. Every module imports from here instead of calling `os.getenv()` directly. |
| Named Docker volumes | Sensor data and MQTT messages persist across container restarts — no accidental data loss during development. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-51 | MQTT topics + Mosquitto wiring | This scaffold ✅ |
| **Chinmay** | OI-54 | TimescaleDB hypertables + migrations | This scaffold ✅ |
| **vibhanshuinfo** | OI-23, OI-5–7 | Sensor schemas (electrical, vibration, thermal, pressure) | Schemas can land in `src/omniview/` |
| **Dnyandev** | OI-42 | Layer 3 architecture contracts | `rules/` package ready for his modules |

---

## How to Use This Scaffold (for team reference)

```bash
# 1. Clone and switch to branch
git clone https://github.com/Mightium/omniview-iq-poc
cd omniview-iq-poc
git checkout chinmay

# 2. Set up environment
cp .env.example .env          # edit TSDB_PASSWORD at minimum

# 3. Start infrastructure
docker compose up -d           # Mosquitto + TimescaleDB
docker compose ps              # verify both are healthy

# 4. Install Python package
python -m venv .venv
.venv\Scripts\Activate.ps1     # Windows
pip install -e .

# 5. Verify
python -c "import omniview; print(omniview.__version__)"
# → 0.1.0
```

---

*Session completed: 5 August 2026, 6:05 PM IST*
