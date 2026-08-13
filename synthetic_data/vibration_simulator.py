import os
import datetime
import random
from pathlib import Path

def generate_vibration_data():
    """Generates 30 days of raw Vibration data at 1-minute intervals, with Banner QM30VT1 real parameters."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_vibration_dump.txt"
    print(f"Generating Banner QM30VT1 Vibration simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Banner-QM30VT1-01"
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, Z_RMS_VEL, X_RMS_VEL, Z_PEAK, X_PEAK, HF_RMS, TEMP, ISO_ZONE
        
        while current_time <= end_time:
            rand_state = random.random()
            
            # Anomaly injection for ML training
            if rand_state < 0.005:
                # 0.5% chance: Critical failure (ZONE_D)
                iso_zone = "ZONE_D"
                z_rms_vel = random.uniform(15.0, 25.0)
                temp = random.uniform(85.0, 110.0)
            elif rand_state < 0.05:
                # 4.5% chance: Warning / Early wear (ZONE_C)
                iso_zone = "ZONE_C"
                z_rms_vel = random.uniform(7.1, 14.5)
                temp = random.uniform(70.0, 85.0)
            elif rand_state < 0.30:
                # 25% chance: Acceptable long-term operation (ZONE_B)
                iso_zone = "ZONE_B"
                z_rms_vel = random.uniform(2.8, 7.0)
                temp = random.uniform(45.0, 65.0)
            else:
                # 70% chance: Newly commissioned / perfect health (ZONE_A)
                iso_zone = "ZONE_A"
                z_rms_vel = random.uniform(0.5, 2.7)
                temp = random.uniform(35.0, 45.0)

            # Derive other realistic parameters based on primary Z-axis RMS
            x_rms_vel = z_rms_vel * random.uniform(0.6, 0.9)  # Lateral usually slightly lower
            z_peak = (z_rms_vel / 9.81) * random.uniform(1.4, 2.5) # Approximate conversion to g with crest factor
            x_peak = (x_rms_vel / 9.81) * random.uniform(1.4, 2.5)
            
            # High frequency RMS shoots up drastically during bearing failure (Zone C/D)
            hf_rms = z_peak * random.uniform(0.5, 0.8) if iso_zone in ["ZONE_A", "ZONE_B"] else z_peak * random.uniform(1.5, 3.0)

            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                f"{z_rms_vel:.3f}",
                f"{x_rms_vel:.3f}",
                f"{z_peak:.3f}",
                f"{x_peak:.3f}",
                f"{hf_rms:.3f}",
                f"{temp:.2f}",
                iso_zone
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of vibration data at {output_file}")

if __name__ == "__main__":
    generate_vibration_data()
