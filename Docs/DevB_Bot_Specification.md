# DevB Bot Specification — All 7 Sensor Bots

> **Author:** DevC (Chinmay) · **Date:** 2026-08-13  
> **Purpose:** Exact payload format, function signatures, and anomaly behavior for all 7 bots in `src/omniview/edge/bots/`. Share this with Vibhanshu for the 3 missing bots and fixes to the 4 existing ones.

---

## Overall Status

| Bot | File | Status | Issue |
|-----|------|--------|-------|
| Electrical | `electrical_bot.py` | ✅ Complete | All 12 schema fields present |
| Vibration | `vibration_bot.py` | ⚠️ **Schema mismatch** | Outputs 3 fields, schema requires 7 |
| Thermal | `thermal_bot.py` | ⚠️ **Schema mismatch** | Outputs 2 fields, schema requires 7 |
| Pressure | `pressure_bot.py` | ⚠️ **Schema mismatch** | Outputs 2 fields, schema requires 8 |
| Gas | `gas_bot.py` | ❌ **Missing** | Needs to be created |
| Stroke | `stroke_bot.py` | ❌ **Missing** | Needs to be created |
| Ambient | `ambient_bot.py` | ❌ **Missing** | Needs to be created |

> **CAUTION:** The 3 existing bots (vibration, thermal, pressure) were written before the schemas were upgraded to hardware-accurate parameters. They output simplified field names that **do not match their own schemas**. These must be fixed or they'll fail `jsonschema.validate()`.

---

## Mandatory Bot Contract

Every bot **MUST** follow this pattern:

```python
# File: src/omniview/edge/bots/{sensor}_bot.py

DEVICE_ID = "..."       # From node_registry.py (see Section 2)
POLL_INTERVAL = ...     # Seconds (see Section 2)

def generate_reading(is_anomaly: bool = False) -> dict:
    """Returns a single payload dict that passes jsonschema validation
    against the corresponding schema in schemas/{sensor}_schema.json.
    
    The payload MUST have this exact envelope:
    {
        "device_id": str,
        "timestamp": str (ISO 8601 + "Z"),
        "sensor_type": str (const from schema),
        "data": { ... all required fields ... }
    }
    """

def run_bot():
    """Infinite loop: generate_reading() → print(json.dumps(...)) → sleep(POLL_INTERVAL)
    Periodically sets is_anomaly=True to simulate fault conditions.
    """
```

---

## Device IDs & Poll Intervals (from `node_registry.py`)

| Sensor | Node | Device ID (use in bot) | Poll Interval |
|--------|------|------------------------|---------------|
| electrical | compressor-01 / isbm-01 | `Selec-MFM384-01` | 15s |
| vibration | compressor-01 | `Banner-QM30VT1-01` | 60s |
| thermal | compressor-01 / isbm-01 | `Omron-E5CC-01` | 60s |
| pressure | compressor-01 | `Festo-SPAU-01` | 60s |
| gas | compressor-01 | `Schneider-HeatTag-01` | 60s |
| stroke | isbm-01 | `Sick-IME-01` | 15s |
| ambient | floor | `Schneider-TH110-01` | 60s |

> **IMPORTANT:** The device IDs above come from the simulators and parsers that Vibhanshu already wrote. They must be consistent across parsers, bots, and schemas.

---

## Bot #1: Electrical ✅ (Complete — reference implementation)

**File:** `src/omniview/edge/bots/electrical_bot.py`  
**Schema:** `schemas/electrical_schema.json`  
**`sensor_type` const:** `"electrical_meter"`  
**Device ID:** `"Selec-MFM384-01"`  
**Status:** ✅ Already correct — all 12 required fields present. Use as the template.

### Expected Payload
```json
{
  "device_id": "Selec-MFM384-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "electrical_meter",
  "data": {
    "voltage_v_ln_avg": 239.5,
    "voltage_v_ll_avg": 414.8,
    "current_a_avg": 205.3,
    "active_power_kw_total": 140.2,
    "apparent_power_kva_total": 147.6,
    "reactive_power_kvar_total": 45.8,
    "power_factor_avg": 0.949,
    "frequency_hz": 50.02,
    "active_energy_kwh": 150042.5,
    "apparent_energy_kvah": 157544.6,
    "rolling_kva_15min": 148.1,
    "md_proximity_percent": 29.6
  }
}
```

