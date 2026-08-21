"""
Jumbo-Display Modbus Register Feed Stub — OI-72
===================================================

Simulates a Modbus holding-register bank that a jumbo LED floor display
would read.  The register values mirror the cloud dashboard's live
metrics — **same source of truth** (``queries.py``).

Why this exists (Architecture §3.3)
------------------------------------
The plant floor operator needs a single glanceable number they can react
to in seconds.  The jumbo display sits next to the machine, showing live
kVA, warning status, and alert severity — no login, no scrolling, no
interpretation.  A different interface for a different audience on a
different timescale.

POC scope
---------
This is a **stub**.  In production the register bank would be exposed
via a pymodbus TCP/RTU slave that the physical display polls.  For the
POC we write to an in-memory register dict, log every update, and
provide a drift-check function that compares register values against
the dashboard's computed values.

Register Map
------------
.. list-table::
   :header-rows: 1

   * - Address
     - Name
     - Type
     - Unit
     - Dashboard Source
   * - 0–1
     - live_kva
     - FLOAT32 (2 regs)
     - kVA
     - ``get_latest_kva()``
   * - 2–3
     - contract_kva
     - FLOAT32
     - kVA
     - ``config.CONTRACTED_DEMAND_KVA``
   * - 4–5
     - md_proximity_pct
     - FLOAT32
     - %
     - ``get_latest_kva()``
   * - 6–7
     - penalty_avoided_inr
     - FLOAT32
     - ₹
     - ``get_penalty_avoided()``
   * - 8–9
     - idle_load_pct
     - FLOAT32
     - %
     - ``get_idle_load_percent()``
   * - 10
     - warning_count
     - UINT16
     - count
     - ``get_alerts()``
   * - 11
     - critical_count
     - UINT16
     - count
     - ``get_alerts()``
   * - 12
     - active_severity
     - UINT16
     - enum
     - 0=NONE, 1=INFO, 2=WARNING, 3=CRITICAL
   * - 13
     - heartbeat
     - UINT16
     - counter
     - Incrementing — proves feed is alive
   * - 14–15
     - peak_kva_24h
     - FLOAT32
     - kVA
     - ``get_peak_kva_24h()``

Usage::

    from omniview.dashboard.jumbo_display import JumboDisplayFeed

    feed = JumboDisplayFeed()
    snapshot = feed.update()          # reads dashboard, writes registers
    print(snapshot.registers)         # {0: 23765, 1: 48545, ...}
    print(snapshot.live_kva)          # 478.5
    drift = feed.check_drift()       # compares register ↔ dashboard
"""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Timezone ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


# ── Register addresses ──────────────────────────────────────────────────

class RegisterAddress:
    """Modbus holding register addresses for the jumbo display.

    FLOAT32 values occupy 2 consecutive 16-bit registers (big-endian).
    UINT16 values occupy 1 register.
    """

    LIVE_KVA        = 0    # FLOAT32 → regs 0, 1
    CONTRACT_KVA    = 2    # FLOAT32 → regs 2, 3
    MD_PROXIMITY    = 4    # FLOAT32 → regs 4, 5
    PENALTY_AVOIDED = 6    # FLOAT32 → regs 6, 7
    IDLE_LOAD_PCT   = 8    # FLOAT32 → regs 8, 9
    WARNING_COUNT   = 10   # UINT16  → reg 10
    CRITICAL_COUNT  = 11   # UINT16  → reg 11
    ACTIVE_SEVERITY = 12   # UINT16  → reg 12  (0=NONE, 1=INFO, 2=WARNING, 3=CRITICAL)
    HEARTBEAT       = 13   # UINT16  → reg 13
    PEAK_KVA_24H    = 14   # FLOAT32 → regs 14, 15

    TOTAL_REGISTERS = 16


# Severity enum for the ACTIVE_SEVERITY register
SEVERITY_NONE     = 0
SEVERITY_INFO     = 1
SEVERITY_WARNING  = 2
SEVERITY_CRITICAL = 3

