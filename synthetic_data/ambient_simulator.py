import os
import datetime
import random
import math
from pathlib import Path

def generate_ambient_data():
    """Generates 30 days of raw Ambient data at 1-minute intervals, matching Schneider TH110."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_ambient_dump.txt"
    print(f"Generating Schneider TH110 Ambient simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Schneider-TH110-01"
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, TEMP_C, RH_PCT, OFFSET
        
        while current_time <= end_time:
            # 24-hour cycle logic
            hour = current_time.hour
            minute = current_time.minute
            time_in_hours = hour + (minute / 60.0)
            
            # Pune typical climate: Peak temp at 14:00, lowest at 05:00
            phase = (time_in_hours - 14.0) / 24.0 * 2 * math.pi
            
            # Base daily swing: 22C to 38C
            temp_c = 30.0 + (math.cos(phase) * 8.0) + random.uniform(-0.5, 0.5)
            
            # Humidity is usually inverse to temperature (40% to 80%)
            rh_pct = 60.0 - (math.cos(phase) * 20.0) + random.uniform(-2.0, 2.0)
            
            # Calculate a theoretical cooling load offset multiplier
            # Normalizes around 25C (1.0). Above 25C, chiller works harder.
            offset = max(0.5, 1.0 + ((temp_c - 25.0) * 0.05))
                
            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                f"{temp_c:.2f}",
                f"{rh_pct:.1f}",
                f"{offset:.2f}"
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of ambient data at {output_file}")

if __name__ == "__main__":
    generate_ambient_data()
