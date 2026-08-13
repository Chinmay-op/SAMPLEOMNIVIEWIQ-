import json
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "pressure_schema.json"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
INPUT_FILE = DATA_DIR / "raw_pressure_dump.txt"
OUTPUT_FILE = DATA_DIR / "parsed_pressure_payloads.jsonl"

try:
    with open(SCHEMA_PATH, 'r') as f:
        PRESSURE_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    PRESSURE_SCHEMA = None


def validate_payload(payload):
    if PRESSURE_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=PRESSURE_SCHEMA)
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error for {payload.get('timestamp')}: {e.message}")
            return False
    return True 


def parse_pressure_string(raw_string):
    """
    Parses raw comma-separated string from Festo SPAU pressure simulator
    Expected format: ID, TS, PDV_RAW, PRESSURE, OUT_1, OUT_2, STATUS, INT_TEMP, COMP_STATE, TREND
    """
    parts = raw_string.strip().split(',')
    
    if len(parts) != 10:
        return None

    try:
        payload = {
            "device_id": parts[0],
            "timestamp": parts[1],
            "sensor_type": "pressure_transmitter",
            "data": {
                "process_data_variable_raw": int(parts[2]),
                "pressure_bar": float(parts[3]),
                "switching_output_1_active": parts[4] == "1",
                "switching_output_2_active": parts[5] == "1",
                "device_status_code": int(parts[6]),
                "internal_temperature_c": float(parts[7]),
                "compressor_state": parts[8],
                "pressure_trend_5min": parts[9]
            }
        }
        return payload
    except ValueError as e:
        print(f"Warning: Could not parse numerical values: {e}")
        return None


def run_parser():
    print(f"Starting Pressure Parser...")
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
            
            payload = parse_pressure_string(line)
            
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

