import urllib.request
import os
from pathlib import Path

# The official UCI direct download URL for the CSV
UCI_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/00374/energydata_complete.csv"

def main():
    # Resolve the path to data/sensor_datasets/
    root_dir = Path(__file__).resolve().parents[4]
    data_dir = root_dir / "data" / "sensor_datasets"
    
    # Ensure the directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    
    dest_path = data_dir / "energydata_complete.csv"
    
    print(f"Downloading UCI Appliances Energy dataset from {UCI_URL}...")
    print(f"Target location: {dest_path}")
    
    try:
        urllib.request.urlretrieve(UCI_URL, dest_path)
        print(f"✅ Download complete! File size: {os.path.getsize(dest_path) / (1024*1024):.2f} MB")
    except Exception as e:
        print(f"❌ Download failed: {e}")

if __name__ == "__main__":
    main()
