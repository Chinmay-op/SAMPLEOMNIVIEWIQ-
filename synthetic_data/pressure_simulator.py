import os
import datetime
import random
from pathlib import Path

def generate_pressure_data():
    """Generates 30 days of raw Pneumatic Pressure data at 1-minute intervals, matching Festo SPAU IO-Link."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_pressure_dump.txt"
    print(f"Generating Festo SPAU Pressure simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Festo-SPAU-01"
    
    # State tracking
    pressure_bar = 32.0
    compressor_state = "LOADED"
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, PDV_RAW, PRESSURE, OUT_1, OUT_2, STATUS, INT_TEMP, COMP_STATE, TREND
        
        while current_time <= end_time:
            # Simulate compressor loading cycle
            if compressor_state == "LOADED":
                pressure_bar += random.uniform(0.5, 1.5)
                if pressure_bar >= 36.0:
                    compressor_state = "UNLOADED"
                    pressure_bar = 36.0
            elif compressor_state == "UNLOADED":
                # Simulated usage / leak decay
                decay = random.uniform(0.2, 0.8)
                
                # Introduce leak anomaly 10% of the time (faster decay)
                if random.random() < 0.10:
                    decay += random.uniform(0.5, 1.2)
                    
                pressure_bar -= decay
                
                if pressure_bar <= 28.0:
                    compressor_state = "LOADED"
            
            # Trend calculation
            trend = "STABLE"
            if compressor_state == "LOADED":
                trend = "RISING"
            elif compressor_state == "UNLOADED":
                trend = "FALLING"
                
            # Hardware specific values
            pdv_raw = int(pressure_bar * 409.6) # 14-bit scale representation (approx)
            pdv_raw = max(0, min(16383, pdv_raw)) # clamp to 14 bit
            
            # Switch outputs
            out_1 = "1" if pressure_bar < 29.0 else "0" # SP1 = low pressure warning
            out_2 = "1" if pressure_bar > 35.0 else "0" # SP2 = high pressure cutoff
            
            status_code = 0 # OK
            if pressure_bar < 26.0 or pressure_bar > 38.0:
                status_code = 2 # Out of spec
                
            int_temp = random.uniform(30.0, 42.0)
            if compressor_state == "LOADED":
                int_temp += random.uniform(1.0, 2.5) # Heats up when air is flowing rapidly

            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                str(pdv_raw),
                f"{pressure_bar:.2f}",
                out_1,
                out_2,
                str(status_code),
                f"{int_temp:.1f}",
                compressor_state,
                trend
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of pressure data at {output_file}")

if __name__ == "__main__":
    generate_pressure_data()
