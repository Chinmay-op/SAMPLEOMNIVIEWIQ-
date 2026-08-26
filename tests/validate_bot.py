import sys
import time
from pathlib import Path
import importlib
import pandas as pd
import numpy as np
from unittest.mock import patch
import argparse

sys.path.append(str(Path(__file__).resolve().parents[1] / 'src'))

def validate_bot(bot_name: str, num_samples: int = 5000):
    print(f"\n{'='*50}")
    print(f"[AUDIT] Validating ML-Readiness for: {bot_name}")
    print(f"{'='*50}")

    try:
        module_path = f"omniview.edge.bots.{bot_name}"
        bot_module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        print(f"[ERROR] Could not find bot module '{bot_name}'.")
        return

    poll_interval = getattr(bot_module, 'POLL_INTERVAL', 15)
    generate_reading = getattr(bot_module, 'generate_reading', None)

    if not generate_reading:
        print("[ERROR] Bot does not have a 'generate_reading' function.")
        return

    print(f"Generating {num_samples} simulated readings... (Simulating {num_samples * poll_interval / 3600:.1f} hours of runtime)")

    data_records = []
    current_virtual_time = time.time()

    # Mock time.time() so the bot's physics engine thinks real time is passing
    with patch('time.time') as mock_time:
        for _ in range(num_samples):
            mock_time.return_value = current_virtual_time
            payload = generate_reading()
            data_records.append(payload.get("data", {}))
            current_virtual_time += poll_interval

    df = pd.DataFrame(data_records)
    
    score = 100
    deductions = []

    print("\n--- 1. PHYSICS & NULL CHECK ---")
    null_counts = df.isnull().sum().sum()
    if null_counts > 0:
        print(f"[FAIL] Found {null_counts} null values.")
        score -= 20
        deductions.append("Null values generated.")
    else:
        print("[PASS] No null values.")

    # Check for zero-variance columns (dead sensors)
    numeric_df = df.select_dtypes(include=[np.number])
    dead_cols = [col for col in numeric_df.columns if numeric_df[col].std() == 0]
    if dead_cols:
        print(f"[WARN] Found {len(dead_cols)} sensors with 0 variance (completely flat). Models can't learn from dead sensors: {dead_cols}")
        score -= 10
        deductions.append(f"Zero variance columns: {dead_cols}")
    else:
        print("[PASS] All numeric sensors have active variance.")

    print("\n--- 2. AUTOCORRELATION (TIME-SERIES) CHECK ---")
    # Real physical sensors have inertia (AR1 processes). They shouldn't be pure white noise.
    # Autocorrelation at lag=1 should be reasonably high for at least some variables.
    ar_passed = 0
    for col in numeric_df.columns:
        if col not in dead_cols:
            lag1 = numeric_df[col].autocorr(lag=1)
            if pd.notna(lag1) and lag1 > 0.5:
                ar_passed += 1

    if ar_passed == 0 and len(numeric_df.columns) > 0:
        print("[FAIL] No sensors show strong time-series continuity (autocorrelation). The data looks like pure random white noise.")
        score -= 30
        deductions.append("Data lacks time-series inertia (looks like pure noise).")
    else:
        print(f"[PASS] {ar_passed}/{len(numeric_df.columns)} numeric sensors show strong physical continuity (AR1 processes active).")

    print("\n--- 3. NOISE LEVEL (OVERFITTING) CHECK ---")
    # If standard deviation is extremely low relative to the mean, it might be too clean.
    too_clean = 0
    for col in numeric_df.columns:
        if col not in dead_cols:
            mean_val = numeric_df[col].mean()
            if mean_val != 0:
                cv = numeric_df[col].std() / abs(mean_val) # Coefficient of variation
                if cv < 0.0001:
                    too_clean += 1
    
    if too_clean > len(numeric_df.columns) * 0.5:
        print(f"[WARN] More than half your sensors are too 'perfect' (noise < 0.01%). ML models might overfit to synthetic cleanliness.")
        score -= 15
        deductions.append("Data is suspiciously clean (lacks stochastic noise).")
    else:
        print("[PASS] Data has realistic stochastic variance.")

    print(f"\n==================================================")
    print(f"FINAL ML-READINESS SCORE: {score}/100")
    if score >= 90:
        print("GRADE: A (Excellent for ML Training)")
    elif score >= 70:
        print("GRADE: B (Acceptable, but check warnings)")
    else:
        print("GRADE: F (Not recommended for ML Training)")
    
    if deductions:
        print("\nFix the following issues in the bot:")
        for d in deductions:
            print(f"- {d}")
    print(f"==================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit an edge bot for ML readiness.")
    parser.add_argument("bot_name", type=str, help="Name of the bot file without .py (e.g., pressure_bot)")
    parser.add_argument("--samples", type=int, default=5000, help="Number of samples to generate (default: 5000)")
    
    args = parser.parse_args()
    validate_bot(args.bot_name, args.samples)
