# DevB Restructure Guide — Aligning `Vib_branch` to Project Structure

> **Author:** DevC (Chinmay) · **Date:** 2026-08-13  
> **Purpose:** This document tells Vibhanshu's AI agent exactly how to reorganise `Vib_branch` so it merges cleanly into the `chinmay` branch (the integration trunk). Follow every step — the target structure is non-negotiable.

---

## 1. Why This Matters

The `chinmay` branch uses a proper **installable Python package** layout under `src/omniview/`. Your `Vib_branch` has everything at root-level (`edge/`, `schemas/`, `synthetic_data/`). A direct merge will create duplicate, conflicting hierarchies. This guide maps every file in your branch to its correct destination.

---

## 2. Golden Rule: The Package Layout

```
omniview-iq-poc/
├── src/
│   └── omniview/                     # The importable package
│       ├── __init__.py
│       ├── config.py                 # Centralised env-based config
│       ├── edge/                     # Layer 2 — Edge connectivity
│       │   ├── __init__.py
│       │   ├── mqtt_client.py        # MQTT pub/sub client (OI-51)
│       │   ├── topics.py             # Topic hierarchy contract
│       │   ├── node_registry.py      # Device/node map
│       │   ├── injector.py           # CSV → MQTT replay
│       │   ├── offline_buffer.py     # SQLite offline cache (OI-28)
│       │   ├── parsers/              # ← YOUR PARSERS GO HERE (NEW)
│       │   │   ├── __init__.py
│       │   │   ├── modbus_parser.py
│       │   │   ├── vibration_parser.py
│       │   │   ├── thermal_parser.py
│       │   │   ├── pressure_parser.py
│       │   │   ├── stroke_parser.py
│       │   │   ├── gas_parser.py
│       │   │   └── ambient_parser.py
│       │   └── bots/                 # ← YOUR BOTS GO HERE (NEW)
│       │       ├── __init__.py
│       │       ├── electrical_bot.py
│       │       ├── pressure_bot.py
│       │       ├── thermal_bot.py
│       │       └── vibration_bot.py
│       ├── ingest/                   # Layer 3 — Cloud ingest
│       │   ├── __init__.py
│       │   ├── subscriber.py
│       │   ├── validation.py         # ← YOUR SCHEMAS LOADED HERE
│       │   ├── db.py
│       │   └── migrations.py
│       ├── rules/                    # Layer 4 — Rule engine
│       │   └── __init__.py
│       └── dashboard/                # Layer 5 — Dashboard
│           └── __init__.py
├── schemas/                          # ← KEEP AT REPO ROOT (shared resource)
│   ├── electrical_schema.json
│   ├── vibration_schema.json
│   ├── thermal_schema.json
│   ├── pressure_schema.json
│   ├── stroke_schema.json
│   ├── gas_schema.json
│   └── ambient_schema.json
├── synthetic_data/                   # ← KEEP AT REPO ROOT (tooling, not library)
│   ├── config.py
│   ├── *_generator.py
│   ├── *_simulator.py
│   ├── timeline.py
│   ├── verify.py
│   └── output/                       # Generated artifacts
├── data/                             # ← KEEP AT REPO ROOT (gitignored large files)
│   ├── raw_*.txt
│   └── parsed_*.jsonl
├── tests/
│   ├── test_mqtt_client.py
│   ├── test_subscriber.py
│   ├── test_offline_buffer.py
│   ├── test_validation.py
│   ├── test_parsers.py               # ← NEW: tests for your parsers
│   └── test_bots.py                  # ← NEW: tests for your bots
├── Docs/
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## 3. File-by-File Migration Map

### 3.1 Parsers: `edge/` → `src/omniview/edge/parsers/`

| Current Location (Vib_branch)   | New Location                                        |
|---------------------------------|-----------------------------------------------------|
| `edge/modbus_parser.py`         | `src/omniview/edge/parsers/modbus_parser.py`        |
| `edge/vibration_parser.py`      | `src/omniview/edge/parsers/vibration_parser.py`     |
| `edge/thermal_parser.py`        | `src/omniview/edge/parsers/thermal_parser.py`       |
| `edge/pressure_parser.py`       | `src/omniview/edge/parsers/pressure_parser.py`      |
| `edge/stroke_parser.py`         | `src/omniview/edge/parsers/stroke_parser.py`        |
| `edge/gas_parser.py`            | `src/omniview/edge/parsers/gas_parser.py`           |
| `edge/ambient_parser.py`        | `src/omniview/edge/parsers/ambient_parser.py`       |

### 3.2 Bots: `edge/` → `src/omniview/edge/bots/`

| Current Location (Vib_branch)   | New Location                                        |
|---------------------------------|-----------------------------------------------------|
| `edge/electrical_bot.py`        | `src/omniview/edge/bots/electrical_bot.py`          |
| `edge/pressure_bot.py`          | `src/omniview/edge/bots/pressure_bot.py`            |
| `edge/thermal_bot.py`           | `src/omniview/edge/bots/thermal_bot.py`             |
| `edge/vibration_bot.py`         | `src/omniview/edge/bots/vibration_bot.py`           |

### 3.3 Schemas: `schemas/` → `schemas/` (no change, stays at repo root)

All 7 schema JSON files stay at `schemas/` at the repo root. **No move needed.**

### 3.4 Synthetic Data: `synthetic_data/` → `synthetic_data/` (no change)

All generators, simulators, `config.py`, `timeline.py`, `verify.py`, and `output/` stay at `synthetic_data/` at the repo root. **No move needed.**

### 3.5 Data: `data/` → `data/` (no change, but add to `.gitignore`)

Large `.jsonl` and `.txt` dumps stay at `data/`. **But add these to `.gitignore`** — they should not be tracked in git (302,407+ lines of generated data):

```gitignore
# Generated sensor data (re-generate with synthetic_data/ scripts)
data/raw_*.txt
data/parsed_*.jsonl
synthetic_data/output/*.parquet
```

### 3.6 Docs: Root-level `.md` files → `Docs/`

| Current Location (Vib_branch)        | New Location                              |
|--------------------------------------|-------------------------------------------|
| `datastream_context.md`              | `Docs/datastream_context.md`              |
| `pipeline_and_references.md`         | `Docs/pipeline_and_references.md`         |
| `pneumatic_pressure_parameter_prd.md`| `Docs/pneumatic_pressure_parameter_prd.md`|

---

## 4. Code Changes Required After Moving Files

### 4.1 Fix All Import Paths in Parsers

Every parser currently does:
```python
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "some_schema.json"
DATA_DIR = Path(__file__).parent.parent / "data"
```

After the move, `__file__` will be at `src/omniview/edge/parsers/`, so the paths need to go up 4 levels to reach repo root:

```python
# NEW — correct path from src/omniview/edge/parsers/
_REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = _REPO_ROOT / "schemas" / "some_schema.json"
DATA_DIR = _REPO_ROOT / "data"
```

**OR BETTER** — use our centralised `config.py` pattern:

```python
from omniview.config import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "schemas" / "vibration_schema.json"
DATA_DIR = REPO_ROOT / "data"
```

> ⚠️ **Action:** Add `REPO_ROOT` to `src/omniview/config.py` if not present:
> ```python
> REPO_ROOT: Path = Path(__file__).resolve().parents[2]
> ```

### 4.2 Fix Import Paths in Bots

Same pattern as parsers — update `Path(__file__)` references and switch to `from omniview.config import ...`.

### 4.3 Create `__init__.py` Files

Create these new `__init__.py` files:

**`src/omniview/edge/parsers/__init__.py`:**
```python
"""
omniview.edge.parsers — Sensor Data Parsers
=============================================

Raw serial/CSV → structured JSON payloads, validated against DevB schemas.
"""

from omniview.edge.parsers.modbus_parser import parse_modbus_string
from omniview.edge.parsers.vibration_parser import parse_vibration_string
from omniview.edge.parsers.thermal_parser import parse_thermal_string
from omniview.edge.parsers.pressure_parser import parse_pressure_string
from omniview.edge.parsers.stroke_parser import parse_stroke_string
from omniview.edge.parsers.gas_parser import parse_gas_string
from omniview.edge.parsers.ambient_parser import parse_ambient_string

__all__ = [
    "parse_modbus_string",
    "parse_vibration_string",
    "parse_thermal_string",
    "parse_pressure_string",
    "parse_stroke_string",
    "parse_gas_string",
    "parse_ambient_string",
]
```

**`src/omniview/edge/bots/__init__.py`:**
```python
"""
omniview.edge.bots — Synthetic Data Bots (Live Edge Simulators)
================================================================

Real-time sensor simulators that emit MQTT-like payloads for testing.
"""
```

### 4.4 Update `src/omniview/edge/__init__.py`

Add the parsers subpackage to the edge layer's public API:

```python
# Add after existing imports:
from omniview.edge import parsers
```

### 4.5 Integrate Schemas into `src/omniview/ingest/validation.py`

Our `validation.py` currently has a placeholder schema. **Replace the placeholder with your real schemas:**

```python
import json
from pathlib import Path

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"

def _load_schema(filename: str) -> dict | None:
    path = _SCHEMA_DIR / filename
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return None

# Mapping of sensor_type (from topics.py) → JSON schema
_SCHEMAS = {
    "electrical":  _load_schema("electrical_schema.json"),
    "vibration":   _load_schema("vibration_schema.json"),
    "thermal":     _load_schema("thermal_schema.json"),
    "pressure":    _load_schema("pressure_schema.json"),
    "stroke":      _load_schema("stroke_schema.json"),
    "gas":         _load_schema("gas_schema.json"),
    "ambient":     _load_schema("ambient_schema.json"),
}
```

> ⚠️ **Critical:** The `sensor_type` keys **MUST** match the values in `src/omniview/edge/topics.py` → `SENSOR_TYPES` frozenset. Currently defined as: `electrical`, `vibration`, `thermal`, `pressure`, `gas`, `stroke`, `ambient`.

> ⚠️ **Critical:** Your schemas use `sensor_type` values like `"pressure_transmitter"`, `"vibration_node"`, `"electrical_meter"` in the payload `const` fields. These must be **reconciled** with our `SENSOR_TYPES` enum. Either:
> 1. Change your schema `const` values to match our enum (`pressure`, `vibration`, `electrical`), or  
> 2. Add a mapping layer in the parsers. **Option 1 is preferred.**

---

## 5. Do NOT Modify These Files

These files exist on `chinmay` and should **not** be overwritten or deleted by your branch:

| File | Owner | Reason |
|------|-------|--------|
| `src/omniview/config.py` | DevC | You may **append** new config vars, but do not remove existing ones |
| `src/omniview/edge/mqtt_client.py` | DevC | MQTT client with QoS + offline buffer integration |
| `src/omniview/edge/offline_buffer.py` | DevC | SQLite offline storage (OI-28) |
| `src/omniview/edge/topics.py` | DevC | Topic hierarchy — your `sensor_type` values must align with this |
| `src/omniview/edge/injector.py` | DevC | CSV→MQTT replay |
| `src/omniview/edge/node_registry.py` | DevC | Device map |
| `src/omniview/ingest/subscriber.py` | DevC | MQTT subscriber with validation hooks |
| `src/omniview/ingest/db.py` | DevC | TimescaleDB writer |
| `src/omniview/ingest/migrations.py` | DevC | DB migration runner |
| `pyproject.toml` | DevC | You may **append** dependencies, but do not rewrite |
| `requirements.txt` | DevC | Same — append only |
| `docker-compose.yml` | DevC | Do not delete |
| `.env.example` | DevC | Do not delete |
| `tests/test_mqtt_client.py` | DevC | Do not overwrite |
| `tests/test_subscriber.py` | DevC | Do not overwrite |
| `tests/test_offline_buffer.py` | DevC | Do not overwrite |
| `tests/test_validation.py` | DevC | Do not overwrite — but you can ADD schemas to make existing tests pass with real data |

---

## 6. Dependencies to Add

Append these to **both** `requirements.txt` and `pyproject.toml` `[project.dependencies]` if not already present:

```
jsonschema>=4.20.0
```

This is already in our `requirements.txt`, so just confirm it's there.

---

## 7. Files to Delete from Your Branch

Remove these before merging — they are either duplicates or should not be in the repo:

| File | Reason |
|------|--------|
| `edge/__pycache__/*` | Build artifact — should be in `.gitignore` |
| `synthetic_data/__pycache__/*` | Build artifact — should be in `.gitignore` |
| All `data/raw_*.txt` (43K+ lines each) | Generated data — add to `.gitignore`, regenerate locally |
| All `data/parsed_*.jsonl` (43K+ lines each) | Generated data — add to `.gitignore`, regenerate locally |
| `synthetic_data/output/*.parquet` | Generated data — add to `.gitignore`, regenerate locally |

> ⚠️ **These files total ~600K+ lines and ~60MB+.** They must be removed from git history too, ideally with `git filter-branch` or BFG Repo Cleaner, or at minimum removed from the working tree before the merge PR.

---

## 8. `.gitignore` Additions

Append these lines to `.gitignore`:

```gitignore
# Generated sensor data (re-generate locally with synthetic_data/ scripts)
data/raw_*.txt
data/parsed_*.jsonl
synthetic_data/output/*.parquet
synthetic_data/output/*.csv

# Python cache
__pycache__/
*.pyc
```

---

## 9. Checklist Before Merge

- [ ] All parsers moved to `src/omniview/edge/parsers/`
- [ ] All bots moved to `src/omniview/edge/bots/`
- [ ] All `Path(__file__)` references updated for new directory depth
- [ ] `__init__.py` created for `parsers/` and `bots/` subpackages
- [ ] `sensor_type` values in schemas reconciled with `topics.py` `SENSOR_TYPES`
- [ ] Schema loading integrated into `validation.py` (or separate `schema_loader.py`)
- [ ] Root-level `.md` docs moved to `Docs/`
- [ ] Large generated data files removed from git tracking
- [ ] `.gitignore` updated
- [ ] No DevC files overwritten or deleted
- [ ] `jsonschema` dependency confirmed in `requirements.txt`
- [ ] All existing tests still pass (`pytest tests/`)
- [ ] New tests added for parsers (`tests/test_parsers.py`)

---

## 10. Quick Validation After Restructure

Run from repo root:

```bash
# 1. Confirm package imports work
python -c "from omniview.edge.parsers import parse_modbus_string; print('OK')"

# 2. Confirm schemas load
python -c "from omniview.ingest.validation import _SCHEMAS; print([k for k,v in _SCHEMAS.items() if v])"

# 3. Run full test suite
pytest tests/ -v
```

---

**Questions?** Ping DevC (Chinmay) in the team channel. Do NOT guess at structure — ask first.
