"""
omniview.rules — Rule Engine & Intelligence Layer (Layers 3–4)
===============================================================

Owned by Lead (Dnyandev). Package scaffolded here so cross-imports resolve.

Shipped modules:
* Action-card generator from rule/PdM events        (OI-69)
* Gas / switchboard overheat detector                (S1)

Future modules (Lead track):
* Rolling 15-min kVA + MD trajectory alert  (OI-56)
* Lazy-idle detection heuristic             (OI-57)
* ISO 10816-3 vibration zone classifier     (OI-58)
* Pressure-decay leak proxy                 (OI-59)
* Conflict arbitration (safety > compliance > cost)  (OI-60)
* PdM Stage 0/A — HI batch + CUSUM          (OI-62–67)
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

__all__ = [
    "ActionCard",
    "ActionCardGenerator",
    "CARD_TEMPLATES",
    "GasOverheatDetector",
    "GasOverheatEvent",
]

