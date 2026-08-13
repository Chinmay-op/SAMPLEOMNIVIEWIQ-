# ============================================================
# OmniView IQ POC — Master Timeline Generator
# Builds the shared backbone that all sensor generators read.
# Outputs a DataFrame with one row per minute for 365 days,
# each row labelled with machine_state, active_event, shift_period,
# and day_type. Sensor generators sample this at their own intervals.
# ============================================================

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
from config import LAYER_0

# ── Seed for reproducibility ──────────────────────────────
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ── State constants ───────────────────────────────────────
STATES = {
    "NORMAL": "NORMAL",
    "IDLE": "IDLE",
    "CRITICAL": "CRITICAL",
    "POWER_OFF": "POWER_OFF",
}

EVENT_TYPES = {
    "NONE": None,
    "COLD_START": "COLD_START",
    "COOLDOWN": "COOLDOWN",
    "LAZY_IDLE": "LAZY_IDLE",
    "MD_BREACH_RISK": "MD_BREACH_RISK",
    "PNEUMATIC_LEAK": "PNEUMATIC_LEAK",
    "VIBRATION_ZONE_D": "VIBRATION_ZONE_D",
    "CONFLICT_SCENARIO": "CONFLICT_SCENARIO",
    "GRADUAL_VIB_DEGRADATION": "GRADUAL_VIB_DEGRADATION",
    "GRADUAL_THD_GROWTH": "GRADUAL_THD_GROWTH",
    "GRADUAL_PRESSURE_NARROWING": "GRADUAL_PRESSURE_NARROWING",
    "GRADUAL_PF_DRIFT": "GRADUAL_PF_DRIFT",
    "SENSOR_GLITCH": "SENSOR_GLITCH",
}

# ── Valid state transitions ───────────────────────────────
VALID_TRANSITIONS = {
    "POWER_OFF": ["IDLE"],
    "IDLE": ["NORMAL", "POWER_OFF"],
    "NORMAL": ["IDLE", "CRITICAL"],
    "CRITICAL": ["NORMAL", "POWER_OFF"],
}


def _day_type(dt: datetime) -> str:
    """Returns WEEKDAY, SATURDAY, or SUNDAY_HOLIDAY."""
    if dt.weekday() == 6:
        return "SUNDAY_HOLIDAY"
    elif dt.weekday() == 5:
        return "SATURDAY"
    return "WEEKDAY"


def _shift_period(dt: datetime) -> str:
    """Returns the shift period label for a given datetime."""
    hour = dt.hour
    if 7 <= hour < 13:
        return "MORNING_SHIFT"
    elif 13 <= hour < 19:
        return "AFTERNOON_SHIFT"
    elif 19 <= hour < 23:
        return "OFF_HOURS"
    return "NIGHT_OFF"


