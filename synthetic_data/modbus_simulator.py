import os
import datetime
import random
import math
from pathlib import Path

def generate_modbus_data():
    """Generates 30 days of raw Modbus serial data at 1-minute intervals, matching Selec MFM384."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "raw_serial_dump.txt"
    print(f"Generating Selec MFM384 Modbus simulation data to {output_file}...")

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=30)
    current_time = start_time

    device_id = "Selec-MFM384-01"
    
    # Base values
    active_energy_kwh = 150000.0
    apparent_energy_kvah = 158000.0

    with open(output_file, "w", encoding="utf-8") as f:
        # String format: ID, TS, V_LN, V_LL, I_AVG, KW, KVA, KVAR, PF, FREQ, KWH, KVAH, ROLL_KVA, MD_PROX
        
        while current_time <= end_time:
            hour = current_time.hour
            is_running = 7 <= hour < 19
            
            v_ln = random.uniform(235.0, 245.0)
            v_ll = v_ln * 1.732
            freq = random.uniform(49.8, 50.2)
            
            if is_running:
                i_avg = random.uniform(350.0, 420.0)
                pf = random.uniform(0.92, 0.98)
            else:
                i_avg = random.uniform(10.0, 25.0)
                pf = random.uniform(0.70, 0.85)
                
            kva = (v_ll * i_avg * 1.732) / 1000.0
            kw = kva * pf
            
            # KVAR = sqrt(KVA^2 - KW^2)
            kvar = math.sqrt(max(0, kva**2 - kw**2))
            
            rolling_kva = kva + random.uniform(-2, 2)
            md_prox = (rolling_kva / 500.0) * 100.0 # Assuming 500 kVA contracted MD
            
            # 1 min = 1/60th hour
            active_energy_kwh += kw / 60.0
            apparent_energy_kvah += kva / 60.0

            ts_str = current_time.isoformat() + "Z"
            row = [
                device_id,
                ts_str,
                f"{v_ln:.2f}",
                f"{v_ll:.2f}",
                f"{i_avg:.2f}",
                f"{kw:.2f}",
                f"{kva:.2f}",
                f"{kvar:.2f}",
                f"{pf:.3f}",
                f"{freq:.2f}",
                f"{active_energy_kwh:.2f}",
                f"{apparent_energy_kvah:.2f}",
                f"{rolling_kva:.2f}",
                f"{md_prox:.2f}"
            ]
            
            f.write(",".join(row) + "\n")
            current_time += datetime.timedelta(minutes=1)

    print(f"Successfully generated 30 days of electrical data at {output_file}")

if __name__ == "__main__":
    generate_modbus_data()
