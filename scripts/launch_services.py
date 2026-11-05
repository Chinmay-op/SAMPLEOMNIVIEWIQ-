"""
OmniView IQ — Robust Detached Service Launcher
Launches the Live Bots runner and the Streamlit Dashboard as detached Windows processes,
ensuring they persist independently after startup scripts finish.
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent
    venv_python = root_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print(f"[ERROR] Virtual environment not found at {venv_python}")
        sys.exit(1)

    pid_file = root_dir / ".running_pids.json"
    
    # Flags for completely detached independent processes on Windows:
    # DETACHED_PROCESS (0x00000008) | CREATE_NEW_PROCESS_GROUP (0x00000200)
    flags = 0x00000008 | 0x00000200
    # Try adding CREATE_BREAKAWAY_FROM_JOB (0x01000000) if allowed
    try:
        flags |= 0x01000000
    except Exception:
        pass
    
    # 1. Start Bots & Ingest Runner
    bots_cmd = [str(venv_python), "-m", "omniview.edge.bots.runner"]
    try:
        bots_proc = subprocess.Popen(
            bots_cmd,
            cwd=str(root_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )
    except OSError:
        # If breakaway from job is denied by sandbox, fallback without it
        flags = 0x00000008 | 0x00000200
        bots_proc = subprocess.Popen(
            bots_cmd,
            cwd=str(root_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )
    print(f"[OK] Live Bots & Ingest Runner started (PID: {bots_proc.pid})")

    # Give bots 2 seconds to initialize
    time.sleep(2)

    # 2. Start Streamlit Live Tester Dashboard
    port = sys.argv[1] if len(sys.argv) > 1 else "8501"
    dash_cmd = [
        str(venv_python), "-m", "streamlit", "run",
        "src/omniview/dashboard/live_tester.py",
        f"--server.port={port}",
        "--server.headless=true"
    ]
    dash_proc = subprocess.Popen(
        dash_cmd,
        cwd=str(root_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags
    )
    print(f"[OK] Streamlit Dashboard started on port {port} (PID: {dash_proc.pid})")

    # Save PIDs
    pids = {
        "bots_runner": bots_proc.pid,
        "dashboard": dash_proc.pid
    }
    with open(pid_file, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)

    print("[OK] Services launched and PIDs persisted to .running_pids.json")

if __name__ == "__main__":
    main()