def _build_daily_state_blocks(date: datetime, day_type: str) -> list:
    """
    Returns a list of (start_minute_of_day, end_minute_of_day, state, event) tuples
    for a single calendar day, based on the shift schedule in config.
    Minutes are 0-indexed from midnight.
    """
    sched = LAYER_0["schedule"]
    blocks = []

    if day_type == "SUNDAY_HOLIDAY":
        blocks.append((0, 1440, "POWER_OFF", None))
        return blocks

    if day_type == "SATURDAY":
        s = sched["saturday"]
        po_end = _time_to_min(s["power_off_end"])
        cold_end = po_end + s["cold_start_duration_min"]
        shift1_start = _time_to_min(s["shift_1_start"])
        shift1_end = _time_to_min(s["shift_1_end"])
        cooldown_end = shift1_end + s["cooldown_duration_min"]
        po_start = _time_to_min(s["power_off_start"])

        blocks = [
            (0, po_end, "POWER_OFF", None),
            (po_end, cold_end, "IDLE", "COLD_START"),
            (cold_end, shift1_start, "IDLE", None),
            (shift1_start, shift1_end, "NORMAL", None),
            (shift1_end, cooldown_end, "IDLE", "COOLDOWN"),
            (cooldown_end, 1440, "POWER_OFF", None),
        ]
        return blocks

    # Weekday
    s = sched["weekday"]
    po_end = _time_to_min(s["power_off_end"])
    cold_end = po_end + s["cold_start_duration_min"]
    s1_start = _time_to_min(s["shift_1_start"])
    s1_end = _time_to_min(s["shift_1_end"])
    changeover_end = s1_end + s["changeover_duration_min"]
    s2_start = _time_to_min(s["shift_2_start"])
    s2_end = _time_to_min(s["shift_2_end"])
    cooldown_end = s2_end + s["cooldown_duration_min"]
    po_start = _time_to_min(s["power_off_start"])

    blocks = [
        (0, po_end, "POWER_OFF", None),
        (po_end, cold_end, "IDLE", "COLD_START"),
        (cold_end, s1_start, "IDLE", None),
        (s1_start, s1_end, "NORMAL", None),
        (s1_end, changeover_end, "IDLE", "COOLDOWN"),
        (changeover_end, s2_start, "IDLE", None),
        (s2_start, s2_end, "NORMAL", None),
        (s2_end, cooldown_end, "IDLE", "COOLDOWN"),
        (cooldown_end, 1440, "POWER_OFF", None),
    ]
    return blocks


