"""
omniview.dashboard — Dashboard & Delivery Layer (Layer 6)
==========================================================

Live operator/plant-manager interface (PRD FR8).

Modules:
* **app** — Streamlit dashboard: hero metrics, kVA chart, alerts, HI,
  action cards                                                         (OI-68, OI-69)
* **queries** — Data access layer: TSDB queries → pandas DataFrames    (OI-68)
* **action_card_ui** — Streamlit rendering for action cards            (OI-69)
* **alert_router** — Hierarchical alert routing stub                   (OI-71)
* **jumbo_display** — Jumbo display Modbus register feed stub          (OI-72)
"""

from omniview.dashboard.alert_router import (
    AlertChannel,
    AlertRouter,
    ROUTING_TABLE,
    RoutingResult,
)
from omniview.dashboard.jumbo_display import (
    JumboDisplayFeed,
    RegisterSnapshot,
)
from omniview.dashboard.queries import (
    get_action_cards,
    get_alerts,
    get_energy_and_strokes,
    get_health_index_trend,
    get_idle_load_percent,
    get_kva_timeseries,
    get_latest_kva,
    get_penalty_avoided,
    get_peak_kva_24h,
)

__all__ = [
    "AlertChannel",
    "AlertRouter",
    "JumboDisplayFeed",
    "ROUTING_TABLE",
    "RegisterSnapshot",
    "RoutingResult",
    "get_action_cards",
    "get_alerts",
    "get_energy_and_strokes",
    "get_health_index_trend",
    "get_idle_load_percent",
    "get_kva_timeseries",
    "get_latest_kva",
    "get_penalty_avoided",
    "get_peak_kva_24h",
]