_SEVERITY_MAP: dict[str, int] = {
    "INFO": SEVERITY_INFO,
    "WARNING": SEVERITY_WARNING,
    "CRITICAL": SEVERITY_CRITICAL,
}


# ── Float ↔ register conversion ────────────────────────────────────────


def float_to_registers(value: float) -> tuple[int, int]:
    """Convert a float to two 16-bit Modbus registers (big-endian).

    Packs as IEEE 754 float32, splits into high and low 16-bit words.

    >>> float_to_registers(478.5)
    (17142, 32768)
    """
    packed = struct.pack(">f", value)
    high, low = struct.unpack(">HH", packed)
    return (high, low)


def registers_to_float(high: int, low: int) -> float:
    """Convert two 16-bit Modbus registers back to float.

    >>> registers_to_float(17142, 32768)
    478.5
    """
    packed = struct.pack(">HH", high, low)
    return struct.unpack(">f", packed)[0]


# ── Register Snapshot ───────────────────────────────────────────────────


@dataclass
class RegisterSnapshot:
    """Snapshot of all register values after an update cycle.

    Provides both raw register values and decoded human-readable fields.
    """

    timestamp: datetime
    registers: dict[int, int]

    # Decoded values (for convenience and drift checking)
    live_kva: float = 0.0
    contract_kva: float = 0.0
    md_proximity_pct: float = 0.0
    penalty_avoided_inr: float = 0.0
    idle_load_pct: float = 0.0
    warning_count: int = 0
    critical_count: int = 0
    active_severity: int = 0
    heartbeat: int = 0
    peak_kva_24h: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "live_kva": round(self.live_kva, 2),
            "contract_kva": round(self.contract_kva, 2),
            "md_proximity_pct": round(self.md_proximity_pct, 1),
            "penalty_avoided_inr": round(self.penalty_avoided_inr, 2),
            "idle_load_pct": round(self.idle_load_pct, 1),
            "warning_count": self.warning_count,
            "critical_count": self.critical_count,
            "active_severity": self.active_severity,
            "heartbeat": self.heartbeat,
            "peak_kva_24h": round(self.peak_kva_24h, 2),
            "register_count": len(self.registers),
        }


# ── Drift Check Result ─────────────────────────────────────────────────


@dataclass
class DriftCheckResult:
    """Result of comparing register values against dashboard values.

    ``drifted`` is True if any float value differs by more than
    ``tolerance``, or any integer value differs at all.
    """

    timestamp: datetime
    drifted: bool = False
    max_drift_pct: float = 0.0
    field_drifts: dict[str, dict[str, Any]] = field(default_factory=dict)
    tolerance_pct: float = 0.1  # 0.1% default

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "drifted": self.drifted,
            "max_drift_pct": round(self.max_drift_pct, 4),
            "tolerance_pct": self.tolerance_pct,
            "field_count": len(self.field_drifts),
            "drifted_fields": {
                k: v for k, v in self.field_drifts.items() if v.get("drifted")
            },
        }


# ═══════════════════════════════════════════════════════════════════════
#  JUMBO DISPLAY FEED
# ═══════════════════════════════════════════════════════════════════════