def _time_to_min(time_str: str) -> int:
    """Converts 'HH:MM' string to minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _inject_gradual_degradation(timeline_df: pd.DataFrame) -> pd.DataFrame:
    """
    Marks multi-day slow degradation windows in the timeline.
    Only injected during NORMAL windows. Does not change machine_state.
    """
    cfg = LAYER_0["degradation"]
    total_minutes = len(timeline_df)
    
    if "degradation_pct" not in timeline_df.columns:
        timeline_df["degradation_pct"] = 0.0

    degradation_types = [
        ("GRADUAL_VIB_DEGRADATION", cfg["bearing_wear_events_per_year"],
         cfg["bearing_wear_duration_days"] * 1440),
        ("GRADUAL_THD_GROWTH", cfg["thd_growth_events_per_year"],
         cfg["thd_growth_duration_days"] * 1440),
        ("GRADUAL_PRESSURE_NARROWING", cfg["pressure_narrowing_events_per_year"],
         cfg["pressure_narrowing_duration_days"] * 1440),
        ("GRADUAL_PF_DRIFT", cfg["pf_drift_events_per_year"],
         cfg["pf_drift_duration_days"] * 1440),
    ]

    for event_label, count, duration_min in degradation_types:
        normal_indices = timeline_df[timeline_df["machine_state"] == "NORMAL"].index.tolist()
        if len(normal_indices) < duration_min:
            continue

        for _ in range(count):
            if len(normal_indices) < duration_min:
                break
            start_idx = random.choice(normal_indices[:-duration_min])
            end_idx = min(start_idx + duration_min, total_minutes - 1)

            # Only mark rows that are currently NORMAL with no existing event
            mask = (
                (timeline_df.index >= start_idx) &
                (timeline_df.index <= end_idx) &
                (timeline_df["machine_state"] == "NORMAL") &
                (timeline_df["active_event"].isna())
            )
            timeline_df.loc[mask, "active_event"] = event_label
            
            if event_label == "GRADUAL_VIB_DEGRADATION":
                # Calculate percentage (0.0 to 1.0) based on time elapsed since start_idx
                elapsed = timeline_df.index[mask] - start_idx
                timeline_df.loc[mask, "degradation_pct"] = np.clip(elapsed / duration_min, 0.0, 1.0)

    return timeline_df


def _inject_critical_scenarios(timeline_df: pd.DataFrame) -> pd.DataFrame:
    """
    Injects short CRITICAL events into NORMAL windows.
    Records each injection in the event log list.
    """
    cfg = LAYER_0["scenarios"]
    event_log = []

    scenario_types = [
        ("LAZY_IDLE", cfg["lazy_idle_events_per_year"], 20, 45),
        ("MD_BREACH_RISK", cfg["md_breach_events_per_year"], 10, 25),
        ("PNEUMATIC_LEAK", cfg["pneumatic_leak_events_per_year"], 15, 35),
        ("VIBRATION_ZONE_D", cfg["vibration_zone_d_events_per_year"], 8, 20),
        ("CONFLICT_SCENARIO", cfg["conflict_scenario_events_per_year"], 15, 30),
    ]

    normal_indices = timeline_df[timeline_df["machine_state"] == "NORMAL"].index.tolist()

    for event_label, count, min_duration, max_duration in scenario_types:
        for _ in range(count):
            if not normal_indices:
                break
            start_idx = random.choice(normal_indices)
            duration = random.randint(min_duration, max_duration)
            end_idx = min(start_idx + duration, len(timeline_df) - 1)

            mask = (
                (timeline_df.index >= start_idx) &
                (timeline_df.index <= end_idx) &
                (timeline_df["machine_state"] == "NORMAL")
            )
            timeline_df.loc[mask, "machine_state"] = "CRITICAL"
            timeline_df.loc[mask, "active_event"] = event_label

            start_ts = timeline_df.loc[start_idx, "timestamp"]
            end_ts = timeline_df.loc[end_idx, "timestamp"]
            event_log.append({
                "event_type": event_label,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "duration_minutes": duration,
            })

            # Remove injected indices from normal pool to avoid overlap
            normal_indices = [i for i in normal_indices if i < start_idx or i > end_idx]

    return timeline_df, event_log


def generate_master_timeline() -> tuple:
    """
    Builds the 1-minute-resolution master timeline for the full simulation period.
    Returns: (timeline_df, event_log_df)
    """
    start_dt = datetime.fromisoformat(LAYER_0["simulation_start"])
    total_days = LAYER_0["simulation_days"]
    total_minutes = total_days * 1440

    print(f"Generating {total_days}-day master timeline ({total_minutes:,} rows)...")

    timestamps = [start_dt + timedelta(minutes=i) for i in range(total_minutes)]
    records = []

    for i, ts in enumerate(timestamps):
        day_type = _day_type(ts)
        blocks = _build_daily_state_blocks(ts, day_type)
        minute_of_day = ts.hour * 60 + ts.minute

        state = "POWER_OFF"
        event = None
        for (block_start, block_end, block_state, block_event) in blocks:
            if block_start <= minute_of_day < block_end:
                state = block_state
                event = block_event
                break

        records.append({
            "timestamp": ts,
            "machine_state": state,
            "active_event": event,
            "day_type": day_type,
            "shift_period": _shift_period(ts),
        })

    timeline_df = pd.DataFrame(records)

    print("Injecting gradual degradation windows...")
    timeline_df = _inject_gradual_degradation(timeline_df)

    print("Injecting critical scenario events...")
    timeline_df, event_log = _inject_critical_scenarios(timeline_df)

    event_log_df = pd.DataFrame(event_log)

    # Summary
    state_counts = timeline_df["machine_state"].value_counts(normalize=True) * 100
    print("\nState distribution:")
    for state, pct in state_counts.items():
        print(f"  {state}: {pct:.1f}%")

    print(f"\nEvent log: {len(event_log_df)} events injected.")
    print("Master timeline generation complete.")

    return timeline_df, event_log_df


if __name__ == "__main__":
    import os
    os.makedirs("output", exist_ok=True)
    
    timeline_df, event_log_df = generate_master_timeline()
    
    timeline_df.to_parquet("output/master_timeline.parquet")
    event_log_df.to_csv("output/event_log.csv", index=False)
    
    print("Exported master_timeline.parquet and event_log.csv successfully.")
