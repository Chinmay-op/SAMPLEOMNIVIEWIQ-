# Detector attach matrix

**Status:** Active  
**Date:** 2026-08-17  
**Product path:** Timescale window → Lead adapter → Layer3 rule → Owner screen  
**Offline path:** CSV / correlated (labeled synthetic)

Layer3 SoT never auto-replaced by pack ML.

| Goal | Layer3 SoT | Lab ML | Wire → sample | DB (DevC) | Owner surface today (`yash`) | Live attach (integration P1+) |
|------|------------|--------|---------------|-----------|------------------------------|-------------------------------|
| 1 HD / MD | `demand_window` + `md_risk` | HD pack xgboost / slots | `apparent_power_kva_total` or `kw`+`kvar` → `kva` / `kw`+`var` | electrical hypertable | `/api/power/*` from processed CSV / master | Poll electrical 15-min window |
| 2 Idle | `lazy_idle` OI-57 | `idle_models.py` `lab_only` | `present_value_pv_c` + `current_a_avg` → `zone_temp_c`, `current_a` | thermal + electrical | `/api/idle/replay` file/correlated | Same rules on DB rows |
| 3 Pressure | `pressure_leak` OI-59 | leak ML JSON | `pressure_bar`, `compressor_state`→`loaded` | pressure hypertable | `/api/pressure/replay` CSV/correlated; **BFF does not score leak ML** | Leak/hold/capacity/health from DB |
| 4 Vibration | `vibration_zone` OI-58 (to build) | none yet | `z_axis_rms_velocity_mm_sec` (or max XYZ) + `temperature_c` → `rms_velocity_mms`, `surface_temp_c` | vibration hypertable (schema on DevB/DevC) | **No Owner screen** | Pack + `/api/vibration/*` + Events |
| 5 Motor health | `maintenance_risk` Stage A + compose hold/heat/current | Colab extras not extracted | pressure capacity + thermal + electrical motor current + PdM features | compose families | **No Owner screen**; `predictive_maintenance.py` exists | `/api/motor/health` + Motor screen |
| 6 Owner UI | n/a | n/a | n/a | n/a | Lab 6-screen shell, JSON dumps on Events | Operator console, severity rail |
| 7 Live pipe | n/a | n/a | envelope §2 plug doc | Mosquitto + Timescale on `main` | **Not on yash** | `OWNER_FEED=tsdb` |
| 8 Explainer | n/a | n/a | n/a | n/a | Capsule / ADR / pack docs | This D0 set + `OWNER_LIVE_SYSTEM_EXPLAINER.md` |

## Adapter field map (locked)

Copied from [`DevB_DevC_Model_Plug_Requirements.md`](DevB_DevC_Model_Plug_Requirements.md) §3 — do not invent columns.

| Feature | MQTT `data` | Lead sample |
|---------|-------------|-------------|
| F02 MD | `apparent_power_kva_total` **or** `active_power_kw_total` + `reactive_power_kvar_total` | `kva` **or** `kw` + `var` |
| F04 idle | `present_value_pv_c`, `current_a_avg` | `zone_temp_c`, `current_a` |
| F05 leak | `pressure_bar`, `compressor_state` | `pressure_bar`, `loaded` (`LOADED` → 1) |
| F06 vib | `z_axis_rms_velocity_mm_sec` (or max Z/X), `temperature_c` | `rms_velocity_mms`, `surface_temp_c` |

Topic short type ↔ payload `sensor_type`: electrical→`electrical_meter`, vibration→`vibration_node`, thermal→`thermal_probe`, pressure→`pressure_transmitter`, gas→`gas_particle_sensor`, stroke→`digital_pulse_counter`, ambient→`ambient_weather`.

## Motor health compose (goal 5)

Owner Motor screen answers: is the compressor/motor **holding pressure under load**, **heating**, drawing **electrical current**, and trending **`maintenance_risk`**?

Inputs (no new universal model):

- Pressure: `run_pressure_capacity_series` / leak while loaded (OI-59)
- Heat: zone/surface temp from idle/thermal path
- Electrical: motor current from wire / correlated `motor_current_a`
- PdM: `predict_maintenance_risk` (OI-62 / notebook cells 19/20/22/25/28)

## Promotion

`promote_to_layer3` stays false until a human ADR. Gate helpers: Idle `IDLE_ML_PROMOTION.md`, Pressure `LEAK_ML_PROMOTION.md`.