---

## Bot #2: Vibration ⚠️ (Needs Fix)

**File:** `src/omniview/edge/bots/vibration_bot.py`  
**Schema:** `schemas/vibration_schema.json`  
**`sensor_type` const:** `"vibration_node"`  
**Device ID:** Change from `"gateway-001"` → `"Banner-QM30VT1-01"`

### Current Problem
The bot outputs 3 fields with wrong names:
```python
# ❌ CURRENT (wrong)
"rms_velocity_mm_s": ...,
"peak_acceleration_g": ...,
"surface_temperature_c": ...
```

### Required Payload (all 7 fields)
```json
{
  "device_id": "Banner-QM30VT1-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "vibration_node",
  "data": {
    "z_axis_rms_velocity_mm_sec": 2.1,
    "x_axis_rms_velocity_mm_sec": 1.5,
    "z_axis_peak_acceleration_g": 0.45,
    "x_axis_peak_acceleration_g": 0.33,
    "high_frequency_rms_acceleration_g": 0.38,
    "temperature_c": 42.5,
    "iso_health_zone": "ZONE_A"
  }
}
```

### Value Ranges (from `synthetic_data/config.py`)

| Field | Normal Range | Anomaly (Zone D) |
|-------|-------------|-------------------|
| `z_axis_rms_velocity_mm_sec` | 1.0 – 2.8 | 7.5 – 18.0+ |
| `x_axis_rms_velocity_mm_sec` | 0.8 – 2.0 | 5.0 – 12.0 |
| `z_axis_peak_acceleration_g` | 0.1 – 0.5 | 1.5 – 3.0 |
| `x_axis_peak_acceleration_g` | 0.08 – 0.4 | 1.0 – 2.5 |
| `high_frequency_rms_acceleration_g` | 0.1 – 0.5 | 1.5 – 4.0 |
| `temperature_c` | 38.0 – 58.0 | +15°C spike (bearing heat) |
| `iso_health_zone` | `ZONE_A` or `ZONE_B` | `ZONE_C` or `ZONE_D` |

### ISO 10816-3 Zone Logic (must be computed in bot)
```python
def classify_iso_zone(z_rms_velocity):
    if z_rms_velocity <= 2.8:   return "ZONE_A"  # Good
    elif z_rms_velocity <= 7.1: return "ZONE_B"  # Acceptable
    elif z_rms_velocity <= 18.0: return "ZONE_C" # Alert
    else:                        return "ZONE_D" # Danger
```

---

## Bot #3: Thermal ⚠️ (Needs Fix)

**File:** `src/omniview/edge/bots/thermal_bot.py`  
**Schema:** `schemas/thermal_schema.json`  
**`sensor_type` const:** `"thermal_probe"`  
**Device ID:** Change from `"gateway-001"` → `"Omron-E5CC-01"`

### Current Problem
The bot outputs 2 fields with wrong names:
```python
# ❌ CURRENT (wrong)
"surface_temperature_c": ...,
"ambient_temperature_c": ...
```

### Required Payload (all 7 fields)
```json
{
  "device_id": "Omron-E5CC-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "thermal_probe",
  "data": {
    "present_value_pv_c": 254.8,
    "set_point_sp_c": 255.0,
    "manipulated_variable_mv_heat_percent": 42.5,
    "heater_burnout_alarm_hb": false,
    "temperature_input_error": false,
    "temp_trend_15min": "STABLE",
    "machine_thermal_state": "AT_SETPOINT"
  }
}
```

### Value Ranges

