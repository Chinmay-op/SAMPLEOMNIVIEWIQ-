"""
OmniView IQ — Thread-Safe Edge State Manager
Prevents race conditions, file corruption, and missing keys between concurrent sensor bots.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATE_FILE = Path(".edge_state.json")
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {
    "machine_running": True,
    "current_a_avg": 120.0,
    "grid_voltage_sag": False,
    "compressor_running": 0,
    "pneumatic_pressure": 35.0,
    "thermal_duty_cycle": 50.0,
    "thermal_pv": 250.0,
    "heater_failed": False,
    "ambient_temp_c": 25.0,
    "environmental_baseline_offset": 1.0,
    "last_cycle_time": 15.0,
}

# Pre-populate cache from disk if available
if _STATE_FILE.exists():
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            disk_state = json.load(f)
            if isinstance(disk_state, dict):
                _CACHE.update(disk_state)
    except Exception:
        pass


def get_edge_state() -> dict[str, Any]:
    """Return a thread-safe snapshot of the current edge state."""
    with _LOCK:
        return dict(_CACHE)


def update_edge_state(updates: dict[str, Any]) -> None:
    """Atomically update the edge state in memory and persist safely."""
    with _LOCK:
        _CACHE.update(updates)
        try:
            # Atomic disk write: write to temp file then replace
            tmp_file = Path(".edge_state.json.tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(_CACHE, f)
            tmp_file.replace(_STATE_FILE)
        except Exception as e:
            logger.debug("Failed to persist edge state: %s", e)
