"""
omniview.predictive — Predictive Maintenance (PdM) Stage 0/A Pipeline
======================================================================

Day/week-scale trend analysis for equipment health monitoring.
This is fundamentally different from the real-time anomaly detector
(``omniview.edge.anomaly_detector``) which works at polling-interval
scale (~minutes).

Modules
-------
- ``priors``        — load equipment-class population baselines from YAML
- ``features``      — daily feature aggregation + 7-day rolling slope
- ``health_index``  — weighted z-score composite → 0–100 HI score
- ``cusum``         — two-sided CUSUM change-point early warning
- ``events``        — ``maintenance_risk`` event envelope (Layer 3 §6)
- ``maintenance_log`` — log maintenance events for future Stage B
- ``batch_runner``  — orchestrate the daily per-machine batch job

Usage::

    from omniview.predictive import HealthIndexPipeline

    pipeline = HealthIndexPipeline()
    results = pipeline.run_batch(machine_id="isbm-main-feed",
                                 daily_readings=df)

Design principles:
    - Zero ML in Stage A — unsupervised z-score composite, not XGBoost/LSTM
    - Config-driven priors, not hardcoded thresholds
    - Self-documenting: every HI score comes with contributing features
    - Honest staging: Stage A ships now, B/C are roadmap
"""

from omniview.predictive.priors import PriorStore, EquipmentPriors
from omniview.predictive.features import (
    aggregate_daily,
    compute_rolling_slopes,
    compute_phase_imbalance,
    enrich_daily_features,
)
from omniview.predictive.health_index import (
    compute_health_index,
    HealthIndexResult,
)
from omniview.predictive.cusum import CUSUMDetector, CUSUMAlert
from omniview.predictive.events import build_maintenance_risk_event
from omniview.predictive.batch_runner import HealthIndexPipeline

__all__ = [
    # Priors
    "PriorStore",
    "EquipmentPriors",
    # Features
    "aggregate_daily",
    "compute_rolling_slopes",
    "compute_phase_imbalance",
    "enrich_daily_features",
    # Health Index
    "compute_health_index",
    "HealthIndexResult",
    # CUSUM
    "CUSUMDetector",
    "CUSUMAlert",
    # Events
    "build_maintenance_risk_event",
    # Pipeline
    "HealthIndexPipeline",
]
