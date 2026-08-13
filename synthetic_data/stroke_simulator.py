import os
import datetime
import random
from pathlib import Path

def generate_stroke_data():
    """Generates 30 days of raw Stroke Counter data at 1-minute intervals, matching Sick IME IO-Link."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_stroke_dump.txt"
    print(f"Generating Sick IME IO-Link Stroke Counter simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Sick-IME-01"
    
    # State tracking
    counter_value = 1500000 # lifetime
    operating_hours = 8000
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, BDC1, COUNTER, DEV_TEMP, OP_HOURS, SIG_QUAL, STROKES_INT, CYCLE_TIME
        
        while current_time <= end_time:
            # Simulate a 1-minute interval of strokes
            hour = current_time.hour
            is_running = 7 <= hour < 19 # Shift 1 & 2
            
            strokes_in_int = 0
            cycle_time = 0.0
            bdc1 = "0"
            
            if is_running:
                # Typically ~22 seconds per cycle -> ~2.7 cycles per minute
                strokes_in_int = random.choice([2, 3])
                cycle_time = random.uniform(20.5, 24.5)
                counter_value += strokes_in_int
                # Chance that at the exact moment of polling, it's detecting metal
                bdc1 = "1" if random.random() < 0.2 else "0"
            else:
                strokes_in_int = 0
                cycle_time = 0.0
                bdc1 = "0"
            
            dev_temp = random.uniform(28.0, 35.0) if is_running else random.uniform(22.0, 25.0)
            
            # Operating hours increments by 1/60th
            operating_hours_update = operating_hours + ((current_time - start_time).total_seconds() / 3600.0)
            
            # Signal quality degrades slightly over time due to dust/oil
            days_elapsed = (current_time - start_time).days
            sig_qual = 255 - int(days_elapsed * 1.5) - random.randint(0, 10)
            sig_qual = max(0, min(255, sig_qual))

            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                bdc1,
                str(counter_value),
                f"{dev_temp:.1f}",
                str(int(operating_hours_update)),
                str(sig_qual),
                str(strokes_in_int),
                f"{cycle_time:.2f}"
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of stroke counter data at {output_file}")

if __name__ == "__main__":
    generate_stroke_data()
