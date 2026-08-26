import os
import json
import time
import datetime
import urllib.request
from pathlib import Path
import numpy as np

try:
    import scipy.io
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

DEVICE_ID = "Banner-QM30VT1-CWRU"
POLL_INTERVAL = 2.0  # Output a payload every 2 seconds for demo

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "vibration_schema.json"

try:
    with open(SCHEMA_PATH, 'r') as f:
        SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    SCHEMA = None

def validate_payload(payload):
    if SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error: {e.message}")

def get_iso_zone(rms_vel: float) -> str:
    """ISO 10816-3 generic classification"""
    if rms_vel <= 2.8:
        return "ZONE_A"
    elif rms_vel <= 4.5:
        return "ZONE_B"
    elif rms_vel <= 7.1:
        return "ZONE_C"
    else:
        return "ZONE_D"

def download_cwru_file(url: str, dest_path: Path):
    if not dest_path.exists():
        print(f"Downloading {url} to {dest_path}...")
        try:
            urllib.request.urlretrieve(url, dest_path)
        except Exception as e:
            print(f"Failed to download {url}: {e}")

def process_mat_file(file_path: Path, label: str):
    if not HAS_SCIPY:
        print("Scipy is required to read .mat files. Please run: pip install scipy")
        return

    print(f"\nProcessing {file_path.name} ({label})...")
    try:
        mat = scipy.io.loadmat(str(file_path))
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return

    # Find the Drive End (DE) acceleration array
    de_data = None
    for key in mat.keys():
        if key.endswith('DE_time'):
            de_data = mat[key]
            break

    if de_data is None:
        print("Could not find DE_time array in MAT file.")
        return

    de_data = de_data.flatten()
    print(f"Found DE acceleration data: {len(de_data)} samples.")

    # Process in chunks of 12000 samples (1 second at 12kHz)
    chunk_size = 12000
    num_chunks = len(de_data) // chunk_size

    for i in range(min(5, num_chunks)): # Process up to 5 chunks for demo
        chunk = de_data[i * chunk_size : (i + 1) * chunk_size]
        
        # Physics Mapping
        accel_rms = float(np.std(chunk))
        accel_peak = float(np.max(np.abs(chunk)))
        
        # Rough mapping from high freq g's to overall mm/s for demo purposes
        # Normal baseline accel_rms is ~0.07g. Mapped to mm/s -> 0.07 * 20 = 1.4 mm/s (ZONE_A)
        # Fault accel_rms is ~0.2g to 0.5g. Mapped to mm/s -> 0.3 * 20 = 6.0 mm/s (ZONE_C/D)
        vel_rms = round(accel_rms * 20.0, 2)
        
        payload = {
            "device_id": DEVICE_ID,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "sensor_type": "vibration_node",
            "data": {
                "data_source": "CWRU",
                "z_axis_rms_velocity_mm_sec": vel_rms,
                "x_axis_rms_velocity_mm_sec": round(vel_rms * 0.8, 2),
                "z_axis_peak_acceleration_g": round(accel_peak, 2),
                "x_axis_peak_acceleration_g": round(accel_peak * 0.8, 2),
                "high_frequency_rms_acceleration_g": round(accel_rms, 3),
                "temperature_c": 35.0, # Not in CWRU, use constant
                "iso_health_zone": get_iso_zone(vel_rms)
            }
        }
        
        validate_payload(payload)
        print(json.dumps(payload))
        time.sleep(POLL_INTERVAL)


def run():
    cwru_dir = Path(__file__).resolve().parents[4] / "data" / "cwru"
    cwru_dir.mkdir(parents=True, exist_ok=True)
    
    # 97.mat = Normal Baseline, 105.mat = Inner Race Fault
    urls = {
        "97.mat": "https://engineering.case.edu/sites/default/files/97.mat",
        "105.mat": "https://engineering.case.edu/sites/default/files/105.mat"
    }

    print("Starting CWRU Public Dataset Loader...")
    
    for filename, url in urls.items():
        file_path = cwru_dir / filename
        download_cwru_file(url, file_path)
        
        if file_path.exists():
            label = "Normal Baseline" if filename == "97.mat" else "Inner Race Fault"
            process_mat_file(file_path, label)

if __name__ == "__main__":
    run()
