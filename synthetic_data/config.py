# ============================================================
# OmniView IQ POC — Layer 0 Config
# All operating bands, thresholds, and simulation parameters.
# No values are hardcoded in any generator. All values live here.
# ============================================================

LAYER_0 = {

    # --------------------------------------------------------
    # SITE IDENTITY
    # --------------------------------------------------------
    "site_id": "pune_isbm_poc_001",
    "device_id": "gateway-001",

    # --------------------------------------------------------
    # SIMULATION DURATION
    # --------------------------------------------------------
    "simulation_days": 365,
    "simulation_start": "2025-01-01T06:00:00",  # Factory cold start on Day 1

    # --------------------------------------------------------
    # ELECTRICAL — Selec MFM384
    # --------------------------------------------------------
    "electrical": {
        "poll_interval_sec": 15,
        "contracted_demand_kva": 500,           # Sanctioned MD — confirm on-site
        "md_alert_threshold_pct": 90,           # Alert fires at 90% of contracted demand
        "md_critical_threshold_pct": 100,       # Breach confirmed
        "md_window_minutes": 15,               # MSEDCL integration window

        # Normal production band
        "normal_voltage_v": 415,                # Stable baseline
        "normal_kva_min": 280,
        "normal_kva_max": 420,
        "normal_kw_min": 250,
        "normal_kw_max": 380,
        "normal_pf_min": 0.92,
        "normal_pf_max": 0.97,
        "normal_thd_min": 2.5,
        "normal_thd_max": 5.0,
        "normal_current_min": 350,              # Amps
        "normal_current_max": 600,

        # Idle band (machine powered, not producing)
        "idle_kva_max": 80,
        "idle_current_max": 120,               # Below this → machine is idle/off

        # Power off
        "power_off_kva_max": 5,               # Residual / standby draw

        # Noise (Datasheet Alignment: Selec MFM384 Class 0.5S = 0.5% accuracy)
        "noise_voltage_abs": 2.0,               # ±2V fluctuation
        "noise_kva_pct": 0.005,                 # ±0.5%
        "noise_pf_abs": 0.005,
        "noise_current_pct": 0.005,             # ±0.5%
        "noise_thd_abs": 0.05,
        "outlier_rate": 0.0005,
    },

    # --------------------------------------------------------
    # VIBRATION — Banner Q45 / NCD MEMS (compressor bearing)
    # --------------------------------------------------------
    "vibration": {
        "poll_interval_sec": 60,
        "iso_class": "II",                     # Confirm on-site (Class I/II/III)

        # ISO 10816-3 Class II zone boundaries (mm/s RMS)
        # Fetched at runtime — adjust for Class I or III if confirmed otherwise
        "zone_a_max": 2.8,
        "zone_b_max": 7.1,
        "zone_c_max": 18.0,
        # Zone D = above zone_c_max

        # Normal bearing surface temp range
        "normal_bearing_temp_min": 38.0,       # °C
        "normal_bearing_temp_max": 58.0,

        # Max credible change per 60s reading (transition physics)
        "max_temp_change_per_reading": 5.0,    # °C
        "max_velocity_change_per_reading": 2.0, # mm/s

        # Noise (Datasheet Alignment: NCD MEMS typical resolution/accuracy)
        "noise_velocity_abs": 0.1,            # ±0.1 mm/s typical MEMS noise floor
        "noise_temp_abs": 0.5,                # ±0.5 °C typical integrated sensor accuracy
        "outlier_rate": 0.001,
    },

    # --------------------------------------------------------
    # THERMAL — Surface thermal probe (ISBM barrel)
    # --------------------------------------------------------
    "thermal": {
        "poll_interval_sec": 60,
        "barrel_setpoint_c": 255.0,            # Confirm on-site
        "normal_band_tolerance_c": 8.0,        # ±8°C from setpoint is normal

        # Lazy-idle trigger: barrel temp above this while machine is idle
        "lazy_idle_temp_threshold_c": 240.0,
        "lazy_idle_duration_minutes": 15,      # Must sustain this long to trigger alert

        # Cold start / heat-up rate
        "heat_up_rate_c_per_min": 4.5,        # Approx rate from ambient to setpoint
        "cool_down_rate_c_per_min": 2.0,       # Base rate — modified by ambient temp

        # Over-temperature limit
        "over_temp_limit_c": 275.0,

        # Max credible change per 60s reading (transition physics)
        "max_temp_change_per_reading": 15.0,   # °C

        # Noise (Datasheet Alignment: Industrial PT100 Class B or Type J/K at 250°C)
        "noise_temp_abs": 1.5,               # ±1.5 °C accuracy at high temps
        "outlier_rate": 0.0005,
    },

    # --------------------------------------------------------
    # PNEUMATIC PRESSURE — WIKA A-10 (compressor manifold)
    # --------------------------------------------------------
    "pressure": {
        "poll_interval_sec": 60,
        "setpoint_bar": 32.0,                  # Confirm on-site
        "normal_band_min_bar": 28.0,
        "normal_band_max_bar": 36.0,

        # Leak detection
        "leak_decay_threshold_bar_per_min": -0.4,  # More negative = suspected leak

        # Recovery time after compressor reloads
        "max_recovery_time_minutes": 3,

        # Max credible change per 60s reading (transition physics)
        "max_pressure_change_per_reading": 3.0,   # bar

        # Noise (Datasheet Alignment: WIKA A-10 is ≤ ±0.5% of span. 0.5% of 40 bar = 0.2 bar)
        "noise_pressure_abs": 0.2,            # ±0.2 bar accuracy
        "outlier_rate": 0.0005,
    },

    # --------------------------------------------------------
    # AMBIENT / WEATHER — Shop floor
    # --------------------------------------------------------
    "ambient": {
        "poll_interval_sec": 120,
        "cycle_days": 16,                      # 15–17 day sinusoidal cycle

        # Annual ambient temperature range for Pune (°C)
        "annual_temp_mean": 28.0,
        "annual_temp_amplitude": 7.0,          # Summer peak ~35°C, winter ~21°C
        "daily_temp_variation": 5.0,           # Day/night swing

        # Humidity range
        "humidity_mean_pct": 60.0,
        "humidity_amplitude_pct": 25.0,        # Monsoon ~85%, dry ~35%

        # Noise
        "noise_temp_abs": 0.3,
        "noise_humidity_abs": 1.5,
    },

    # --------------------------------------------------------
    # AMBIENT EFFECT COEFFICIENTS (linkage to sensor readings)
    # --------------------------------------------------------
    "ambient_effect": {
        # Barrel baseline shift: for every 1°C above 30°C ambient, barrel rises by this
        "barrel_temp_per_ambient_c": 0.3,
        # Bearing baseline shift
        "bearing_temp_per_ambient_c": 0.15,
        # Cooldown rate modifier: at <20°C ambient, cooldown is 25% faster
        "cold_ambient_cooldown_boost": 0.25,
        # Warm ambient cooldown penalty
        "warm_ambient_cooldown_penalty": 0.20,
        # THD offset from high humidity
        "thd_humidity_offset_above_75pct": 0.2,  # % THD added when humidity > 75%
    },

    # --------------------------------------------------------
    # SHIFT SCHEDULE
    # --------------------------------------------------------
    "schedule": {
        "weekday": {
            "power_off_end": "06:00",          # Cold start begins
            "cold_start_duration_min": 60,     # Minutes to reach setpoint
            "shift_1_start": "07:00",
            "shift_1_end": "13:00",
            "changeover_duration_min": 30,
            "shift_2_start": "13:30",
            "shift_2_end": "19:00",
            "cooldown_duration_min": 30,
            "power_off_start": "19:30",
        },
        "saturday": {
            "power_off_end": "07:00",
            "cold_start_duration_min": 60,
            "shift_1_start": "08:00",
            "shift_1_end": "14:00",
            "cooldown_duration_min": 30,
            "power_off_start": "14:30",
        },
        "sunday_holiday": {
            "state": "POWER_OFF",              # Full day off
        },
    },

    # --------------------------------------------------------
    # DEGRADATION INJECTION SCHEDULE (injected N times per year)
    # --------------------------------------------------------
    "degradation": {
        "bearing_wear_events_per_year": 3,
        "bearing_wear_duration_days": 14,      # Slow drift over 14 days before spike

        "thd_growth_events_per_year": 2,
        "thd_growth_duration_days": 60,        # Slow rise over 60 days

        "pressure_narrowing_events_per_year": 3,
        "pressure_narrowing_duration_days": 10,

        "pf_drift_events_per_year": 2,
        "pf_drift_duration_days": 21,
    },

    # --------------------------------------------------------
    # CRITICAL SCENARIO INJECTION
    # --------------------------------------------------------
    "scenarios": {
        "lazy_idle_events_per_year": 18,       # ~1.5 per month
        "md_breach_events_per_year": 12,       # ~1 per month
        "pneumatic_leak_events_per_year": 10,
        "vibration_zone_d_events_per_year": 6,
        "conflict_scenario_events_per_year": 3, # Vibration Zone D + MD breach simultaneously
    },
    
    # --------------------------------------------------------
    # Stroke / Production Counter Config
    # --------------------------------------------------------
    "stroke": {
        "nominal_cycle_time_s": 22.0,      # Expected seconds per stroke
        "cycle_time_variance_s": 1.5,      # Normal random variance
        "slow_cycle_threshold_s": 25.0     # Above this is an inefficient cycle
    }
}
