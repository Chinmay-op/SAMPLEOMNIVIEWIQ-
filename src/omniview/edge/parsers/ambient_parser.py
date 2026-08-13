import json
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "ambient_schema.json"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
INPUT_FILE = DATA_DIR / "raw_ambient_dump.txt"
OUTPUT_FILE = DATA_DIR / "parsed_ambient_payloads.jsonl"

try:
    with open(SCHEMA_PATH, 'r') as f:
        AMBIENT_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    AMBIENT_SCHEMA = None


def validate_payload(payload):
    if AMBIENT_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=AMBIENT_SCHEMA)
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error for {payload.get('timestamp')}: {e.message}")
            return False
    return True 


def parse_ambient_string(raw_string):
    """
    Parses raw comma-separated string from Schneider TH110 simulator
    Expected format: ID, TS, TEMP_C, RH_PCT, OFFSET
    """
    parts = raw_string.strip().split(',')
    
    if len(parts) != 5:
        return None

    try:
        payload = {
            "device_id": parts[0],
            "timestamp": parts[1],
            "sensor_type": "ambient_weather",
            "data": {
                "ambient_temp_c": float(parts[2]),
                "relative_humidity_pct": float(parts[3]),
                "environmental_baseline_offset": float(parts[4])
            }
        }
        return payload
    except ValueError as e:
        print(f"Warning: Could not parse numerical values: {e}")
        return None


def run_parser():
    print(f"Starting Ambient Parser...")
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
            
            payload = parse_ambient_string(line)
            
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

