"""
omniview.predictive.batch_runner — Daily Health Index Batch Pipeline
====================================================================

Orchestrates the daily per-machine batch job:

    1. Pull 30–60 days of electrical + vibration readings
    2. Aggregate to daily feature rows
    3. Compute 7-day rolling slopes
    4. Compare slopes against equipment-class priors → Health Index
    5. Run CUSUM change-point detection on the HI series
    6. Emit ``maintenance_risk`` events for machines at risk
    7. Return all results for dashboard wiring

Usage::

    from omniview.predictive import HealthIndexPipeline

    pipeline = HealthIndexPipeline()

    # From raw readings (list of dicts with 'time' and 'data')
    results = pipeline.run_batch(
        machine_id="isbm-main-feed",
        electrical_readings=readings,
    )

    # results.hi_series → list of HealthIndexResult
    # results.cusum_alerts → list of CUSUMAlert
    # results.events → list of maintenance_risk event dicts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from omniview.predictive.priors import PriorStore
from omniview.predictive.features import (
    DailyRow,
    aggregate_daily,
    compute_rolling_slopes,
)
from omniview.predictive.health_index import (
    HealthIndexResult,
    compute_health_index,
)
from omniview.predictive.cusum import CUSUMDetector, CUSUMAlert
from omniview.predictive.events import build_maintenance_risk_event

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Complete output of one batch run for one machine.

    Attributes
    ----------
    machine_id : str
        The machine processed.
    daily_rows : list[DailyRow]
        Aggregated daily feature rows.
    slopes : list[dict[str, float | None]]
        Per-day slope features.
    hi_series : list[HealthIndexResult]
        Health Index results per day.
    cusum_alerts : list[CUSUMAlert]
        CUSUM change-point alerts.
    events : list[dict]
        Layer 3 ``maintenance_risk`` events (only for at-risk days).
    latest_hi : HealthIndexResult | None
        The most recent Health Index result.
    """

    machine_id: str
    daily_rows: list[DailyRow] = field(default_factory=list)
    slopes: list[dict[str, float | None]] = field(default_factory=list)
    hi_series: list[HealthIndexResult] = field(default_factory=list)
    cusum_alerts: list[CUSUMAlert] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    latest_hi: HealthIndexResult | None = None

    def summary(self) -> dict[str, Any]:
        """Return a summary dict for logging/dashboard."""
        return {
            "machine_id": self.machine_id,
            "days_processed": len(self.daily_rows),
            "hi_observations": len(self.hi_series),
            "cusum_alerts": len(self.cusum_alerts),
            "events_emitted": len(self.events),
            "latest_hi": (
                round(self.latest_hi.health_index, 2)
                if self.latest_hi
                else None
            ),
            "latest_risk_tier": (
                self.latest_hi.risk_tier if self.latest_hi else None
            ),
        }


