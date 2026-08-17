# OI-52 — Edge Config: device_id → Node Map: Session Worklog

**Date:** 17 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Epic:** [OI-33](https://mightium.atlassian.net/browse/OI-33) (Edge Gateway)  
**Branch:** `chinmay`  
**Depends on:** OI-41 (scaffold) ✅, OI-51 (MQTT topics + node_registry) ✅

---

## What Was the Task?

The `node_registry.py` (OI-51) defined nodes as a hardcoded Python dict, but lacked **device_id mapping** — the link between physical Modbus devices (with slave addresses, register maps, and protocol details) and logical nodes. The goal was to create a proper config file and schema that edge pollers (OI-13) and replay bots (OI-12) can load at runtime to know "this physical device at Modbus address X belongs to node `compressor-01` and polls these sensors at these intervals."

**Acceptance Criteria (all met ✅):**

- [x] Config file/schema exists
- [x] Both POC nodes represented (HP compressor + ISBM main feed)
- [x] Config map for device_id → node, sensor types, poll intervals
- [x] Used by edge pollers and replay bots (via loader module)
- [x] Unit tests (56 new tests, all passing)
- [x] Zero regressions (222/222 total tests pass)

---

## What Was Built

### 1. `config/edge_nodes.json` — Edge Device Config File

The single source of truth for the Pune ISBM-PET POC edge deployment. Maps 9 physical devices across 3 nodes:

| Node | Devices | Sensor Types |
|------|---------|-------------|
| **compressor-01** | 5 | electrical, vibration, pressure, thermal, gas |
| **isbm-01** | 3 | electrical, thermal, stroke |
| **floor** | 1 | ambient |

Each device entry includes:

| Field | Purpose |
|-------|---------|
| `device_id` | Globally unique identifier (e.g. `pune-comp-mfm384`) |
| `sensor_type` | One of the 7 canonical types from `topics.py` |
| `hardware` | Make/model (e.g. `Selec MFM384-C-CE`) |
| `protocol` | `modbus_rtu`, `wireless_modbus`, `4-20mA_modbus` |
| `modbus_slave_address` | Modbus RTU address (1–247) |
| `poll_interval_s` | Poll cadence: 15s electrical (FR1), 60s physical |
| `register_map` | Field → {address, count, type, unit} Modbus mapping |
| `notes` | Installation notes, PRD cross-references |

Also includes site-level metadata (contracted demand 500 kVA, MSEDCL HT-I tariff, timezone) and gateway serial config (RUT956, 9600 baud, 8N1).

### 2. `schemas/edge_config_schema.json` — Validation Schema

JSON Schema (draft-07) that validates:
- Required top-level fields (`config_version`, `site`, `nodes`)
- Semver pattern on `config_version`
- `device_id` regex pattern (`^[a-z0-9][a-z0-9\-]*$`)
- `sensor_type` enum matching the 7 canonical families
- `modbus_slave_address` range (1–247 per Modbus spec)
- `poll_interval_s` minimum of 1
- Nested `register_entry` structure for Modbus field mappings
- Standard baud rates, parity, data bits

### 3. `src/omniview/edge/device_config.py` — Config Loader Module

| Component | Purpose |
|-----------|---------|
| `EdgeConfig` | Loaded config object with indexed lookups |
| `load_edge_config()` | Load JSON + validate against schema |
| `get_default_config()` | Convenience wrapper for standard path |
| `EdgeConfigError` | Custom exception for config failures |

**Key APIs on `EdgeConfig`:**

```python
cfg = load_edge_config()

cfg.site_id                              # "pune-isbm"
cfg.contracted_demand_kva                # 500
cfg.get_device("pune-comp-mfm384")       # full device dict
cfg.get_node_for_device("pune-comp-vib01")  # "compressor-01"
cfg.get_poll_interval("pune-isbm-mfm384")   # 15
cfg.get_sensor_type("pune-comp-wika01")     # "pressure"
cfg.get_devices_by_sensor_type("electrical")  # [comp, isbm]
cfg.get_register_map("pune-comp-mfm384")    # Modbus register map
cfg.get_devices_for_node("compressor-01")   # 5 devices
cfg.get_all_device_ids()                    # sorted list of 9 device_ids
```

### 4. Updated `src/omniview/edge/__init__.py`

Added `EdgeConfig` and `load_edge_config` to public API exports.

---

## Files Created/Modified (5 total)

```
 NEW  config/edge_nodes.json                    — Device config (9 devices, 3 nodes)
 NEW  schemas/edge_config_schema.json           — JSON Schema for validation
 NEW  src/omniview/edge/device_config.py        — Config loader module
 MOD  src/omniview/edge/__init__.py             — Added EdgeConfig, load_edge_config
 NEW  tests/test_device_config.py               — 56 unit tests
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_device_config.py -v` | ✅ 56/56 passed |
| `pytest tests/ -v` (full suite) | ✅ 222/222 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.edge import EdgeConfig, load_edge_config` |
| Config loads and validates | ✅ Schema validation passes |
| Both POC nodes present | ✅ compressor-01 (5 devices), isbm-01 (3 devices) |
| device_id uniqueness enforced | ✅ Duplicate detection raises EdgeConfigError |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| **JSON config (not YAML)** | Avoids adding PyYAML dependency. JSON is native to Python, matches existing schemas/ directory pattern, and jsonschema already in requirements. |
| **Separate from `node_registry.py`** | `node_registry.py` (OI-51) is a lightweight in-memory lookup. `device_config.py` adds file-based loading, schema validation, and device_id resolution. Both can coexist — registry for quick topic generation, config for full Modbus setup. |
| **device_id uniqueness enforced at load time** | Prevents silent config errors. A duplicate device_id would cause ambiguous routing in the poller. Fail-fast at startup, not at runtime. |
| **Register maps included but optional** | Not all devices need register maps (e.g., during synthetic replay). Required fields are device_id, sensor_type, hardware, protocol, poll_interval_s. Register maps are used by the Modbus poller (OI-13) when hardware is live. |
| **Schema validates `modbus_slave_address` range 1–247** | Per Modbus RTU spec, address 0 is broadcast, 248–255 are reserved. Catches config typos. |
| **Site metadata in config** | `contracted_demand_kva`, `utility`, `tariff_category` in one place. Previously only in `.env` / `config.py`. Now the edge config is self-contained for per-site deployment. |
| **`get_devices_by_sensor_type()` cross-node query** | Useful for the rule engine: "give me all electrical devices" regardless of which node they're on. Avoids the consumer needing to iterate nodes manually. |
| **Missing schema warns but doesn't crash** | If someone deletes the schema file, the config still loads (with a warning). Prevents hard failures in environments where only the config was deployed. |

---

## Dependency Analysis (Pre-Task)

| Question | Answer |
|----------|--------|
| **Depends on other devs?** | No. Config is self-contained based on PRD §1.4 and architecture docs. |
| **Requires physical hardware?** | No. This is a config/schema definition task. The Modbus addresses and register maps are from device datasheets. |
| **Blocks other work?** | Unblocks OI-13 (physical sensor poller) which needs device_id → Modbus address mapping. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-13 | Physical Modbus sensor poller | Edge config ✅ (register maps + slave addresses) |
| **Chinmay** | OI-53 | NTP drift guard | Edge config ✅ (gateway NTP settings) |
| **Chinmay** | OI-68 | Live dashboard | Edge config ✅ (site metadata for hero metrics) |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert rule | Edge config ✅ (contracted_demand_kva) |

---

*Session completed: 17 August 2026, 11:20 PM IST*
