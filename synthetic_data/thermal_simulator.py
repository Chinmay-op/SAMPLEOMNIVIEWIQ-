import os
import datetime
import random
from pathlib import Path

def generate_thermal_data():
    """Generates 30 days of raw Thermal data at 1-minute intervals, matching Omron E5CC Modbus PID."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_thermal_dump.txt"
    print(f"Generating Omron E5CC Thermal simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Omron-E5CC-01"
    
    # State tracking
    set_point_sp = 255.0
    present_value_pv = 30.0 # Starts at ambient
    state = "COOLING"
    
    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, PV, SP, MV, HB_ALARM, INPUT_ERROR, TREND, STATE
        
        while current_time <= end_time:
            hour = current_time.hour
            is_running = 7 <= hour < 19
            
            # Simulated PID loop
            if is_running:
                if present_value_pv < set_point_sp - 2.0:
                    state = "HEATING"
                    mv = 100.0
                    present_value_pv += random.uniform(2.0, 5.0)
                elif present_value_pv > set_point_sp + 2.0:
                    state = "COOLING"
                    mv = 0.0
                    present_value_pv -= random.uniform(1.0, 3.0)
                else:
                    state = "AT_SETPOINT"
                    mv = random.uniform(20.0, 60.0) # Maintaining temp
                    present_value_pv += random.uniform(-0.5, 0.5)
            else:
                state = "COOLING"
                mv = 0.0
                if present_value_pv > 30.0:
                    present_value_pv -= random.uniform(1.0, 3.0)
                else:
                    present_value_pv = random.uniform(28.0, 32.0)
                    
            # Inject lazy idle (machine is off but heater left on)
            # We'll just randomly do this for 1 hour occasionally
            is_lazy_idle = random.random() < 0.001
            if is_lazy_idle and not is_running:
                state = "IDLE_HOT"
                mv = random.uniform(20.0, 60.0)
                present_value_pv = set_point_sp + random.uniform(-1.0, 1.0)
                
            # Alarms
            hb_alarm = "1" if (mv == 100.0 and random.random() < 0.005) else "0"
            input_error = "1" if random.random() < 0.0001 else "0" # very rare short/disconnect
            
            if input_error == "1":
                present_value_pv = 0.0 # Error state
                
            # Trend calculation
            trend = "STABLE"
            if state == "HEATING":
                trend = "RISING"
            elif state == "COOLING" and present_value_pv > 35.0:
                trend = "FALLING"

            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                f"{present_value_pv:.1f}",
                f"{set_point_sp:.1f}",
                f"{mv:.1f}",
                hb_alarm,
                input_error,
                trend,
                state
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of thermal data at {output_file}")

if __name__ == "__main__":
    generate_thermal_data()
