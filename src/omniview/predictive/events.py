"""
omniview.predictive.events — ``maintenance_risk`` Event Envelope
================================================================

Builds the Layer 3 event for PdM Stage A. Conforms to the event
envelope contract (§3):

    event_id · machine_id · device_id? · timestamp · source_unit ·
    event_type · severity · confidence_stage? · synthetic · payload{}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from omniview.predictive.health_index import HealthIndexResult
from omniview.predictive.cusum import CUSUMAlert


def build_maintenance_risk_event(
    hi_result: HealthIndexResult,
    cusum_alerts: list[CUSUMAlert] | None = None,
    device_id: str | None = None,
    synthetic: bool = True,
) -> dict[str, Any]:
    """Build a ``maintenance_risk`` Layer 3 event from an HI result.

    Parameters
    ----------
    hi_result : HealthIndexResult
        The computed Health Index for one machine/day.
    cusum_alerts : list[CUSUMAlert], optional
        Any CUSUM alerts associated with this HI observation.
    device_id : str, optional
        Specific device ID if different from machine_id.
    synthetic : bool
        Whether this is from synthetic/proxy data.

    Returns
    -------
    dict
        A complete Layer 3 event envelope.
    """
    # Map risk tier to severity
    severity_map = {
        "high": "critical",
        "medium": "alert",
        "low": "info",
    }

    payload: dict[str, Any] = {
        "health_index": round(hi_result.health_index, 2),
        "risk_tier": hi_result.risk_tier,
        "confidence_stage": hi_result.confidence_stage,
        "avg_z_score": round(hi_result.avg_z, 4),
        "signal_count": hi_result.signal_count,
        "gap_flagged": hi_result.gap_flagged,
        "contributing_features": {
            f.signal: {
                "slope_7d": round(f.slope_value, 6),
                "z_score": round(f.z_score, 3),
                "direction": f.direction,
                "prior_mean": f.prior_mean,
                "prior_std": f.prior_std,
            }
            for f in hi_result.contributing_features
        },
    }

    # Attach CUSUM alerts if any
    if cusum_alerts:
        payload["cusum_alerts"] = [a.to_dict() for a in cusum_alerts]
        payload["cusum_alert_count"] = len(cusum_alerts)
    else:
        payload["cusum_alerts"] = []
        payload["cusum_alert_count"] = 0

    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "machine_id": hi_result.machine_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_unit": "predictive_maintenance_stage_a",
        "event_type": "maintenance_risk",
        "severity": severity_map.get(hi_result.risk_tier, "info"),
        "confidence_stage": hi_result.confidence_stage,
        "synthetic": synthetic,
        "payload": payload,
    }

    if device_id:
        event["device_id"] = device_id

    if hi_result.date:
        event["observation_date"] = hi_result.date

    return event
