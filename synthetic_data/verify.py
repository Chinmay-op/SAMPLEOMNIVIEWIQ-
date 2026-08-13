import pandas as pd
import os

output_dir = "output"
files = {
    "master_timeline": "master_timeline.parquet",
    "ambient": "ambient_data.parquet",
    "pressure": "pressure_data.parquet",
    "electrical": "electrical_data.parquet",
    "thermal": "thermal_data.parquet",
    "vibration": "vibration_data.parquet",
    "stroke": "stroke_data.parquet",
}

all_ok = True

for name, fname in files.items():
    path = os.path.join(output_dir, fname)
    df = pd.read_parquet(path)
    ts_min = df["timestamp"].min()
    ts_max = df["timestamp"].max()
    nulls = df.isnull().sum().sum()
    print(f"--- {name} ---")
    print(f"  Rows      : {len(df):,}")
    print(f"  Columns   : {list(df.columns)}")
    print(f"  Time start: {ts_min}")
    print(f"  Time end  : {ts_max}")
    print(f"  Null cells: {nulls}")
    if nulls > 0:
        print(f"  WARNING: Nulls found in {name}!")
        all_ok = False
    print()

print("=" * 40)
if all_ok:
    print("VERIFICATION PASSED: All files look clean.")
else:
    print("VERIFICATION ISSUES FOUND - review above warnings.")