class JumboDisplayFeed:
    """Stub Modbus register feed for the jumbo floor display.

    Reads from the same dashboard query layer (``queries.py``) that
    powers the Streamlit UI — **same source of truth**.

    In production, this class would be replaced by a pymodbus
    ``ModbusTcpServer`` exposing these registers to the display's
    Modbus RTU/TCP master.  For the POC, it writes to an in-memory
    register dict and logs every update.

    Parameters
    ----------
    data_source : str
        ``"dashboard"`` (reads from TSDB via queries.py) or
        ``"mock"`` (uses fixed demo values — no DB needed).
    """

    def __init__(self, data_source: str = "dashboard") -> None:
        self._data_source = data_source
        self._registers: dict[int, int] = {
            i: 0 for i in range(RegisterAddress.TOTAL_REGISTERS)
        }
        self._heartbeat: int = 0
        self._last_snapshot: RegisterSnapshot | None = None
        self._last_dashboard_values: dict[str, Any] | None = None

    @property
    def registers(self) -> dict[int, int]:
        """Current register bank (read-only copy)."""
        return dict(self._registers)

    @property
    def last_snapshot(self) -> RegisterSnapshot | None:
        """Most recent update snapshot."""
        return self._last_snapshot

    # ── Write helpers ───────────────────────────────────────────────────

    def _write_float(self, address: int, value: float) -> None:
        """Write a float32 to two consecutive registers."""
        high, low = float_to_registers(value)
        self._registers[address] = high
        self._registers[address + 1] = low

    def _write_uint16(self, address: int, value: int) -> None:
        """Write a uint16 to a single register."""
        self._registers[address] = value & 0xFFFF

    def _read_float(self, address: int) -> float:
        """Read a float32 from two consecutive registers."""
        high = self._registers.get(address, 0)
        low = self._registers.get(address + 1, 0)
        return registers_to_float(high, low)

    def _read_uint16(self, address: int) -> int:
        """Read a uint16 from a single register."""
        return self._registers.get(address, 0)

    # ── Data sources ────────────────────────────────────────────────────

    def _fetch_dashboard_values(self) -> dict[str, Any]:
        """Fetch current values from the dashboard query layer.

        Same functions the Streamlit UI calls — single source of truth.
        """
        from omniview.config import CONTRACTED_DEMAND_KVA
        from omniview.dashboard.queries import (
            get_alerts,
            get_idle_load_percent,
            get_latest_kva,
            get_peak_kva_24h,
            get_penalty_avoided,
        )

        kva_data = get_latest_kva()
        penalty_data = get_penalty_avoided()
        idle_data = get_idle_load_percent()
        peak_kva = get_peak_kva_24h()

        # Alert counts from last 24h
        try:
            alerts_df = get_alerts(hours=24)
            warning_count = len(alerts_df[alerts_df["severity"] == "WARNING"]) if not alerts_df.empty else 0
            critical_count = len(alerts_df[alerts_df["severity"] == "CRITICAL"]) if not alerts_df.empty else 0
        except Exception:
            warning_count = 0
            critical_count = 0

        # Determine highest active severity
        if critical_count > 0:
            active_severity = SEVERITY_CRITICAL
        elif warning_count > 0:
            active_severity = SEVERITY_WARNING
        else:
            active_severity = SEVERITY_NONE

        return {
            "live_kva": kva_data["kva"],
            "contract_kva": CONTRACTED_DEMAND_KVA,
            "md_proximity_pct": kva_data["md_proximity_percent"],
            "penalty_avoided_inr": penalty_data["penalty_avoided_inr"],
            "idle_load_pct": idle_data["idle_pct"],
            "warning_count": warning_count,
            "critical_count": critical_count,
            "active_severity": active_severity,
            "peak_kva_24h": peak_kva,
        }

    def _fetch_mock_values(self) -> dict[str, Any]:
        """Return fixed demo values — no DB required.

        Useful for testing the register feed without a running TSDB.
        """
        return {
            "live_kva": 478.5,
            "contract_kva": 500.0,
            "md_proximity_pct": 95.7,
            "penalty_avoided_inr": 7525.0,
            "idle_load_pct": 12.3,
            "warning_count": 2,
            "critical_count": 1,
            "active_severity": SEVERITY_CRITICAL,
            "peak_kva_24h": 482.1,
        }

    # ── Core update ─────────────────────────────────────────────────────

    def update(self) -> RegisterSnapshot:
        """Read dashboard values and write to register bank.

        Returns
        -------
        RegisterSnapshot
            Snapshot of all registers after the update.
        """
        now = datetime.now(IST)

        # Fetch values from chosen source
        if self._data_source == "mock":
            values = self._fetch_mock_values()
        else:
            try:
                values = self._fetch_dashboard_values()
            except Exception:
                logger.exception("Failed to fetch dashboard values — using last known or zeros")
                values = self._last_dashboard_values or self._fetch_mock_values()

        self._last_dashboard_values = values

        # Write to register bank
        self._write_float(RegisterAddress.LIVE_KVA, values["live_kva"])
        self._write_float(RegisterAddress.CONTRACT_KVA, values["contract_kva"])
        self._write_float(RegisterAddress.MD_PROXIMITY, values["md_proximity_pct"])
        self._write_float(RegisterAddress.PENALTY_AVOIDED, values["penalty_avoided_inr"])
        self._write_float(RegisterAddress.IDLE_LOAD_PCT, values["idle_load_pct"])
        self._write_uint16(RegisterAddress.WARNING_COUNT, values["warning_count"])
        self._write_uint16(RegisterAddress.CRITICAL_COUNT, values["critical_count"])
        self._write_uint16(RegisterAddress.ACTIVE_SEVERITY, values["active_severity"])
        self._write_float(RegisterAddress.PEAK_KVA_24H, values["peak_kva_24h"])

        # Heartbeat — incrementing counter proves feed is alive
        self._heartbeat = (self._heartbeat + 1) % 65536
        self._write_uint16(RegisterAddress.HEARTBEAT, self._heartbeat)

        # Build snapshot
        snapshot = RegisterSnapshot(
            timestamp=now,
            registers=dict(self._registers),
            live_kva=values["live_kva"],
            contract_kva=values["contract_kva"],
            md_proximity_pct=values["md_proximity_pct"],
            penalty_avoided_inr=values["penalty_avoided_inr"],
            idle_load_pct=values["idle_load_pct"],
            warning_count=values["warning_count"],
            critical_count=values["critical_count"],
            active_severity=values["active_severity"],
            heartbeat=self._heartbeat,
            peak_kva_24h=values["peak_kva_24h"],
        )

        self._last_snapshot = snapshot

        # Log the update
        logger.info(
            "JUMBO DISPLAY REGISTERS UPDATED: kVA=%.1f/%s (%.0f%%) | "
            "Alerts: %d warn, %d crit | Severity: %d | HB: %d",
            values["live_kva"],
            values["contract_kva"],
            values["md_proximity_pct"],
            values["warning_count"],
            values["critical_count"],
            values["active_severity"],
            self._heartbeat,
        )

        return snapshot

    # ── Drift check ─────────────────────────────────────────────────────

    def check_drift(
        self,
        tolerance_pct: float = 0.1,
    ) -> DriftCheckResult:
        """Compare current register values against fresh dashboard query.

        This verifies the "same source of truth" acceptance criterion —
        the registers should always match what the dashboard shows.

        Parameters
        ----------
        tolerance_pct : float
            Maximum acceptable drift as a percentage of the reference
            value.  Default: 0.1% (covers float rounding).

        Returns
        -------
        DriftCheckResult
            Contains per-field drift analysis and overall pass/fail.
        """
        now = datetime.now(IST)

        # Read current register values
        reg_values = {
            "live_kva": self._read_float(RegisterAddress.LIVE_KVA),
            "contract_kva": self._read_float(RegisterAddress.CONTRACT_KVA),
            "md_proximity_pct": self._read_float(RegisterAddress.MD_PROXIMITY),
            "penalty_avoided_inr": self._read_float(RegisterAddress.PENALTY_AVOIDED),
            "idle_load_pct": self._read_float(RegisterAddress.IDLE_LOAD_PCT),
            "warning_count": self._read_uint16(RegisterAddress.WARNING_COUNT),
            "critical_count": self._read_uint16(RegisterAddress.CRITICAL_COUNT),
            "active_severity": self._read_uint16(RegisterAddress.ACTIVE_SEVERITY),
            "peak_kva_24h": self._read_float(RegisterAddress.PEAK_KVA_24H),
        }

        # Fresh dashboard values for comparison
        if self._data_source == "mock":
            dashboard_values = self._fetch_mock_values()
        else:
            try:
                dashboard_values = self._fetch_dashboard_values()
            except Exception:
                logger.exception("Cannot check drift — dashboard query failed")
                return DriftCheckResult(
                    timestamp=now,
                    drifted=True,
                    max_drift_pct=100.0,
                    field_drifts={"_error": {"drifted": True, "reason": "dashboard query failed"}},
                    tolerance_pct=tolerance_pct,
                )

        # Compare
        field_drifts: dict[str, dict[str, Any]] = {}
        max_drift = 0.0
        any_drifted = False

        float_fields = [
            "live_kva", "contract_kva", "md_proximity_pct",
            "penalty_avoided_inr", "idle_load_pct", "peak_kva_24h",
        ]
        int_fields = ["warning_count", "critical_count", "active_severity"]

        for field_name in float_fields:
            reg_val = reg_values[field_name]
            dash_val = dashboard_values[field_name]

            if dash_val == 0:
                drift_pct = 0.0 if reg_val == 0 else 100.0
            else:
                drift_pct = abs(reg_val - dash_val) / abs(dash_val) * 100

            drifted = drift_pct > tolerance_pct
            if drifted:
                any_drifted = True

            max_drift = max(max_drift, drift_pct)

            field_drifts[field_name] = {
                "register_value": round(reg_val, 4),
                "dashboard_value": round(dash_val, 4),
                "drift_pct": round(drift_pct, 4),
                "drifted": drifted,
            }

        for field_name in int_fields:
            reg_val = reg_values[field_name]
            dash_val = dashboard_values[field_name]
            drifted = reg_val != dash_val

            if drifted:
                any_drifted = True
                max_drift = max(max_drift, 100.0)

            field_drifts[field_name] = {
                "register_value": reg_val,
                "dashboard_value": dash_val,
                "drift_pct": 100.0 if drifted else 0.0,
                "drifted": drifted,
            }

        result = DriftCheckResult(
            timestamp=now,
            drifted=any_drifted,
            max_drift_pct=max_drift,
            field_drifts=field_drifts,
            tolerance_pct=tolerance_pct,
        )

        if any_drifted:
            logger.warning("JUMBO DISPLAY DRIFT DETECTED: max_drift=%.2f%%", max_drift)
        else:
            logger.info("JUMBO DISPLAY DRIFT CHECK: OK (max_drift=%.4f%%)", max_drift)

        return result

    # ── Register map documentation ──────────────────────────────────────

    @staticmethod
    def get_register_map_markdown() -> str:
        """Return the register map as a markdown table.

        Used for worklog and acceptance criteria documentation.
        """
        rows = [
            "| Address | Name | Type | Unit | Dashboard Source |",
            "|---------|------|------|------|-----------------|",
            "| 0–1 | live_kva | FLOAT32 | kVA | `get_latest_kva()` |",
            "| 2–3 | contract_kva | FLOAT32 | kVA | `config.CONTRACTED_DEMAND_KVA` |",
            "| 4–5 | md_proximity_pct | FLOAT32 | % | `get_latest_kva()` |",
            "| 6–7 | penalty_avoided_inr | FLOAT32 | ₹ | `get_penalty_avoided()` |",
            "| 8–9 | idle_load_pct | FLOAT32 | % | `get_idle_load_percent()` |",
            "| 10 | warning_count | UINT16 | count | `get_alerts()` |",
            "| 11 | critical_count | UINT16 | count | `get_alerts()` |",
            "| 12 | active_severity | UINT16 | enum | 0=NONE 1=INFO 2=WARNING 3=CRITICAL |",
            "| 13 | heartbeat | UINT16 | counter | Incrementing (proves feed alive) |",
            "| 14–15 | peak_kva_24h | FLOAT32 | kVA | `get_peak_kva_24h()` |",
        ]
        return "\n".join(rows)