| Field | Normal (AT_SETPOINT) | Heating Phase | Lazy Idle | Anomaly |
|-------|---------------------|---------------|-----------|---------|
| `present_value_pv_c` | 247.0 – 263.0 | 25.0 → 255.0 (ramp 4.5°C/min) | 240.0 – 260.0 | > 275.0 |
| `set_point_sp_c` | 255.0 (constant) | 255.0 | 255.0 | 255.0 |
| `manipulated_variable_mv_heat_percent` | 30.0 – 60.0 | 85.0 – 100.0 | 15.0 – 35.0 | 100.0 |
| `heater_burnout_alarm_hb` | `false` | `false` | `false` | `true` |
| `temperature_input_error` | `false` | `false` | `false` | `true` (thermocouple fault) |
| `temp_trend_15min` | `"STABLE"` | `"RISING"` | `"STABLE"` or `"FALLING"` | `"RISING"` |
| `machine_thermal_state` | `"AT_SETPOINT"` | `"HEATING"` | `"IDLE_HOT"` | `"AT_SETPOINT"` |

---

## Bot #4: Pressure ⚠️ (Needs Fix)

**File:** `src/omniview/edge/bots/pressure_bot.py`  
**Schema:** `schemas/pressure_schema.json`  
**`sensor_type` const:** `"pressure_transmitter"`  
**Device ID:** Change from `"gateway-001"` → `"Festo-SPAU-01"`

### Current Problem
The bot outputs 2 fields with wrong names:
```python
# ❌ CURRENT (wrong)
"pressure_bar": ...,
"decay_rate_bar_min": ...
```

### Required Payload (all 8 fields)
```json
{
  "device_id": "Festo-SPAU-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "pressure_transmitter",
  "data": {
    "process_data_variable_raw": 13500,
    "pressure_bar": 33.0,
    "switching_output_1_active": false,
    "switching_output_2_active": false,
    "device_status_code": 0,
    "internal_temperature_c": 32.5,
    "compressor_state": "LOADED",
    "pressure_trend_5min": "STABLE"
  }
}
```

### Value Ranges

| Field | Normal | Leak Anomaly | Compressor Off |
|-------|--------|-------------|----------------|
| `process_data_variable_raw` | 11000 – 14500 (14-bit, maps to bar) | Decreasing | 0 |
| `pressure_bar` | 28.0 – 36.0 | Decaying below 28.0 | 0.0 |
| `switching_output_1_active` | `false` | `true` (SP1 = low threshold) | `false` |
| `switching_output_2_active` | `false` | `true` (SP2 = critical) | `false` |
| `device_status_code` | `0` (OK) | `1` (Maintenance) | `0` |
| `internal_temperature_c` | 28.0 – 40.0 | 28.0 – 40.0 | 22.0 – 26.0 |
| `compressor_state` | `"LOADED"` or `"UNLOADED"` | `"LOADED"` | `"OFF"` |
| `pressure_trend_5min` | `"STABLE"` | `"FALLING"` | `"STABLE"` |

### Raw → Bar Conversion (Festo SPAU IO-Link)
```python
# 14-bit PDV: 0 = 0 bar, 16383 = 40 bar (0-40 bar range)
def raw_to_bar(raw_value: int) -> float:
    return round((raw_value / 16383) * 40.0, 2)

def bar_to_raw(pressure_bar: float) -> int:
    return int((pressure_bar / 40.0) * 16383)
```

---

## Bot #5: Gas ❌ (Missing — CREATE NEW)

**File:** `src/omniview/edge/bots/gas_bot.py`  
**Schema:** `schemas/gas_schema.json`  
**`sensor_type` const:** `"gas_particle_sensor"`  
**Device ID:** `"Schneider-HeatTag-01"`  
**Poll Interval:** 60s  
**Reference:** `synthetic_data/gas_simulator.py`

### Required Payload (all 5 fields)
```json
{
  "device_id": "Schneider-HeatTag-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "gas_particle_sensor",
  "data": {
    "gas_concentration_ppm": 1.25,
    "micro_particle_index": 3.50,
    "internal_panel_temp_c": 35.2,
    "rate_of_thermal_rise_c_per_min": 0.05,
    "alert_severity_level": "NORMAL"
  }
}
```

### Value Ranges

