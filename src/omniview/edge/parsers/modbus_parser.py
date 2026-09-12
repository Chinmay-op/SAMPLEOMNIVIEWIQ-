import json
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "electrical_schema.json"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
INPUT_FILE = DATA_DIR / "raw_serial_dump.txt"
OUTPUT_FILE = DATA_DIR / "parsed_modbus_payloads.jsonl"

try:
    with open(SCHEMA_PATH, 'r') as f:
        ELECTRICAL_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    ELECTRICAL_SCHEMA = None


def validate_payload(payload):
    if ELECTRICAL_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=ELECTRICAL_SCHEMA)
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error for {payload.get('timestamp')}: {e.message}")
            return False
    return True 


def parse_modbus_string(raw_string):
    """
    Parses raw comma-separated string from Selec MFM384 simulator
    Expected format: ID, TS, V_LN, V_LL, I_AVG, KW, KVA, KVAR, PF, FREQ, KWH, KVAH, ROLL_KVA, MD_PROX
    """
    parts = raw_string.strip().split(',')
    
    if len(parts) != 14:
        return None

    try:
        payload = {
            "device_id": parts[0],
            "timestamp": parts[1],
            "sensor_type": "electrical",
            "data": {
                "voltage_v_ln_avg": float(parts[2]),
                "voltage_v_ll_avg": float(parts[3]),
                "current_a_avg": float(parts[4]),
                "active_power_kw_total": float(parts[5]),
                "apparent_power_kva_total": float(parts[6]),
                "reactive_power_kvar_total": float(parts[7]),
                "power_factor_avg": float(parts[8]),
                "frequency_hz": float(parts[9]),
                "active_energy_kwh": float(parts[10]),
                "apparent_energy_kvah": float(parts[11]),
                "rolling_kva_15min": float(parts[12]),
                "md_proximity_percent": float(parts[13])
            }
        }
        return payload
    except ValueError as e:
        print(f"Warning: Could not parse numerical values: {e}")
        return None


def run_parser():
    print(f"Starting Modbus Parser...")
    if not INPUT_FILE.exists():
        print(f"Error: Could not find {INPUT_FILE}. Run the simulator first.")
        return

    processed_count = 0
    valid_count = 0

    with open(INPUT_FILE, 'r', encoding='utf-8') as infile, \
         open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            if not line.strip():
                continue
            
            payload = parse_modbus_string(line)
            
            if payload:
                if validate_payload(payload):
                    outfile.write(json.dumps(payload) + "\n")
                    valid_count += 1
            
            processed_count += 1
            
            if processed_count % 10000 == 0:
                print(f"Processed {processed_count} lines...")

    print(f"Finished parsing. Total processed: {processed_count}. Total valid JSON payloads generated: {valid_count}.")

if __name__ == "__main__":
    run_parser()

