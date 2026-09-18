"""
omniview.predictive.cusum — Two-Sided CUSUM Change-Point Detection
===================================================================

Early-warning layer on top of the Health Index. Detects sustained
shifts in the HI that individual point-in-time checks would miss.

Uses the tabular CUSUM method (Build Spec §5, §4):

    S_pos[t] = max(0, S_pos[t-1] + (target - HI[t]) / scale - slack)
    S_neg[t] = max(0, S_neg[t-1] - (target - HI[t]) / scale - slack)

    Alert when S_pos > threshold  (HI dropping = degrading)
           or  S_neg > threshold  (HI rising = recovering / recalibration)

Known issue (OI-66): the original implementation over-flagged (12/12 on
the drift fixture) because slack=1.0 and threshold=5.0 were too sensitive.
The retuned defaults (slack=2.0, threshold=8.0) target ≤ 2/12.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from omniview.predictive.priors import CUSUMParams

logger = logging.getLogger(__name__)


@dataclass
class CUSUMAlert:
    """An alert fired by the CUSUM detector.

    Attributes
    ----------
    direction : str
        ``"degrading"`` (HI dropping) or ``"recovering"`` (HI rising).
    cusum_value : float
        The accumulator value when the alert fired.
    current_hi : float
        The Health Index value at the time of alert.
    target_hi : float
        The target HI the CUSUM is tracking (usually 100 for healthy).
    day_index : int
        Which day in the series triggered the alert.
    date : str
        ISO date string if available.
    """

    direction: str
    cusum_value: float
    current_hi: float
    target_hi: float
    day_index: int
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "cusum_value": round(self.cusum_value, 3),
            "current_hi": round(self.current_hi, 2),
            "target_hi": round(self.target_hi, 2),
            "day_index": self.day_index,
            "date": self.date,
        }


class CUSUMDetector:
    """Two-sided tabular CUSUM for Health Index change-point detection.

    Tracks both degradation (HI dropping) and recovery (HI rising)
    against a target HI (default: 95, representing healthy baseline).

    Parameters
    ----------
    params : CUSUMParams, optional
        Configuration (slack, threshold, reset_on_alert).
    target_hi : float
        The expected healthy HI baseline. Default 95.
    scale : float
        Scaling factor for the deviation. Default 10.0.
        This maps HI deviations to a normalized scale where
        the slack parameter makes sense.

    Usage::

        detector = CUSUMDetector()
        alerts = detector.run(hi_series)
        # alerts is a list of CUSUMAlert
    """

    def __init__(
        self,
        params: CUSUMParams | None = None,
        target_hi: float = 95.0,
        scale: float = 10.0,
    ):
        self._params = params or CUSUMParams()
        self._target = target_hi
        self._scale = scale

        # Accumulators
        self._s_pos: float = 0.0  # Tracks degradation (HI below target)
        self._s_neg: float = 0.0  # Tracks recovery (HI above target)

    def reset(self) -> None:
        """Reset both accumulators to zero."""
        self._s_pos = 0.0
        self._s_neg = 0.0

    def step(
        self,
        hi: float,
        day_index: int = 0,
        date_str: str = "",
    ) -> CUSUMAlert | None:
        """Process one HI observation through the CUSUM.

        Parameters
        ----------
        hi : float
            The Health Index value (0–100).
        day_index : int
            Index of this day in the series.
        date_str : str
            ISO date string for the result.

        Returns
        -------
        CUSUMAlert or None
            An alert if a change-point was detected, else None.
        """
        # Normalized deviation from target
        deviation = (self._target - hi) / self._scale

        # Update accumulators (tabular CUSUM)
        # S_pos tracks sustained drops below target
        self._s_pos = max(0.0, self._s_pos + deviation - self._params.slack)
        # S_neg tracks sustained rises above target
        self._s_neg = max(0.0, self._s_neg - deviation - self._params.slack)

        alert: CUSUMAlert | None = None

        if self._s_pos > self._params.threshold:
            alert = CUSUMAlert(
                direction="degrading",
                cusum_value=self._s_pos,
                current_hi=hi,
                target_hi=self._target,
                day_index=day_index,
                date=date_str,
            )
            if self._params.reset_on_alert:
                self._s_pos = 0.0

            logger.info(
                "CUSUM alert: %s (S_pos=%.2f > %.2f) at HI=%.1f on %s",
                alert.direction,
                alert.cusum_value,
                self._params.threshold,
                hi,
                date_str,
            )

        elif self._s_neg > self._params.threshold:
            alert = CUSUMAlert(
                direction="recovering",
                cusum_value=self._s_neg,
                current_hi=hi,
                target_hi=self._target,
                day_index=day_index,
                date=date_str,
            )
            if self._params.reset_on_alert:
                self._s_neg = 0.0

            logger.info(
                "CUSUM alert: %s (S_neg=%.2f > %.2f) at HI=%.1f on %s",
                alert.direction,
                alert.cusum_value,
                self._params.threshold,
                hi,
                date_str,
            )

        return alert

    def run(
        self,
        hi_series: list[float],
        dates: list[str] | None = None,
    ) -> list[CUSUMAlert]:
        """Run CUSUM over an entire Health Index series.

        Parameters
        ----------
        hi_series : list[float]
            Chronological HI values (one per day).
        dates : list[str], optional
            ISO date strings corresponding to each HI value.

        Returns
        -------
        list[CUSUMAlert]
            All change-point alerts detected.
        """
        self.reset()
        alerts: list[CUSUMAlert] = []

        for i, hi in enumerate(hi_series):
            date_str = dates[i] if dates and i < len(dates) else ""
            alert = self.step(hi, day_index=i, date_str=date_str)
            if alert:
                alerts.append(alert)

        logger.info(
            "CUSUM run complete: %d alerts from %d observations "
            "(slack=%.1f, threshold=%.1f)",
            len(alerts),
            len(hi_series),
            self._params.slack,
            self._params.threshold,
        )

        return alerts

    @property
    def s_pos(self) -> float:
        """Current positive accumulator (degradation tracking)."""
        return self._s_pos

    @property
    def s_neg(self) -> float:
        """Current negative accumulator (recovery tracking)."""
        return self._s_neg
