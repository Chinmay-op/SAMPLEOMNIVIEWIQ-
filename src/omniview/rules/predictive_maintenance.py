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
    return pipeline.run_batch(
        machine_id=machine_id,
        electrical_readings=readings,
        vibration_readings=vibration_readings,
    )


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

    return build_maintenance_risk_event(
        hi_result=computed_hi,
        cusum_alerts=cusum_alerts,
        device_id=device_id or m_id,
        synthetic=synthetic,
    )


__all__ = [
    # Facade Functions & Constants
    "run_stage_a_pipeline",
    "predict_maintenance_risk",
    "evaluate_cooling_malfunction",
    "CoolingMalfunctionEvent",
    "CoolingMalfunctionDetector",
    "DEMO_PRIORS",
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
