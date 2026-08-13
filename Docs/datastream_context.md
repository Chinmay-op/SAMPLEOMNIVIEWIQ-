# OmniView Datastream Context & Playbook

**Target Audience:** Downstream Developers (Platform & ML/Rule Engine)
**Context:** This document explains the behavioral characteristics of the 7 edge data streams you will be ingesting. It details the underlying timeline, shift schedules, and the ground-truth anomalies that have been mathematically injected into the 30-day baseline data.

---

## 1. Datastream Architecture & Volume

The 30-day historical datastream provided to you consists of exactly **43,200 JSON payloads per sensor** (1 payload per minute × 60 mins × 24 hours × 30 days). 

### Ingestion Strategy
When testing your TimescaleDB ingestion or your Rule Engine, you should "replay" these `.jsonl` files sequentially by `timestamp`. The data is highly correlated across sensors (e.g., if the Electrical sensor shows `0 kW`, the Vibration sensor will simultaneously show near-zero velocity). 

---

## 2. The Master Timeline & Machine States

All 7 sensor data streams are synchronized against a single hidden "Master Timeline." This timeline mathematically models a real factory operating schedule:

* **Shifts:** Morning Shift (07:00–13:00), Afternoon Shift (13:00–19:00), Off-Hours (19:00–23:00).
* **Weekends:** Saturday has a partial schedule. Sunday is a complete `POWER_OFF` holiday.
* **Standard States:**
  * `NORMAL`: Machine is loaded and running standard production cycles.
  * `IDLE`: Machine is powered on but not cycling (e.g., Changeover or Cooldown).
  * `POWER_OFF`: Machine is physically disconnected / powered down.

When building your dashboards, you should see clear daily cyclical patterns that map exactly to these shift hours.

---

## 3. Ground Truth Anomalies (For Rule Engine / ML)

To test your downstream Rule Engine (OI-56) and future ML models, we have intentionally injected realistic anomalies into the 30-day data streams. 

### A. Critical "Spike" Scenarios
These are short-duration (10–45 minute) events that occur randomly during `NORMAL` production windows. Your Rule Engine should be able to catch these in near real-time:

| Anomaly Type | What to look for in the Datastream |
| :--- | :--- |
| **`LAZY_IDLE`** | `electrical_meter` kW drops to near zero, but `thermal_probe` PV temperature remains dangerously high for >15 minutes. |
| **`MD_BREACH_RISK`** | `electrical_meter` rolling 15-minute kVA average suddenly spikes aggressively toward the Sanctioned Maximum Demand limit. |
| **`PNEUMATIC_LEAK`** | `pressure_transmitter` shows a sharp increase in `decay_rate_bar_min` while the compressor is running. |
| **`VIBRATION_ZONE_D`** | `vibration_node` ISO health zone switches to `ZONE_D` and `high_frequency_rms_acceleration_g` spikes, simulating a sudden mechanical clash. |

### B. Gradual Degradation Windows
These are slow-moving trends that span multiple days. These are designed to test future predictive ML models (like XGBoost or LSTMs), rather than simple static rules:

1. **Gradual Bearing Wear (`GRADUAL_VIB_DEGRADATION`)**: The baseline vibration RMS velocity slowly creeps upward over a 5-day window.
2. **Harmonic Growth (`GRADUAL_THD_GROWTH`)**: The Electrical Meter's `thd_voltage_pct` steadily worsens, simulating degrading power quality on the grid.
3. **Power Factor Drift (`GRADUAL_PF_DRIFT`)**: The Electrical Meter's `power_factor_avg` slowly drops below 0.90, which would eventually trigger a utility penalty.

---

## 4. Expected Output Validation
If your data ingestion (MQTT -> TimescaleDB) and your Rule Engine are built correctly, you should be able to query your database for the anomalies listed in Section 3 and find the exact timestamps where they occurred in the synthetic baseline. 

If you do not see them, check that you are querying the new **Real-World Hardware Parameters** (detailed in the Developer Handoff) rather than generic legacy keys.
