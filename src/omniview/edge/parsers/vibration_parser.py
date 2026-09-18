import json
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "vibration_schema.json"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
INPUT_FILE = DATA_DIR / "raw_vibration_dump.txt"
OUTPUT_FILE = DATA_DIR / "parsed_vibration_payloads.jsonl"

try:
    with open(SCHEMA_PATH, 'r') as f:
        VIB_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    VIB_SCHEMA = None


def validate_payload(payload):
    if VIB_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=VIB_SCHEMA)
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error for {payload.get('timestamp')}: {e.message}")
            return False
    return True 


def parse_vibration_string(raw_string):
    """
    Parses raw comma-separated string from Banner QM30VT1 vibration simulator
    Expected format: ID, TS, Z_RMS_VEL, X_RMS_VEL, Z_PEAK, X_PEAK, HF_RMS, TEMP, ISO_ZONE
    """
    parts = raw_string.strip().split(',')
    
    if len(parts) != 9:
        return None

    try:
        payload = {
            "device_id": parts[0],
            "timestamp": parts[1],
            "sensor_type": "vibration",
            "data": {
                "z_axis_rms_velocity_mm_sec": float(parts[2]),
                "x_axis_rms_velocity_mm_sec": float(parts[3]),
                "z_axis_peak_acceleration_g": float(parts[4]),
                "x_axis_peak_acceleration_g": float(parts[5]),
                "high_frequency_rms_acceleration_g": float(parts[6]),
                "temperature_c": float(parts[7]),
                "iso_health_zone": parts[8]
            }
        }
        return payload
    except ValueError as e:
        print(f"Warning: Could not parse numerical values: {e}")
        return None


def run_parser():
    print(f"Starting Vibration Parser...")
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
            
            payload = parse_vibration_string(line)
            
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

