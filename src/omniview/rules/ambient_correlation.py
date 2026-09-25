"""
omniview.rules.ambient_correlation
====================================

Row S3 of the OmniView IQ Feature Ledger:
  "Ambient → cooling-load / demand correlation feature"

This rule correlates the ambient temperature with electrical power consumption
to determine whether a power spike is weather-justified or a genuine anomaly.

How it works:
  1. Maintains a rolling window of paired (ambient_temp, electrical_kw) readings.
  2. Fits a simple linear regression:  expected_kw = slope * ambient_temp + intercept
  3. Computes the residual:  residual = actual_kw - expected_kw
  4. If |residual| > threshold (dynamic, based on rolling std dev), emits an event.

Events emitted:
  - COOLING_LOAD_NORMAL:   Power consumption matches what the weather predicts.
  - COOLING_LOAD_HIGH:     Power is significantly higher than weather justifies.
  - COOLING_LOAD_LOW:      Power is significantly lower than weather justifies (possible equipment failure).
  - INSUFFICIENT_DATA:     Not enough paired readings yet to compute correlation.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CorrelationEvent:
    """Output of the ambient correlation rule."""
    event_type: str                # COOLING_LOAD_NORMAL | HIGH | LOW | INSUFFICIENT_DATA
    ambient_temp_c: float          # Current ambient temperature
    actual_power_kw: float         # Actual electrical power observed
    expected_power_kw: float       # Power predicted by the linear model
    residual_kw: float             # actual - expected
    residual_sigma: float          # How many std devs away from expected
    baseline_offset: float         # The MBN offset from ambient bot
    correlation_r: float           # Pearson R between ambient and power
    window_size: int               # How many paired readings are in the window
    message: str                   # Human-readable explanation


@dataclass
class AmbientCorrelationRule:
    """Real-time ambient → cooling-load correlation detector.

    Feed it paired (ambient_temp_c, active_power_kw, baseline_offset) readings
    every poll cycle. It builds an internal model and emits events.

    Parameters:
        window_size:    Number of paired readings to keep in the rolling window.
                        Default 60 = 1 hour at 60s poll.
        sigma_threshold: Number of standard deviations for the residual to be
                        flagged as anomalous. Default 2.0.
        min_readings:   Minimum paired readings before the rule starts emitting
                        real events. Default 15 = 15 minutes warmup.
    """
    window_size: int = 60
    sigma_threshold: float = 2.0
    min_readings: int = 15

    # Internal state
    _temps: list = field(default_factory=list, repr=False)
    _powers: list = field(default_factory=list, repr=False)

    def evaluate(
        self,
        ambient_temp_c: float,
        active_power_kw: float,
        baseline_offset: float = 1.0,
    ) -> CorrelationEvent:
        """Ingest one paired reading and return a correlation event.

        Args:
            ambient_temp_c:   Current ambient temperature from the ambient bot.
            active_power_kw:  Current total active power from the electrical bot.
            baseline_offset:  The environmental_baseline_offset from the ambient bot.

        Returns:
            A CorrelationEvent describing whether the power is weather-justified.
        """
        # ── Push into rolling window ──────────────────────────────────────
        self._temps.append(ambient_temp_c)
        self._powers.append(active_power_kw)
        if len(self._temps) > self.window_size:
            self._temps.pop(0)
            self._powers.pop(0)

        n = len(self._temps)

        # ── Not enough data yet ───────────────────────────────────────────
        if n < self.min_readings:
            return CorrelationEvent(
                event_type="INSUFFICIENT_DATA",
                ambient_temp_c=ambient_temp_c,
                actual_power_kw=active_power_kw,
                expected_power_kw=0.0,
                residual_kw=0.0,
                residual_sigma=0.0,
                baseline_offset=baseline_offset,
                correlation_r=0.0,
                window_size=n,
                message=f"Warming up: {n}/{self.min_readings} readings collected.",
            )

        # ── Linear regression: expected_kw = slope * temp + intercept ─────
        slope, intercept = self._fit_linear()
        expected_kw = slope * ambient_temp_c + intercept
        residual = active_power_kw - expected_kw

        # ── Rolling standard deviation of residuals ───────────────────────
        residuals = [
            self._powers[i] - (slope * self._temps[i] + intercept)
            for i in range(n)
        ]
        std_residual = self._std(residuals)

        # Prevent division by zero (all readings identical)
        if std_residual < 0.01:
            std_residual = 0.01

        sigma = residual / std_residual

        # ── Pearson correlation coefficient ───────────────────────────────
        corr_r = self._pearson()

        # ── Classification ────────────────────────────────────────────────
        if sigma > self.sigma_threshold:
            event_type = "COOLING_LOAD_HIGH"
            message = (
                f"Power is {abs(residual):.1f} kW ABOVE what the weather predicts "
                f"({sigma:+.1f}σ). Ambient is {ambient_temp_c:.1f}°C (offset {baseline_offset:.2f}), "
                f"expected ~{expected_kw:.0f} kW but observed {active_power_kw:.0f} kW. "
                f"Possible equipment fault or unexpected load."
            )
        elif sigma < -self.sigma_threshold:
            event_type = "COOLING_LOAD_LOW"
            message = (
                f"Power is {abs(residual):.1f} kW BELOW what the weather predicts "
                f"({sigma:+.1f}σ). Ambient is {ambient_temp_c:.1f}°C (offset {baseline_offset:.2f}), "
                f"expected ~{expected_kw:.0f} kW but observed {active_power_kw:.0f} kW. "
                f"Possible compressor trip or equipment shutdown."
            )
        else:
            event_type = "COOLING_LOAD_NORMAL"
            message = (
                f"Power consumption is weather-justified. "
                f"Ambient {ambient_temp_c:.1f}°C → expected ~{expected_kw:.0f} kW, "
                f"observed {active_power_kw:.0f} kW ({sigma:+.1f}σ). Correlation R={corr_r:.3f}."
            )

        return CorrelationEvent(
            event_type=event_type,
            ambient_temp_c=ambient_temp_c,
            actual_power_kw=active_power_kw,
            expected_power_kw=round(expected_kw, 2),
            residual_kw=round(residual, 2),
            residual_sigma=round(sigma, 2),
            baseline_offset=baseline_offset,
            correlation_r=round(corr_r, 4),
            window_size=n,
            message=message,
        )

    # ── Internal Math ─────────────────────────────────────────────────────

    def _fit_linear(self) -> tuple:
        """Ordinary least squares: y = slope * x + intercept."""
        n = len(self._temps)
        sum_x = sum(self._temps)
        sum_y = sum(self._powers)
        sum_xy = sum(self._temps[i] * self._powers[i] for i in range(n))
        sum_x2 = sum(t * t for t in self._temps)

        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-10:
            # All temperatures identical — flat line
            return 0.0, sum_y / n

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        return slope, intercept

    def _pearson(self) -> float:
        """Pearson correlation coefficient between temp and power."""
        n = len(self._temps)
        if n < 2:
            return 0.0

        mean_t = sum(self._temps) / n
        mean_p = sum(self._powers) / n

        num = sum((self._temps[i] - mean_t) * (self._powers[i] - mean_p) for i in range(n))
        den_t = math.sqrt(sum((t - mean_t) ** 2 for t in self._temps))
        den_p = math.sqrt(sum((p - mean_p) ** 2 for p in self._powers))

        if den_t < 1e-10 or den_p < 1e-10:
            return 0.0
        return num / (den_t * den_p)

    @staticmethod
    def _std(values: list) -> float:
        """Population standard deviation."""
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return math.sqrt(variance)
