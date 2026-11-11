"""
omniview.rules — Rule Engine & Intelligence Layer (Layers 3–4)
===============================================================

Real-time detection rules that process sensor telemetry and emit events.

Active modules:
* ambient_correlation  — Ambient → cooling-load / demand correlation (S3)
* demand_slots         — 96-slot day-ahead demand plan & maintenance attachment (Feature 3)
* waste_schedule       — Waste schedule composer & maintenance suppression (Feature 4)

Shipped modules:
* Action-card generator from rule/PdM events        (OI-69)
* Gas / switchboard overheat detector                (S1)
* Live 15-min MD risk detector                       (F02)
* Lazy-idle waste detector                           (F04)
* Pressure-leak proxy detector                       (F05)
* ISO 10816-3 vibration zone classifier              (F06)
* Cooling malfunction detector                       (F07 / OI-145)
* Predictive maintenance facade & service flag       (OI-62, OI-148, OI-154)
* Detectors live runner (TSDB → wire → rules → alerts)
"""

from omniview.rules.action_cards import (
    ActionCard,
    ActionCardGenerator,
    CARD_TEMPLATES,
)
from omniview.rules.gas_overheat import (
    GasOverheatDetector,
    GasOverheatEvent,
)
from omniview.rules.demand_window import (
    DemandWindowDetector,
    MDRiskEvent,
)
from omniview.rules.lazy_idle import (
    LazyIdleDetector,
    LazyIdleEvent,
    evaluate_lazy_idle,
)
from omniview.rules.demand_slots import (
    NUM_SLOTS_PER_DAY,
    SLOT_DURATION_MINUTES,
    MachineRecord,
    SlotDemand,
    DayAheadDemandPlan,
    format_slot_time,
    generate_baseline_campus_slots,
    aggregate_96_slot_demand,
)
from omniview.rules.waste_schedule import (
    WasteSchedule,
    compose_waste_schedule,
)
from omniview.rules.pressure_leak import (
    PressureLeakDetector,
    PressureLeakEvent,
)
from omniview.rules.vibration_zone import (
    VibrationZoneDetector,
    VibrationZoneEvent,
    classify_zone,
    evaluate_vibration_zone,
)
from omniview.rules.detectors_live import (
    DetectorsLiveRunner,
    DetectorEntry,
    CycleMetrics,
    build_default_registry,
)
from omniview.rules.ambient_correlation import (
    AmbientCorrelationRule,
    CorrelationEvent,
)
from omniview.rules.cooling_malfunction import (
    CoolingMalfunctionDetector,
    CoolingMalfunctionEvent,
    evaluate_cooling_malfunction,
    get_cooling_thresholds,
    load_cooling_calibration,
)
from omniview.rules.predictive_maintenance import (
    run_stage_a_pipeline,
    predict_maintenance_risk,
    DEMO_PRIORS,
    MachineServiceRegistry,
    get_machine_service_status,
    set_machine_service_status,
    clear_machine_service_registry,
)

__all__ = [
    # Action Cards
    "ActionCard",
    "ActionCardGenerator",
    "CARD_TEMPLATES",
    # Gas Overheat (S1)
    "GasOverheatDetector",
    "GasOverheatEvent",
    # Demand Window (F02)
    "DemandWindowDetector",
    "MDRiskEvent",
    # 96-Slot Demand Plan (Feature 3 / OI-146 / OI-154)
    "NUM_SLOTS_PER_DAY",
    "SLOT_DURATION_MINUTES",
    "MachineRecord",
    "SlotDemand",
    "DayAheadDemandPlan",
    "format_slot_time",
    "generate_baseline_campus_slots",
    "aggregate_96_slot_demand",
    # Lazy Idle (F04 / OI-154)
    "LazyIdleDetector",
    "LazyIdleEvent",
    "evaluate_lazy_idle",
    # Waste Schedule (Feature 4 / OI-139 / OI-154)
    "WasteSchedule",
    "compose_waste_schedule",
    # Pressure Leak (F05)
    "PressureLeakDetector",
    "PressureLeakEvent",
    # Vibration Zone (F06)
    "VibrationZoneDetector",
    "VibrationZoneEvent",
    "classify_zone",
    "evaluate_vibration_zone",
    # Live Runner
    "DetectorsLiveRunner",
    "DetectorEntry",
    "CycleMetrics",
    "build_default_registry",
    # Ambient Correlation (S3)
    "AmbientCorrelationRule",
    "CorrelationEvent",
    # Predictive Maintenance (Stage A / Feature 2 / OI-154)
    "run_stage_a_pipeline",
    "predict_maintenance_risk",
    "DEMO_PRIORS",
    "MachineServiceRegistry",
    "get_machine_service_status",
    "set_machine_service_status",
    "clear_machine_service_registry",
    # Cooling Malfunction (F07 / OI-145 / LLD §3)
    "CoolingMalfunctionDetector",
    "CoolingMalfunctionEvent",
    "evaluate_cooling_malfunction",
    "get_cooling_thresholds",
    "load_cooling_calibration",
]