class HealthIndexPipeline:
    """Orchestrates the PdM Stage A daily batch pipeline.

    Parameters
    ----------
    prior_store : PriorStore, optional
        Loaded equipment-class priors. If not provided, loads from
        the default config path.
    emit_events_for : set[str]
        Which risk tiers to emit events for. Default: ``{"medium", "high"}``.
        Set to ``{"low", "medium", "high"}`` to emit for all.
    synthetic : bool
        Whether to mark events as synthetic. Default True.
    """

    def __init__(
        self,
        prior_store: PriorStore | None = None,
        emit_events_for: set[str] | None = None,
        synthetic: bool = True,
    ):
        self._store = prior_store or PriorStore()
        self._emit_for = emit_events_for or {"medium", "high"}
        self._synthetic = synthetic

    def run_batch(
        self,
        machine_id: str,
        electrical_readings: list[dict[str, Any]] | None = None,
        vibration_readings: list[dict[str, Any]] | None = None,
    ) -> BatchResult:
        """Run the full pipeline for one machine.

        Parameters
        ----------
        machine_id : str
            The machine to process.
        electrical_readings : list[dict], optional
            Raw electrical readings from TSDB (30-60 days).
        vibration_readings : list[dict], optional
            Raw vibration readings from TSDB (30-60 days).

        Returns
        -------
        BatchResult
            Complete pipeline output.
        """
        result = BatchResult(machine_id=machine_id)

        priors = self._store.get_priors(machine_id)
        hi_params = self._store.hi_params
        cusum_params = self._store.cusum_params

        # Step 1: Aggregate to daily rows
        if electrical_readings:
            elec_daily = aggregate_daily(
                electrical_readings, machine_id, "electrical"
            )
            result.daily_rows.extend(elec_daily)

        if vibration_readings:
            vib_daily = aggregate_daily(
                vibration_readings, machine_id, "vibration"
            )
            # Merge vibration data into existing daily rows
            self._merge_vibration(result.daily_rows, vib_daily)

        if not result.daily_rows:
            logger.warning(
                "No daily rows for machine '%s' — skipping", machine_id
            )
            return result

        # Sort chronologically
        result.daily_rows.sort(key=lambda r: r.date)

        logger.info(
            "Processing %d days for machine '%s' (%s to %s)",
            len(result.daily_rows),
            machine_id,
            result.daily_rows[0].date,
            result.daily_rows[-1].date,
        )

        # Step 2: Compute rolling slopes
        result.slopes = compute_rolling_slopes(
            result.daily_rows,
            window_days=hi_params.slope_window_days,
        )

        # Step 3: Compute Health Index for each day (after warmup)
        for i, (daily_row, slopes) in enumerate(
            zip(result.daily_rows, result.slopes)
        ):
            if i < hi_params.min_warmup_days - 1:
                continue  # Not enough history yet

            hi_result = compute_health_index(
                slopes=slopes,
                priors=priors,
                hi_params=hi_params,
                machine_id=machine_id,
                date_str=daily_row.date.isoformat(),
                gap_flagged=daily_row.gap_flagged,
            )
            result.hi_series.append(hi_result)

        if not result.hi_series:
            logger.warning(
                "Insufficient data for HI computation on '%s' "
                "(need %d days, have %d)",
                machine_id,
                hi_params.min_warmup_days,
                len(result.daily_rows),
            )
            return result

        # Step 4: Run CUSUM on the HI series
        detector = CUSUMDetector(params=cusum_params)
        hi_values = [h.health_index for h in result.hi_series]
        hi_dates = [h.date for h in result.hi_series]
        result.cusum_alerts = detector.run(hi_values, dates=hi_dates)

        # Step 5: Emit events for at-risk days
        # Build a set of dates that had CUSUM alerts
        cusum_dates = {a.date for a in result.cusum_alerts}

        for hi_result in result.hi_series:
            if hi_result.risk_tier in self._emit_for:
                # Get CUSUM alerts for this specific date
                date_alerts = [
                    a for a in result.cusum_alerts if a.date == hi_result.date
                ]
                event = build_maintenance_risk_event(
                    hi_result=hi_result,
                    cusum_alerts=date_alerts,
                    synthetic=self._synthetic,
                )
                result.events.append(event)

        # Track latest
        result.latest_hi = result.hi_series[-1]

        logger.info(
            "Pipeline complete for '%s': %d HI observations, "
            "%d CUSUM alerts, %d events emitted. Latest HI=%.1f (%s)",
            machine_id,
            len(result.hi_series),
            len(result.cusum_alerts),
            len(result.events),
            result.latest_hi.health_index,
            result.latest_hi.risk_tier,
        )

        return result

    @staticmethod
    def _merge_vibration(
        elec_rows: list[DailyRow], vib_rows: list[DailyRow]
    ) -> None:
        """Merge vibration daily data into electrical daily rows."""
        vib_by_date = {r.date: r for r in vib_rows}

        for row in elec_rows:
            vib = vib_by_date.get(row.date)
            if vib and vib.z_rms_velocity_mm_sec is not None:
                row.z_rms_velocity_mm_sec = vib.z_rms_velocity_mm_sec

        # Add vibration-only days that don't have electrical data
        elec_dates = {r.date for r in elec_rows}
        for vib_row in vib_rows:
            if vib_row.date not in elec_dates:
                elec_rows.append(vib_row)
