# OmniView IQ — Pune ISBM-PET Facility POC

Edge-to-cloud IIoT monitoring for a PET bottle manufacturing plant. Captures real-time electrical, vibration, thermal, and pneumatic telemetry to prove three things with the site's own data: demand-penalty risk is detectable before the billing window closes, compressor "phantom run" waste has a measurable ₹ figure, and lazy-idle thermal degradation can be automatically flagged.

> **Status:** Sprint 1 — scaffolding + Day-1 data pipeline. No live hardware yet.

---

## Repo Structure

```
omniview-iq-poc/
├── src/omniview/            # Python package
│   ├── __init__.py          # Package root (v0.1.0)
│   ├── config.py            # Centralised .env config loader
│   ├── edge/                # Layer 2 — MQTT, Modbus poller, CSV injector
│   │   ├── mqtt_client.py   #   MQTT publish/subscribe         (OI-51)
│   │   └── injector.py      #   CSV → MQTT replay              (OI-12)
│   ├── ingest/              # Layer 3 — TimescaleDB writers
│   │   └── db.py            #   Hypertable helpers              (OI-54)
│   ├── rules/               # Layer 3–4 — Rule engine, PdM     (Lead track)
│   └── dashboard/           # Layer 6 — Streamlit live UI       (OI-68)
├── infra/
│   └── mosquitto/
│       └── mosquitto.conf   # Broker config (POC: anonymous)
├── Docs/                    # PRD, architecture, sprint planning
├── referance/               # Reference docs, notebooks, metaplan
├── docker-compose.yml       # Mosquitto + TimescaleDB
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Build config (editable install)
└── README.md                # ← You are here
```

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| **Docker** + Docker Compose | v24+ / v2+ | `docker --version` |
| **Python** | 3.11+ | `python --version` |
| **Git** | any | `git --version` |

---

## Quickstart — Local POC Run

### 1. Clone & configure environment

```bash
git clone <repo-url>
cd omniview-iq-poc

# Create your local .env from the template
cp .env.example .env
# Edit .env — at minimum, change TSDB_PASSWORD from 'changeme'
```

### 2. Start infrastructure

```bash
docker-compose up -d
```

This brings up:
- **Mosquitto** MQTT broker on `localhost:1883` (WebSocket on `9001`)
- **TimescaleDB** (PostgreSQL 16 + TimescaleDB) on `localhost:5432`

Verify both services are healthy:

```bash
docker-compose ps
```

You should see both containers with status `Up (healthy)`.

### 3. Install the Python package

```bash
# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install in editable mode
pip install -e .
```

### 4. Verify installation

```bash
python -c "import omniview; print(omniview.__version__)"
# → 0.1.0
```

### 5. Verify MQTT broker

```bash
# In one terminal — subscribe:
docker exec omniview-mosquitto mosquitto_sub -t "omniview/#" -v

# In another terminal — publish a test message:
docker exec omniview-mosquitto mosquitto_pub -t "omniview/test" -m '{"status": "ok"}'
```

### 6. Verify TimescaleDB

```bash
docker exec -it omniview-tsdb psql -U omniview -d omniview -c "SELECT version();"
```

---

## Day-1 Replay (OI-12)

The CSV → MQTT electrical injector seeds the full pipeline without live Modbus hardware.

```bash
# Replay from a CSV file (real transformer data from DevB OI-8)
python -m omniview.edge.injector --csv data/electrical_replay.csv

# Use built-in synthetic data (no CSV needed — great for demo)
python -m omniview.edge.injector --synthetic

# Fast replay (5× speed) for quicker demos
python -m omniview.edge.injector --synthetic --speed 5

# Burst mode — no delay, bulk-seeds TSDB immediately
python -m omniview.edge.injector --synthetic --burst --max 500

# Target a specific node
python -m omniview.edge.injector --synthetic --node isbm-01

# Loop a CSV indefinitely for continuous operation
python -m omniview.edge.injector --csv data/replay.csv --loop
```

Each row is published as a timestamped JSON payload to `omniview/pune-isbm/{node}/electrical` at the configured 15-second poll interval, feeding the TSDB and dashboard exactly as live Modbus data would.

---

## Stopping the Stack

```bash
docker-compose down           # Stop containers (data persists in volumes)
docker-compose down -v        # Stop + delete volumes (full reset)
```

---

## Team

| Person | Role | Track |
|--------|------|-------|
| **Dnyandev Sawarkar** | Lead — AI / Rules | Rule engine, PdM, monetize, acceptance |
| **vibhanshuinfo** | DevB — Data Units | Sensor schemas, Day-1 replay bots |
| **Chinmay Wadettiwar** | DevC — Platform | Edge → MQTT → TSDB → Dashboard |

Sprint board: [OI Sprint 1](https://mightium.atlassian.net/jira/software/projects/OI)

---

## Documentation

- [PRD & Architecture](Docs/architeture/OmniView_IQ_POC_Architecture_High_and_Low_Level.md)
- [Sprint Planning & Ownership](Docs/OI_Sprint_Planning_Person_Ownership.md)
- [System Workflow & Functional Units](Docs/OmniView_IQ_System_Workflow_and_Functional_Units.md)
- [Sensor Features](Docs/sesnor-fetures.md)
- [POC Features](Docs/POC-fetures.md)
