"""
omniview.rules — Rule Engine & Intelligence Layer (Layers 3–4)
===============================================================

Real-time detection rules that process sensor telemetry and emit events.

Active modules:
* ambient_correlation  — Ambient → cooling-load / demand correlation (S3)

Future modules (Lead track):
* Rolling 15-min kVA + MD trajectory alert  (OI-56)
* Lazy-idle detection heuristic             (OI-57)
* ISO 10816-3 vibration zone classifier     (OI-58)
* Pressure-decay leak proxy                 (OI-59)
* Conflict arbitration (safety > compliance > cost)  (OI-60)
* PdM Stage 0/A — HI batch + CUSUM          (OI-62–67)
"""

from omniview.rules.ambient_correlation import AmbientCorrelationRule, CorrelationEvent

__all__ = [
    "AmbientCorrelationRule",
    "CorrelationEvent",
]
