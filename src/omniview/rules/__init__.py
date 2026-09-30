"""
omniview.rules — Rule Engine & Intelligence Layer (Layers 3–4)
===============================================================

Real-time detection rules that process sensor telemetry and emit events.

Active modules:
* ambient_correlation  — Ambient → cooling-load / demand correlation (S3)

Shipped modules:
* Action-card generator from rule/PdM events        (OI-69)
* Gas / switchboard overheat detector                (S1)
* Live 15-min MD risk detector                       (F02)
* Lazy-idle waste detector                           (F04)
* Pressure-leak proxy detector                       (F05)
* ISO 10816-3 vibration zone classifier              (F06)
* Detectors live runner (TSDB → wire → rules → alerts)

Future modules (Lead track):
* Conflict arbitration (safety > compliance > cost)  (OI-60)
* PdM Stage 0/A — HI batch + CUSUM                  (OI-62–67)
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
)
from omniview.rules.pressure_leak import (
    PressureLeakDetector,
    PressureLeakEvent,
)
from omniview.rules.vibration_zone import (
    VibrationZoneDetector,
    VibrationZoneEvent,
    classify_zone,
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
    # Lazy Idle (F04)
    "LazyIdleDetector",
    "LazyIdleEvent",
    # Pressure Leak (F05)
    "PressureLeakDetector",
    "PressureLeakEvent",
    # Vibration Zone (F06)
    "VibrationZoneDetector",
    "VibrationZoneEvent",
    "classify_zone",
    # Live Runner
    "DetectorsLiveRunner",
    "DetectorEntry",
    "CycleMetrics",
    "build_default_registry",
    # Ambient Correlation (S3)
    "AmbientCorrelationRule",
    "CorrelationEvent",
]