| Field | Normal | Warning | Alarm | Critical |
|-------|--------|---------|-------|----------|
| `gas_concentration_ppm` | 0.0 – 1.5 | 15.0 – 30.0 | 30.0 – 80.0 | 80.0 – 150.0 |
| `micro_particle_index` | 0.0 – 5.0 | 20.0 – 50.0 | 50.0 – 100.0 | 100.0 – 300.0 |
| `internal_panel_temp_c` | 30.0 – 40.0 | +0.5 – 2.5°C | +2.5 – 5.0°C | +5.0 – 8.0°C |
| `rate_of_thermal_rise_c_per_min` | -0.1 – 0.1 | 0.5 – 1.5 | 1.5 – 3.0 | 3.0 – 8.0 |
| `alert_severity_level` | `"NORMAL"` | `"WARNING"` | `"ALARM"` | `"CRITICAL"` |

### Anomaly Logic
```python
def compute_severity(gas_ppm, particle_idx):
    if gas_ppm > 80.0 or particle_idx > 100.0: return "CRITICAL"
    if gas_ppm > 30.0 or particle_idx > 50.0:  return "ALARM"
    if gas_ppm > 15.0 or particle_idx > 20.0:  return "WARNING"
    return "NORMAL"
```

---

## Bot #6: Stroke ❌ (Missing — CREATE NEW)

**File:** `src/omniview/edge/bots/stroke_bot.py`  
**Schema:** `schemas/stroke_schema.json`  
**`sensor_type` const:** `"digital_pulse_counter"`  
**Device ID:** `"Sick-IME-01"`  
**Poll Interval:** 15s  
**Reference:** `synthetic_data/stroke_simulator.py`

### Required Payload (all 7 fields)
```json
{
  "device_id": "Sick-IME-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "digital_pulse_counter",
  "data": {
    "switching_state_bdc1": true,
    "counter_value": 1500050,
    "device_temperature_c": 31.2,
    "operating_hours": 8005,
    "signal_quality": 252,
    "strokes_in_interval": 5,
    "last_cycle_time_seconds": 22.1
  }
}
```

### Value Ranges

| Field | Running (Shift) | Idle / Off | Slow Cycle Anomaly |
|-------|----------------|------------|---------------------|
| `switching_state_bdc1` | `true` 20% of polls (metal detected) | `false` | `true`/`false` |
| `counter_value` | Incrementing by 2–3 per minute | Static | Incrementing slowly |
| `device_temperature_c` | 28.0 – 35.0 | 22.0 – 25.0 | 28.0 – 35.0 |
| `operating_hours` | Incrementing (lifetime hours) | Incrementing | Incrementing |
| `signal_quality` | 240 – 255 | 240 – 255 | Degrades over days (dust/oil) |
| `strokes_in_interval` | 2 – 3 (per minute @ 22s/cycle) | 0 | 0 – 1 |
| `last_cycle_time_seconds` | 20.5 – 24.5 (nominal 22.0) | 0.0 | > 25.0 (slow cycle) |

### Cycle Time Config (from `synthetic_data/config.py`)
```python
NOMINAL_CYCLE_TIME_S = 22.0
CYCLE_TIME_VARIANCE_S = 1.5
SLOW_CYCLE_THRESHOLD_S = 25.0  # Above this = inefficient
```

---

## Bot #7: Ambient ❌ (Missing — CREATE NEW)

**File:** `src/omniview/edge/bots/ambient_bot.py`  
**Schema:** `schemas/ambient_schema.json`  
**`sensor_type` const:** `"ambient_weather"`  
**Device ID:** `"Schneider-TH110-01"`  
**Poll Interval:** 60s  
**Reference:** `synthetic_data/ambient_simulator.py`

### Required Payload (all 3 fields)
```json
{
  "device_id": "Schneider-TH110-01",
  "timestamp": "2026-08-13T17:00:00Z",
  "sensor_type": "ambient_weather",
  "data": {
    "ambient_temp_c": 32.5,
    "relative_humidity_pct": 55.0,
    "environmental_baseline_offset": 1.38
  }
}
```

### Value Ranges (from `synthetic_data/config.py`)

