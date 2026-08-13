import json
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "stroke_schema.json"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
INPUT_FILE = DATA_DIR / "raw_stroke_dump.txt"
OUTPUT_FILE = DATA_DIR / "parsed_stroke_payloads.jsonl"

try:
    with open(SCHEMA_PATH, 'r') as f:
        STROKE_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    STROKE_SCHEMA = None


def validate_payload(payload):
    if STROKE_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=STROKE_SCHEMA)
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error for {payload.get('timestamp')}: {e.message}")
            return False
    return True 


def parse_stroke_string(raw_string):
    """
    Parses raw comma-separated string from Sick IME Stroke simulator
    Expected format: ID, TS, BDC1, COUNTER, DEV_TEMP, OP_HOURS, SIG_QUAL, STROKES_INT, CYCLE_TIME
    """
    parts = raw_string.strip().split(',')
    
    if len(parts) != 9:
        return None

    try:
        payload = {
            "device_id": parts[0],
            "timestamp": parts[1],
            "sensor_type": "digital_pulse_counter",
            "data": {
                "switching_state_bdc1": parts[2] == "1",
                "counter_value": int(parts[3]),
                "device_temperature_c": float(parts[4]),
                "operating_hours": int(parts[5]),
                "signal_quality": int(parts[6]),
                "strokes_in_interval": int(parts[7]),
                "last_cycle_time_seconds": float(parts[8])
            }
        }
        return payload
    except ValueError as e:
        print(f"Warning: Could not parse numerical values: {e}")
        return None


def run_parser():
    print(f"Starting Stroke Parser...")
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
            
            payload = parse_stroke_string(line)
            
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

