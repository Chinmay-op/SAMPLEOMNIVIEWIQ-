"""
OmniView IQ — Robust Detached Service Stopper
Terminates background Bots Runner and Streamlit Dashboard processes.
"""

import os
import sys
import json
import signal
import subprocess
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent
    pid_file = root_dir / ".running_pids.json"

    # 1. Kill from pid file
    if pid_file.exists():
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pids = json.load(f)
            for name, pid in pids.items():
                if pid:
                    print(f"Stopping {name} (PID: {pid})...")
                    try:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                    except Exception as e:
                        print(f"  Error stopping PID {pid}: {e}")
            pid_file.unlink(missing_ok=True)
        except Exception as ex:
            print(f"Error reading {pid_file}: {ex}")

    # 2. Kill residual patterns with wmic/taskkill
    for pattern in ["omniview.edge.bots.runner", "live_tester.py"]:
        try:
            cmd = f'powershell -Command "Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like \'*\"{pattern}\"*\' -or $_.CommandLine -like \'*{pattern}*\' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"'
            subprocess.run(cmd, shell=True, capture_output=True)
        except Exception:
            pass

    print("[OK] Background services stopped successfully.")

if __name__ == "__main__":
    main()
