# pressure_model.py: Design and Implementation Plan

## 1. The 10 Layers Mapped to Pneumatics

| Layer | Pressure adaptation |
| :--- | :--- |
| 1 | **Health gate**: Range 0–40 bar, plus a Hampel spike filter (median ± 3·MAD, window 5) before anything else. Stuck-sensor detection on (pressure, internal_temp). Consistency check: sw_out_1 must equal p < sp1, otherwise flag a fault. |
| 2 | **EWMA baseline**: Two trackers: pressure while LOADED, and pressure while UNLOADED. They have different normal levels, so a shared baseline would blur them. |
| 3 | **Derivatives**: Slope in bar/min and acceleration from a 5-sample window (60 s poll). Also the last pump-up recovery slope. |
| 4 | **Cross-family and root cause**: Cache the compressor current (electrical, 15 s) and strokes (stroke family, production rate) by site key. Correlate −dP/dt with production. |
| 5 | **Confidence**: Six components: decay depth, duty-cycle residual, z-score, acceleration, leak fraction, recovery deficit. |
| 6 | **Isolation Forest**: 12 features (below). |
| 7 | **Air wastage**: Duty-cycle residual to kWh to ₹. |
| 8 | **Health tracker**: Compressor and air-system HI with RUL. |
| 9 | **Cost estimator**: Energy waste, production loss, downtime risk, early-detection saving. |
| 10 | **Wrapper**: Delegates to the untouched PressureLeakDetector, enriches its events, and adds static-leak tiers when the base rule is silent. |

## 2. Leak vs. Normal Consumption
The physics is a receiver mass balance:
` (V/P_atm)·dP/dt = Q_comp·u(t) − Q_cons(t) − Q_leak(P)      u ∈ {0,1} loaded `
` Q_leak ≈ C_L·P        (orifice flow: continuous, proportional to pressure) `
` Q_cons                (episodic, coincides with strokes) `

A leak is continuous and independent of production. Consumption is bursty and tracks the stroke rate. Four discriminators follow from that:
1. **Static leak-down test**: Take samples where the compressor is UNLOADED or OFF and strokes == 0. Nothing else consumes air then, so dP/dt < −ε is a leak by construction. It's the cleanest test and needs no baseline.
2. **Duty-cycle residual**: Fit D_expected = α + β·ρ, where ρ is strokes/min, by OLS on a known-good window. Then D_leak = D_obs − D_expected(ρ). A leak shows up as an intercept shift that persists when production stops.
3. **Slope shape**: Consumption gives a large \|dP/dt\| for at most 2–3 samples, then recovery, and it correlates with ρ. A leak gives a small persistent negative slope with a step at onset and then a ≈ 0. Compute persistence as the fraction of window samples with Δp < 0.
4. **Correlation**: r = pearson(−dP/dt, ρ) over 15 samples, the same mechanism the gas model uses for temperature vs. current.

Decision logic:
```python
if state in ("UNLOADED", "OFF") and strokes == 0 and slope < -ε_static:
    return "FITTING_LEAK" # (static)
elif state == "LOADED" and slope < -θ and persistence > 0.8 and r < 0.3:
    return "GROSS_LEAK"
elif state == "LOADED" and slope < -θ and r > 0.6:
    return "EXCESSIVE_CONSUMPTION"
elif D_leak > 3*σ_resid and slope >= -θ:
    return "FITTING_LEAK" # (duty-cycle)
else:
    return "UNKNOWN"
```

## 3. Isolation Forest Features
Features: `[ pressure_bar, slope_5m, accel, ewma_z, duty_15m, transitions_per_hr, mean_loaded_dwell_s, recovery_slope, pressure_band_15m (max−min), compressor_current_a, strokes_per_min, internal_temp_c − ambient_temp_c ]`
- Train on NORMAL only, after spike rejection, so glitches don't contaminate the training set.
- Impute unavailable features with the median and add a missing-flag column.
- Set the alert threshold at the 99th percentile of training scores rather than relying on contamination=0.05.

## 4. ₹ Cost of Wasted Compressed Air
```text
P_loaded_kW = √3 · V_LL · I_comp · PF / 1000
E_waste_kWh = P_loaded_kW · D_leak · Δt_h
Cost_INR    = E_waste_kWh · ENERGY_RATE_INR_PER_KWH
```
For a sensing path that doesn't need duty cycle, use the leak-down method:
```text
Q_leak[m³/min FAD] = V_rec · (P1 − P2) / (P_atm · Δt_min)     (absolute bar)
E_waste = Q_leak · SPECIFIC_POWER_kW_per_m3min · Δt_h
```

## 5. Root Causes
| Root cause | Signature |
| :--- | :--- |
| **FITTING_LEAK** | Static decay when idle, or a duty-cycle offset. Mild slope, a≈0. |
| **GROSS_LEAK** | Decay while loaded, slope ≤ −0.5 bar/min, sudden step at onset. |
| **COMPRESSOR_SHORT_CYCLING** | Transitions/hr above a limit, short dwell, collapsed pressure band. |
| **EXCESSIVE_CONSUMPTION** | Decay correlates with ρ (r>0.6), and duty cycle scales with production. |
| **COMPRESSOR_CAPACITY_DEGRADATION** | Pump-up slope falls below its learned baseline. |
| **SENSOR_FAULT** | Spike, stuck reading, or switch-output inconsistency. |
| **UNKNOWN** | Ambiguous evidence. Don't force a label. |

## 6. Implementation Path
- **Phase 0, bot upgrade (prerequisite)**: Done. Modeled compressor hysteresis, episodic consumption, pressure-proportional leaks, and ground truth logging.
- **Phase 1**: Spike filter, health gate and duty tracker, with tests. 
- **Phase 2**: Baseline model, discriminator and confidence score. Tests for each root-cause branch using constructed scenarios.
- **Phase 3**: Isolation Forest, a training script, and the percentile threshold.
- **Phase 4**: Wastage, health and cost classes, the config constants, and the dashboard hook.
- **Phase 5**: Wrapper, registration in detectors_live.py, and per-root-cause action-card wording. Report precision and recall.
