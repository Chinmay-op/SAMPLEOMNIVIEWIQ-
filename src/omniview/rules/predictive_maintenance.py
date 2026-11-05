"""
omniview.rules.predictive_maintenance — LLD Facade Module for Predictive Maintenance (Stage A)
================================================================================================

Exposes standard entry points for Stage A predictive maintenance:
- ``run_stage_a_pipeline``: Runs daily aggregation, 7-day rolling slopes,
  Health Index calculation, and CUSUM change-point detection.
- ``predict_maintenance_risk``: Builds and returns the Layer 3 ``maintenance_risk``
  event envelope dict.
- ``DEMO_PRIORS``: Clearly labeled placeholder baseline per OI-62 PRD / LLD.

Reference:
- Docs/DS/LLD_Four_Core_Features.md §3 Table 3
- Docs/DS/OI-62_Predictive_Maintenance_Module_PRD.md §6
- Epic OI-135 / OI-62 / OI-65 / OI-67 / OI-148
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from omniview.predictive.priors import (
    PriorStore,
    EquipmentPriors,
    SignalPrior,
    HealthIndexParams,
    CUSUMParams,
)
from omniview.predictive.features import (
    DailyRow,
    aggregate_daily,
    compute_rolling_slopes,
    compute_phase_imbalance,
    enrich_daily_features,
)
from omniview.predictive.health_index import (
    HealthIndexResult,
    ContributingFeature,
    compute_health_index,
)
from omniview.predictive.cusum import (
    CUSUMDetector,
    CUSUMAlert,
)
from omniview.predictive.events import (
    build_maintenance_risk_event,
)
from omniview.predictive.batch_runner import (
    HealthIndexPipeline,
    BatchResult,
)
from omniview.predictive.maintenance_log import (
    MaintenanceLogger,
    MaintenanceEvent,
)
from omniview.rules.cooling_malfunction import (
    CoolingMalfunctionEvent,
    CoolingMalfunctionDetector,
    evaluate_cooling_malfunction,
)

logger = logging.getLogger(__name__)


# ── DEMO_PRIORS (OI-62 PRD / LLD §3 line 61) ────────────────────────────────
# Hardcoded baseline priors for demonstration, development, and testing.
# Clearly labeled as PLACEHOLDER until real site calibration (OI-63/OI-79).
DEMO_PRIORS: dict[str, dict[str, Any]] = {
    "current_a_avg": {
        "description": "Average phase current (A)",
        "mean": 205.0,
        "std": 15.0,
        "direction": "rising",
    },
    "voltage_thd_percent": {
        "description": "Voltage Total Harmonic Distortion (%)",
        "mean": 2.5,
        "std": 0.8,
        "direction": "rising",
    },
    "current_thd_percent": {
        "description": "Current THD (%)",
        "mean": 11.0,
        "std": 3.0,
        "direction": "rising",
    },
    "power_factor_avg": {
        "description": "Average Power Factor",
        "mean": 0.95,
        "std": 0.02,
        "direction": "falling",
    },
    "current_a_neutral": {
        "description": "Neutral current (A)",
        "mean": 0.3,
        "std": 0.2,
        "direction": "rising",
    },
    "phase_imbalance_percent": {
        "description": "Phase current imbalance (%)",
        "mean": 1.5,
        "std": 1.0,
        "direction": "rising",
    },
    "frequency_hz": {
        "description": "Supply frequency (Hz)",
        "mean": 50.0,
        "std": 0.05,
        "direction": "both",
    },
    "z_rms_velocity_mm_sec": {
        "description": "Z-axis RMS vibration velocity (mm/s)",
        "mean": 1.2,
        "std": 0.4,
        "direction": "rising",
    },
    "gas_concentration_ppm": {
        "description": "Gas concentration from wire off-gassing (ppm)",
        "mean": 1.2,
        "std": 0.5,
        "direction": "rising",
    },
    "internal_panel_temp_c": {
        "description": "Internal panel temperature (°C)",
        "mean": 38.0,
        "std": 5.0,
        "direction": "rising",
    },
}


# ── LLD Standard Entry-Point Functions ──────────────────────────────────────


def run_stage_a_pipeline(
    readings: list[dict[str, Any]] | None = None,
    machine_id: str = "isbm-main-feed",
    vibration_readings: list[dict[str, Any]] | None = None,
    prior_store: PriorStore | None = None,
    emit_events_for: set[str] | None = None,
    synthetic: bool = True,
) -> BatchResult:
    """Run the Stage A daily batch pipeline for a target machine.

    Orchestrates:
    1. Daily aggregation of electrical and vibration readings
    2. 7-day rolling least-squares slope computation
    3. Health Index (HI) computation against equipment-class priors
    4. CUSUM change-point shift detection
    5. Emission of Layer 3 ``maintenance_risk`` events for at-risk observations

    Parameters
    ----------
    readings : list[dict[str, Any]], optional
        Raw electrical readings (time-series dicts with timestamp/time and data).
    machine_id : str, default "isbm-main-feed"
        Machine identifier to process.
    vibration_readings : list[dict[str, Any]], optional
        Raw vibration readings from the vibration sensor.
    prior_store : PriorStore, optional
        Equipment priors store; defaults to standard PriorStore().
    emit_events_for : set[str], optional
        Risk tiers to emit events for; defaults to {"medium", "high"}.
    synthetic : bool, default True
        Whether the generated event dicts are flagged as synthetic.

    Returns
    -------
    BatchResult
        Container with daily_rows, slopes, hi_series, cusum_alerts, and events.
    """
    pipeline = HealthIndexPipeline(
        prior_store=prior_store,
        emit_events_for=emit_events_for,
        synthetic=synthetic,
    )
    batch_result = pipeline.run_batch(
        machine_id=machine_id,
        electrical_readings=readings,
        vibration_readings=vibration_readings,
    )
    if batch_result.latest_hi is not None:
        MachineServiceRegistry.get_instance().record_hi(batch_result.latest_hi)
    return batch_result


def predict_maintenance_risk(
    hi_result: HealthIndexResult | str,
    latest_row: Any | None = None,
    cusum_alerts: list[CUSUMAlert] | None = None,
    machine_id: str | None = None,
    device_id: str | None = None,
    confidence_stage: str = "stage_a_unsupervised",
    synthetic: bool = True,
) -> dict[str, Any]:
    """Build and return a Layer 3 ``maintenance_risk`` event envelope dictionary.

    Supports dual invocation contracts:
    1. LLD Contract (preferred):
       ``predict_maintenance_risk(hi_result, cusum_alerts=..., device_id=...)``
       where ``hi_result`` is an instance of ``HealthIndexResult``.
    2. PRD §6 Contract:
       ``predict_maintenance_risk(machine_id, latest_row, ...)``
       where the first argument is a string ``machine_id``.

    Parameters
    ----------
    hi_result : HealthIndexResult or str
        Either a computed HealthIndexResult object, or the machine_id string.
    latest_row : Any, optional
        Used when invoking with PRD signature (latest feature row or DailyRow).
    cusum_alerts : list[CUSUMAlert], optional
        Any active CUSUM alerts for this evaluation.
    machine_id : str, optional
        Machine identifier override.
    device_id : str, optional
        Specific sensor device ID if different from machine_id.
    confidence_stage : str, default "stage_a_unsupervised"
        Confidence tier identifier.
    synthetic : bool, default True
        Whether the event is marked synthetic.

    Returns
    -------
    dict[str, Any]
        Layer 3 compliant ``maintenance_risk`` event dictionary.
    """
    if isinstance(hi_result, HealthIndexResult):
        MachineServiceRegistry.get_instance().record_hi(hi_result)
        target_machine = machine_id or hi_result.machine_id
        return build_maintenance_risk_event(
            hi_result=hi_result,
            cusum_alerts=cusum_alerts,
            device_id=device_id or target_machine,
            synthetic=synthetic,
        )

    # PRD §6 signature: predict_maintenance_risk(machine_id, latest_row, ...)
    target_machine = str(hi_result)
    m_id = target_machine

    # If latest_row is already a HealthIndexResult
    if isinstance(latest_row, HealthIndexResult):
        MachineServiceRegistry.get_instance().record_hi(latest_row)
        return build_maintenance_risk_event(
            hi_result=latest_row,
            cusum_alerts=cusum_alerts,
            device_id=device_id or m_id,
            synthetic=synthetic,
        )

    # If latest_row is a dict or DailyRow, compute HealthIndexResult
    store = PriorStore()
    priors = store.get_priors(m_id)
    hi_params = store.hi_params

    # Check if latest_row provides slopes directly or if we compute them
    slope_dict: dict[str, float | None] = {}
    row_date = ""

    if isinstance(latest_row, dict):
        slope_dict = {
            k: v for k, v in latest_row.items() if k.endswith("_slope_7d")
        }
        row_date = str(latest_row.get("date", ""))
    elif latest_row is not None and hasattr(latest_row, "__dict__"):
        row_date = str(getattr(latest_row, "date", ""))

    computed_hi = compute_health_index(
        slopes=slope_dict,
        priors=priors,
        hi_params=hi_params,
        machine_id=m_id,
        date_str=row_date,
    )
    MachineServiceRegistry.get_instance().record_hi(computed_hi)

    return build_maintenance_risk_event(
        hi_result=computed_hi,
        cusum_alerts=cusum_alerts,
        device_id=device_id or m_id,
        synthetic=synthetic,
    )


# ── Cross-Feature Service Flag Registry & API (OI-154 / LLD §3, §4, §5) ────


class MachineServiceRegistry:
    """In-memory service and maintenance state registry for factory machines.

    Tracks active high-risk Health Index states, scheduled maintenance windows,
    and manual service flags across Feature 2, Feature 3, and Feature 4.
    """

    _instance: MachineServiceRegistry | None = None

    def __init__(self) -> None:
        self._manual_status: dict[str, bool] = {}
        self._latest_hi: dict[str, HealthIndexResult] = {}
        self._scheduled_windows: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    def get_instance(cls) -> MachineServiceRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_status(self, machine_id: str, in_maintenance: bool = True) -> None:
        """Manually override machine maintenance status."""
        self._manual_status[machine_id] = in_maintenance

    def record_hi(self, hi_result: HealthIndexResult) -> None:
        """Record latest Health Index observation for a machine."""
        self._latest_hi[hi_result.machine_id] = hi_result

    def schedule_maintenance(
        self,
        machine_id: str,
        start_date: str,
        downtime_hours: float = 24.0,
        reason: str = "scheduled_service",
    ) -> None:
        """Register a scheduled maintenance window."""
        windows = self._scheduled_windows.setdefault(machine_id, [])
        windows.append(
            {
                "start_date": start_date,
                "downtime_hours": downtime_hours,
                "reason": reason,
            }
        )

    def is_in_maintenance(
        self,
        machine_id: str,
        as_of_date: str | date | datetime | None = None,
        hi_result: HealthIndexResult | None = None,
        log_path: str | Path | None = None,
    ) -> bool:
        """Check whether machine is flagged for service or under maintenance."""
        # 1. Manual override takes precedence if explicitly set
        if machine_id in self._manual_status:
            return self._manual_status[machine_id]

        # 2. Check passed HealthIndexResult or latest recorded HI for machine
        target_hi = hi_result or self._latest_hi.get(machine_id)
        if target_hi is not None:
            if target_hi.risk_tier == "high" or target_hi.health_index < 40.0:
                return True

        # 3. Check in-memory scheduled maintenance windows
        check_date_str = ""
        if isinstance(as_of_date, str):
            check_date_str = as_of_date[:10]
        elif isinstance(as_of_date, (datetime, date)):
            check_date_str = as_of_date.strftime("%Y-%m-%d")
        else:
            check_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for window in self._scheduled_windows.get(machine_id, []):
            start = window.get("start_date", "")
            if start == check_date_str:
                return True
            hours = float(window.get("downtime_hours", 24.0))
            if hours > 24:
                try:
                    s_dt = date.fromisoformat(start)
                    c_dt = date.fromisoformat(check_date_str)
                    days_span = int(hours // 24)
                    if 0 <= (c_dt - s_dt).days <= days_span:
                        return True
                except (ValueError, TypeError):
                    pass

        # 4. Check persistent maintenance log file (MaintenanceLogger)
        try:
            m_logger = MaintenanceLogger(log_path=log_path)
            events = m_logger.read_all()
            for evt in events:
                if evt.machine_id == machine_id:
                    if evt.event_date == check_date_str:
                        return True
                    if evt.downtime_hours and evt.downtime_hours > 24:
                        try:
                            s_dt = date.fromisoformat(evt.event_date)
                            c_dt = date.fromisoformat(check_date_str)
                            days_span = int(evt.downtime_hours // 24)
                            if 0 <= (c_dt - s_dt).days <= days_span:
                                return True
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.debug("Could not inspect maintenance log: %s", e)

        return False

    def clear(self) -> None:
        """Reset all registry state."""
        self._manual_status.clear()
        self._latest_hi.clear()
        self._scheduled_windows.clear()


def get_machine_service_status(
    machine_id: str,
    as_of_date: str | date | datetime | None = None,
    hi_result: HealthIndexResult | None = None,
    log_path: str | Path | None = None,
) -> bool:
    """Return True if machine is flagged for service or under active maintenance.

    According to LLD Section 3 line 85 and Section 5 line 101:
    - Returns True if Health Index is in critical/high-risk tier (risk_tier == 'high' or HI < 40).
    - Returns True if an active or scheduled maintenance event exists in the maintenance log.
    - Returns True if an explicit service flag override is set.
    """
    return MachineServiceRegistry.get_instance().is_in_maintenance(
        machine_id=machine_id,
        as_of_date=as_of_date,
        hi_result=hi_result,
        log_path=log_path,
    )


def set_machine_service_status(
    machine_id: str,
    in_maintenance: bool = True,
) -> None:
    """Manually set or clear a machine's service/maintenance status."""
    MachineServiceRegistry.get_instance().set_status(machine_id, in_maintenance=in_maintenance)


def clear_machine_service_registry() -> None:
    """Clear all service registry state (for test isolation)."""
    MachineServiceRegistry.get_instance().clear()


__all__ = [
    # Facade Functions & Constants
    "run_stage_a_pipeline",
    "predict_maintenance_risk",
    "evaluate_cooling_malfunction",
    "CoolingMalfunctionEvent",
    "CoolingMalfunctionDetector",
    "DEMO_PRIORS",
    # Cross-Feature Service Flag (OI-154 / LLD §3, §4, §5)
    "MachineServiceRegistry",
    "get_machine_service_status",
    "set_machine_service_status",
    "clear_machine_service_registry",
    # Core Re-exports
    "HealthIndexPipeline",
    "BatchResult",
    "HealthIndexResult",
    "ContributingFeature",
    "compute_health_index",
    "DailyRow",
    "aggregate_daily",
    "compute_rolling_slopes",
    "compute_phase_imbalance",
    "enrich_daily_features",
    "PriorStore",
    "EquipmentPriors",
    "SignalPrior",
    "HealthIndexParams",
    "CUSUMDetector",
    "CUSUMAlert",
    "CUSUMParams",
    "build_maintenance_risk_event",
]