| Field | Range | Notes |
|-------|-------|-------|
| `ambient_temp_c` | 21.0 – 35.0 | Pune annual range. Daily swing ±5°C. Peak at 14:00, low at 05:00 |
| `relative_humidity_pct` | 35.0 – 85.0 | Inversely correlated with temp. Monsoon ~85%, dry ~35% |
| `environmental_baseline_offset` | 0.5 – 1.5+ | Edge-computed cooling load factor. 1.0 = baseline at 25°C. >1.0 means ambient is above baseline |

### Offset Computation
```python
def compute_baseline_offset(temp_c: float) -> float:
    """Normalizes around 25°C. Above 25°C, chiller works harder."""
    return max(0.5, 1.0 + ((temp_c - 25.0) * 0.05))
```

### Day/Night Cycle (no anomaly mode — ambient is environmental)
```python
import math

def generate_ambient_reading():
    hour = datetime.datetime.utcnow().hour
    time_in_hours = hour + (datetime.datetime.utcnow().minute / 60.0)
    
    # Pune climate: Peak at 14:00, lowest at 05:00
    phase = (time_in_hours - 14.0) / 24.0 * 2 * math.pi
    temp_c = 30.0 + (math.cos(phase) * 8.0) + random.uniform(-0.5, 0.5)
    rh_pct = 60.0 - (math.cos(phase) * 20.0) + random.uniform(-2.0, 2.0)
    offset = compute_baseline_offset(temp_c)
    # ...
```

---

## Summary of Required Changes

### 3 New Bots to Create
1. **`gas_bot.py`** — 5 data fields, severity classification logic, 60s poll
2. **`stroke_bot.py`** — 7 data fields, incrementing counter + cycle time, 15s poll
3. **`ambient_bot.py`** — 3 data fields, sinusoidal day/night cycle, 60s poll

### 3 Existing Bots to Fix

| Bot | Fix Required |
|-----|-------------|
| `vibration_bot.py` | Add 4 missing fields (`x_axis_rms_velocity_mm_sec`, `z/x_peak_acceleration_g`, `high_frequency_rms_acceleration_g`, `iso_health_zone`). Rename `rms_velocity_mm_s` → `z_axis_rms_velocity_mm_sec`, `surface_temperature_c` → `temperature_c`. Change device_id → `"Banner-QM30VT1-01"` |
| `thermal_bot.py` | Replace 2 fields with 7 schema fields (`present_value_pv_c`, `set_point_sp_c`, `manipulated_variable_mv_heat_percent`, `heater_burnout_alarm_hb`, `temperature_input_error`, `temp_trend_15min`, `machine_thermal_state`). Change device_id → `"Omron-E5CC-01"` |
| `pressure_bot.py` | Replace 2 fields with 8 schema fields (`process_data_variable_raw`, `pressure_bar`, `switching_output_1/2_active`, `device_status_code`, `internal_temperature_c`, `compressor_state`, `pressure_trend_5min`). Change device_id → `"Festo-SPAU-01"` |

### Update `bots/__init__.py` After Adding 3 New Bots

```python
"""
omniview.edge.bots — Synthetic Data Bots (Live Edge Simulators)
================================================================

Real-time sensor simulators that emit MQTT-like payloads for testing.
One bot per sensor family, 7 total.
"""

from omniview.edge.bots.electrical_bot import generate_synthetic_reading as generate_electrical
from omniview.edge.bots.vibration_bot import generate_reading as generate_vibration
from omniview.edge.bots.thermal_bot import generate_reading as generate_thermal
from omniview.edge.bots.pressure_bot import generate_reading as generate_pressure
from omniview.edge.bots.gas_bot import generate_reading as generate_gas
from omniview.edge.bots.stroke_bot import generate_reading as generate_stroke
from omniview.edge.bots.ambient_bot import generate_reading as generate_ambient
```

### Update Tests: `tests/test_bots.py`
Add tests for all 7 bots, not just electrical. Each test should:
1. Call `generate_reading(is_anomaly=False)` → verify all required fields present
2. Call `generate_reading(is_anomaly=True)` → verify anomaly values are in expected range
3. Validate the output against the JSON schema with `jsonschema.validate()`
