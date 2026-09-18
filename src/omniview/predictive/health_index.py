"""
omniview.predictive.health_index — Health Index Computation (Stage A)
=====================================================================

Computes a 0–100 Health Index score per machine from slope features
compared against equipment-class population priors.

Formula (Build Spec §5, Stage A)::

    avg_z = mean(directional_z_score(slope_i, prior_i) for each tracked signal)
    health_index = clip(100 - avg_z * z_scale, 0, 100)

Where:
- ``slope_i`` is the 7-day trailing slope of signal i
- ``prior_i`` is the population-prior (mean, std) for signal i
- ``z_scale`` controls how aggressively deviations drop the score
  (default 15 → a 1-σ deviation drops HI by 15 points)

The HI is unsupervised by design — no logged failures needed (that's
Stage B). It's interpretable: each contributing feature is visible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from omniview.predictive.priors import EquipmentPriors, HealthIndexParams

logger = logging.getLogger(__name__)


@dataclass
class ContributingFeature:
    """One signal's contribution to the Health Index.

    Provides full traceability: the client can see *why* a machine was
    flagged, which matters in front of an audience.
    """

    signal: str
    slope_value: float
    prior_mean: float
    prior_std: float
    z_score: float
    direction: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "slope_value": round(self.slope_value, 6),
            "prior_mean": self.prior_mean,
            "prior_std": self.prior_std,
            "z_score": round(self.z_score, 3),
            "direction": self.direction,
            "description": self.description,
        }


@dataclass
class HealthIndexResult:
    """Result of a Health Index computation for one machine on one day.

    Attributes
    ----------
    machine_id : str
        The machine this HI belongs to.
    date : str
        ISO date string (YYYY-MM-DD).
    health_index : float
        0–100 score. 100 = perfectly healthy, 0 = critical.
    risk_tier : str
        ``"low"``, ``"medium"``, or ``"high"``.
    confidence_stage : str
        Always ``"stage_a_unsupervised"`` for Stage A.
    contributing_features : list[ContributingFeature]
        Per-signal breakdown of the score.
    avg_z : float
        The mean z-score that drove the HI.
    signal_count : int
        Number of signals with valid slope data.
    gap_flagged : bool
        Whether any gap was detected in the input data.
    """

    machine_id: str
    date: str
    health_index: float
    risk_tier: str
    confidence_stage: str = "stage_a_unsupervised"
    contributing_features: list[ContributingFeature] = field(
        default_factory=list
    )
    avg_z: float = 0.0
    signal_count: int = 0
    gap_flagged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "date": self.date,
            "health_index": round(self.health_index, 2),
            "risk_tier": self.risk_tier,
            "confidence_stage": self.confidence_stage,
            "avg_z": round(self.avg_z, 4),
            "signal_count": self.signal_count,
            "gap_flagged": self.gap_flagged,
            "contributing_features": [
                f.to_dict() for f in self.contributing_features
            ],
        }


def compute_health_index(
    slopes: dict[str, float | None],
    priors: EquipmentPriors,
    hi_params: HealthIndexParams,
    machine_id: str = "",
    date_str: str = "",
    gap_flagged: bool = False,
) -> HealthIndexResult:
    """Compute the Health Index for one machine on one day.

    Parameters
    ----------
    slopes : dict[str, float | None]
        Slope values keyed by ``"{signal}_slope_7d"``. ``None`` values
        are skipped (insufficient data for that signal).
    priors : EquipmentPriors
        Population baselines for this machine's equipment class.
    hi_params : HealthIndexParams
        Configuration (z_scale, risk tiers).
    machine_id : str
        Machine identifier for the result.
    date_str : str
        ISO date string for the result.
    gap_flagged : bool
        Whether the input data had gaps.

    Returns
    -------
    HealthIndexResult
        The computed Health Index with full feature breakdown.
    """
    contributing: list[ContributingFeature] = []
    z_scores: list[float] = []

    for signal_name, prior in priors.signals.items():
        # Look for the slope key (e.g. "current_a_avg_slope_7d")
        slope_key = f"{signal_name}_slope_{hi_params.slope_window_days}d"
        slope_value = slopes.get(slope_key)

        if slope_value is None:
            continue

        # Compute direction-aware z-score
        z = prior.directional_z_score(slope_value)
        z_scores.append(z)

        contributing.append(
            ContributingFeature(
                signal=signal_name,
                slope_value=slope_value,
                prior_mean=prior.mean,
                prior_std=prior.std,
                z_score=z,
                direction=prior.direction,
                description=prior.description,
            )
        )

    # Compute average z-score
    if z_scores:
        avg_z = sum(z_scores) / len(z_scores)
    else:
        avg_z = 0.0

    # HI formula: clip(100 - avg_z * z_scale, 0, 100)
    hi = max(0.0, min(100.0, 100.0 - avg_z * hi_params.z_scale))

    # Determine risk tier
    risk_tier = _classify_risk(hi, hi_params.risk_tiers)

    # Sort contributing features by z-score (worst first)
    contributing.sort(key=lambda f: f.z_score, reverse=True)

    result = HealthIndexResult(
        machine_id=machine_id,
        date=date_str,
        health_index=hi,
        risk_tier=risk_tier,
        contributing_features=contributing,
        avg_z=avg_z,
        signal_count=len(z_scores),
        gap_flagged=gap_flagged,
    )

    logger.debug(
        "HI for %s on %s: %.1f (%s) from %d signals, avg_z=%.3f",
        machine_id,
        date_str,
        hi,
        risk_tier,
        len(z_scores),
        avg_z,
    )

    return result


def _classify_risk(
    hi: float, tiers: dict[str, int]
) -> str:
    """Map a Health Index score to a risk tier.

    Parameters
    ----------
    hi : float
        Health Index (0–100).
    tiers : dict
        ``{"high": 40, "medium": 70, "low": 100}``.

    Returns
    -------
    str
        ``"high"``, ``"medium"``, or ``"low"``.
    """
    if hi < tiers.get("high", 40):
        return "high"
    elif hi < tiers.get("medium", 70):
        return "medium"
    else:
        return "low"
