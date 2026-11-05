"""
OmniView IQ — Feature 2 Live System Health Audit Script
Audits Docker containers, TimescaleDB telemetry flow, NTP drift,
Streamlit dashboard HTTP status, and Feature 2 unit test suite.
"""

import sys
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

def print_section(title: str) -> None:
    print(f"\n\033[93m{title}\033[0m")

def print_pass(msg: str) -> None:
    print(f"   \033[92m[PASS]\033[0m {msg}")

def print_warn(msg: str) -> None:
    print(f"   \033[93m[WARN]\033[0m {msg}")

def print_fail(msg: str) -> None:
    print(f"   \033[91m[FAIL]\033[0m {msg}")

def print_info(msg: str) -> None:
    print(f"   {msg}")

def check_docker() -> bool:
    print_section("1. Docker Infrastructure:")
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            check=True
        )
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        if not lines:
            print_warn("No running Docker containers found.")
            return False
        for line in lines:
            if "omniview-tsdb" in line or "omniview-mosquitto" in line:
                print_pass(line)
            else:
                print_info(line)
        return True
    except Exception as e:
        print_fail(f"Docker is not accessible: {e}")
        return False

def check_tsdb() -> bool:
    print_section("2. TimescaleDB Sensor Telemetry Flow:")
    try:
        from omniview.ingest.db import get_engine
        from sqlalchemy import text
        engine = get_engine()
        sensors = ["electrical", "thermal", "pressure", "vibration", "gas", "stroke", "ambient"]
        all_ok = True
        with engine.connect() as conn:
            for s in sensors:
                try:
                    cnt = conn.execute(text(f"SELECT count(*) FROM readings_{s}")).scalar() or 0
                    max_t = conn.execute(text(f"SELECT max(time) FROM readings_{s}")).scalar()
                    if cnt > 0:
                        print_pass(f"{s:<15} | Rows: {cnt:<6} | Latest: {max_t}")
                    else:
                        print_warn(f"{s:<15} | Rows: 0 (No data yet)")
                        all_ok = False
                except Exception as ex:
                    print_fail(f"{s:<15} | Error: {ex}")
                    all_ok = False
        return all_ok
    except Exception as e:
        print_fail(f"Could not connect to TimescaleDB: {e}")
        return False

def check_ntp() -> bool:
    print_section("3. NTP Gateway Clock Drift:")
    try:
        from omniview.edge.ntp_guard import check_drift
        s = check_drift()
        status_str = "OK (SYNCED)" if s.is_synced else "OUT OF SYNC"
        msg = f"Status: {status_str} | Offset: {s.offset_seconds:+.3f}s | Server: {s.ntp_server}"
        if s.is_synced:
            print_pass(msg)
            return True
        else:
            print_warn(msg)
            return False
    except Exception as e:
        print_warn(f"Could not check NTP server: {e}")
        return False

def check_dashboard(port: int = 8501) -> bool:
    print_section("4. Streamlit Dashboard HTTP Status:")
    url = f"http://localhost:{port}/_stcore/health"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print_pass(f"Dashboard is ONLINE and responding at http://localhost:{port}")
                return True
            else:
                print_warn(f"Dashboard returned HTTP {resp.status}")
                return False
    except Exception as e:
        print_fail(f"Dashboard is not responding on port {port}: {e}")
        return False

def check_tests() -> bool:
    print_section("5. Feature 2 Unit & Integration Test Suite:")
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_action_cards.py",
        "tests/test_cooling_malfunction.py",
        "tests/test_cross_feature_service_flag.py",
        "tests/test_predictive.py",
        "tests/test_bots.py",
        "-q"
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print_pass("Feature 2 Test Suite: All tests GREEN.")
        return True
    else:
        print_fail("Feature 2 Test Suite: Test failures detected.")
        return False

def main():
    print("=" * 64)
    print("      OmniView IQ — Feature 2 Live System Health Audit          ")
    print("=" * 64)

    docker_ok = check_docker()
    tsdb_ok = check_tsdb()
    ntp_ok = check_ntp()
    dash_ok = check_dashboard(8501)
    tests_ok = check_tests()

    print("\n" + "=" * 64)
    if docker_ok and tsdb_ok and dash_ok and tests_ok:
        print("\033[92m   [SYSTEM HEALTHY] ALL SYSTEMS ONLINE & FUNCTIONING NORMALLY\033[0m")
    else:
        print("\033[93m   [SYSTEM AUDITED] Check specific warnings/failures above\033[0m")
    print("=" * 64 + "\n")

if __name__ == "__main__":
    main()
