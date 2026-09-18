"""
Anomaly Detection Proof-of-Concept — 4-Hour Simulation
=======================================================
Runs all 7 sensor bots in batch mode for 4 simulated hours,
feeds every payload through the Unified Anomaly Detector,
and produces a summary report with detection statistics.

This script completes in seconds (no real-time waiting).
"""

import sys
import json
import datetime
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.edge.bots.stochastic import sim_clock, wanderer
from omniview.edge.bots import (
    generate_electrical,
    generate_vibration,
    generate_thermal,
    generate_pressure,
    generate_gas,
    generate_stroke,
    generate_ambient,
)
from omniview.edge.anomaly_detector import AnomalyDetector

# ── Configuration ───────────────────────────────────────────────────────────

SIMULATION_HOURS = 4
SIMULATION_SECONDS = SIMULATION_HOURS * 3600
TICK_INTERVAL = 15  # Advance 15 seconds per tick (smallest poll interval)

# Bot poll intervals (from DevB_Bot_Specification.md)
BOT_INTERVALS = {
    "electrical": 15,
    "vibration": 60,
    "thermal": 60,
    "pressure": 60,
    "gas": 60,
    "stroke": 15,
    "ambient": 60,
}

BOT_GENERATORS = {
    "electrical": generate_electrical,
    "vibration": generate_vibration,
    "thermal": generate_thermal,
    "pressure": generate_pressure,
    "gas": generate_gas,
    "stroke": generate_stroke,
    "ambient": generate_ambient,
}

# ── Simulation ──────────────────────────────────────────────────────────────

def run_simulation():
    # Switch to batch mode so time advances instantly
    start_time = datetime.datetime(2026, 9, 17, 8, 0, 0).timestamp()  # Start at 8:00 AM
    sim_clock.set_batch_mode(start_time=start_time)

    detector = AnomalyDetector()

    # Tracking
    total_payloads = defaultdict(int)
    all_alerts = []
    alerts_by_sensor = defaultdict(list)
    alerts_by_type = defaultdict(int)
    tick_counters = defaultdict(int)

    elapsed = 0
    tick = 0

    print(f"Simulating {SIMULATION_HOURS} hours of sensor data...")
    print(f"Start time: {datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End time:   {datetime.datetime.fromtimestamp(start_time + SIMULATION_SECONDS).strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    while elapsed < SIMULATION_SECONDS:
        for sensor_name, generator in BOT_GENERATORS.items():
            interval = BOT_INTERVALS[sensor_name]

            # Only fire this bot if we're on its poll boundary
            if elapsed % interval == 0:
                try:
                    payload = generator()
                    total_payloads[sensor_name] += 1

                    # Feed into anomaly detector
                    alerts = detector.ingest(payload)

                    for alert in alerts:
                        alert["sim_elapsed_s"] = elapsed
                        alert["sim_time"] = datetime.datetime.fromtimestamp(
                            start_time + elapsed
                        ).strftime("%H:%M:%S")
                        all_alerts.append(alert)
                        alerts_by_sensor[sensor_name].append(alert)
                        alerts_by_type[alert["anomaly_type"]] += 1

                        # Print live detection
                        print(
                            f"  [{alert['sim_time']}] ALERT: {sensor_name:12s} | "
                            f"{alert['anomaly_type']:20s} | "
                            f"metric={alert['metric'].split(':')[1]:30s} | "
                            f"value={alert.get('value', 'N/A')}"
                        )

                except Exception as e:
                    pass  # Some bots may have edge-state dependencies

        sim_clock.advance(TICK_INTERVAL)
        elapsed += TICK_INTERVAL
        tick += 1

    sim_clock.set_live_mode()

    # ── Summary ─────────────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)

    print(f"\nDuration: {SIMULATION_HOURS} hours ({SIMULATION_SECONDS} seconds)")
    print(f"Total ticks: {tick}")

    print(f"\n--- Payloads Generated per Sensor ---")
    for sensor, count in sorted(total_payloads.items()):
        print(f"  {sensor:15s}: {count:6d} payloads")
    print(f"  {'TOTAL':15s}: {sum(total_payloads.values()):6d} payloads")

    print(f"\n--- Anomalies Detected ---")
    print(f"  Total alerts: {len(all_alerts)}")

    if all_alerts:
        print(f"\n  By type:")
        for atype, count in sorted(alerts_by_type.items(), key=lambda x: -x[1]):
            print(f"    {atype:25s}: {count}")

        print(f"\n  By sensor:")
        for sensor, sensor_alerts in sorted(alerts_by_sensor.items()):
            types = defaultdict(int)
            for a in sensor_alerts:
                types[a["anomaly_type"]] += 1
            type_str = ", ".join(f"{t}={c}" for t, c in sorted(types.items()))
            print(f"    {sensor:15s}: {len(sensor_alerts):4d} alerts ({type_str})")

        print(f"\n--- Timeline of First 20 Alerts ---")
        for i, alert in enumerate(all_alerts[:20]):
            print(
                f"  {i+1:3d}. [{alert['sim_time']}] {alert.get('sensor_type', '?'):12s} "
                f"| {alert['anomaly_type']:20s} "
                f"| {alert['metric'].split(':')[1]:30s} "
                f"| val={alert.get('value', 'N/A')}"
            )
        if len(all_alerts) > 20:
            print(f"  ... and {len(all_alerts) - 20} more alerts")

    return {
        "total_payloads": dict(total_payloads),
        "total_alerts": len(all_alerts),
        "alerts_by_type": dict(alerts_by_type),
        "alerts_by_sensor": {k: len(v) for k, v in alerts_by_sensor.items()},
        "all_alerts": all_alerts,
    }


if __name__ == "__main__":
    results = run_simulation()
