import os
import datetime
import random
from pathlib import Path

def generate_gas_data():
    """Generates 30 days of raw Gas/Particle data at 1-minute intervals, matching Schneider HeatTag."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_gas_dump.txt"
    print(f"Generating Schneider HeatTag simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Schneider-HeatTag-01"
    
    # State tracking
    panel_temp = 35.0
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, GAS_PPM, PARTICLE_IDX, TEMP_C, TEMP_RISE, SEVERITY
        
        while current_time <= end_time:
            hour = current_time.hour
            is_running = 7 <= hour < 19
            
            # Baseline behavior
            if is_running:
                panel_temp += random.uniform(-0.5, 0.6)
            else:
                panel_temp -= random.uniform(0.1, 0.8)
                
            panel_temp = max(25.0, min(50.0, panel_temp))
            
            gas_ppm = random.uniform(0.0, 1.5)
            particle_idx = random.uniform(0.0, 5.0)
            temp_rise = 0.0
            severity = "NORMAL"
            
            # Inject anomaly: Wire insulation overheating (1% chance during operation)
            if is_running and random.random() < 0.01:
                # Early stage overheating (smoldering/outgassing)
                gas_ppm = random.uniform(15.0, 45.0)
                particle_idx = random.uniform(20.0, 60.0)
                temp_rise = random.uniform(0.5, 2.5)
                panel_temp += temp_rise
                
                severity = "WARNING"
                if gas_ppm > 30.0 or particle_idx > 50.0:
                    severity = "ALARM"
                    
            # Inject critical failure (0.1% chance)
            elif is_running and random.random() < 0.001:
                gas_ppm = random.uniform(80.0, 150.0)
                particle_idx = random.uniform(100.0, 300.0)
                temp_rise = random.uniform(3.0, 8.0)
                panel_temp += temp_rise
                severity = "CRITICAL"
                
            else:
                temp_rise = random.uniform(-0.1, 0.1)
                
            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                f"{gas_ppm:.2f}",
                f"{particle_idx:.2f}",
                f"{panel_temp:.1f}",
                f"{temp_rise:.2f}",
                severity
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of gas/particle data at {output_file}")

if __name__ == "__main__":
    generate_gas_data()
