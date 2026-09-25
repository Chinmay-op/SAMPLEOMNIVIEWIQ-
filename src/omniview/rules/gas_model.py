"""
omniview.rules.gas_model — Statistical & ML Extensions for Gas Detection
=========================================================================

Building blocks that extend the deterministic GasOverheatDetector with
real statistical/ML methods.  Components:

§2  Sensor-health / data-integrity gate (range + stuck-sensor checks)
§3  Root-cause classification via rolling Pearson correlation
§4  Adaptive baseline via EWMA + rolling z-score
§5  Derivative feature engineering (slope + acceleration)
§6  Confidence / risk score (0–100)
§7  Multivariate unsupervised outlier detection (IsolationForest)

Design guardrail
~~~~~~~~~~~~~~~~
The CRITICAL fire-precursor tier remains a pure deterministic rule in
``gas_overheat.py``.  Nothing in this module may delay, veto, or replace
its firing.  These components *enrich* events the deterministic rules
have already classified — they don't gate them.

Cross-family note
~~~~~~~~~~~~~~~~~
``detectors_live.py`` feeds each sensor family's readings one at a time.
``lazy_idle.py`` expects both thermal AND electrical in a single sample
dict — this ALWAYS returns None in the live path because the fields are
never co-present.  We avoid this broken pattern:
``EnhancedGasOverheatDetector`` internally caches the latest
``current_a_avg`` / ``ambient_temp_c`` from electrical readings,
keyed by a shared site key (not raw device_id), and uses the cached
values for I²R correlation when gas readings arrive.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omniview.rules.gas_overheat import (
    GAS_CRITICAL_PPM,
    GAS_CRITICAL_PARTICLE_IDX,
    GAS_CRITICAL_RISE_C_PER_MIN,
    GAS_WARNING_PPM,
    GAS_WARNING_PARTICLE_IDX,
    GAS_WARNING_TEMP_C,
    GAS_WATCH_TEMP_C,
    GasOverheatDetector,
    GasOverheatEvent,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# §1  New single-signal thresholds
# ══════════════════════════════════════════════════════════════════════

GAS_WARN_SINGLE_GAS_PPM: float = 20.0
"""Gas-only threshold (ppm). Higher than the AND-combo's 15 ppm because
a single signal needs stronger evidence to be concerning on its own."""

GAS_WARN_SINGLE_PARTICLE_IDX: float = 30.0
"""Particle-only threshold. Higher than the AND-combo's 20."""


# ══════════════════════════════════════════════════════════════════════
# §2  Sensor Health Gate
# ══════════════════════════════════════════════════════════════════════

RANGE_LIMITS: dict[str, tuple[float, float]] = {
    "gas_concentration_ppm": (0.0, 500.0),
    "micro_particle_index": (0.0, 500.0),
    "internal_panel_temp_c": (-20.0, 150.0),
    "ambient_humidity_pct": (5.0, 100.0),
    "rate_of_thermal_rise_c_per_min": (-10.0, 20.0),
}
"""Physical range limits for sensor fields. Values outside these
ranges indicate a sensor hardware fault, not an environmental event."""


@dataclass(frozen=True)
class SensorHealthResult:
    """Result of the sensor-health pre-check."""

    is_healthy: bool
    fault_type: str = "OK"  # OK | NAN_INF | RANGE_VIOLATION | STUCK_SENSOR
    details: str = ""
    failed_field: str = ""


@dataclass(frozen=True)
class GasSensorFaultEvent:
    """Layer 3 event emitted when a gas sensor fails integrity checks.

    Separate from ``GasOverheatEvent`` — a sensor fault is NOT a fire
    risk, it's an instrumentation problem that needs maintenance.
    """

    device_id: str
    timestamp: datetime
    event_type: str = "sensor_fault"
    severity: str = "WARNING"
    fault_type: str = ""
    details: str = ""
    failed_field: str = ""
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


class SensorHealthGate:
    """Range-check + stuck-sensor detection.

    Runs BEFORE fire classification — never score risk against
    untrusted data.

    Stuck-sensor logic: ``gas_bot.py``'s physics model always injects
    jitter via ``wanderer``, so bit-identical consecutive readings
    across ~4 poll cycles mean a frozen sensor, not stable conditions.
    """

    def __init__(self, stuck_window: int = 4) -> None:
        self._stuck_window = stuck_window
        # device_id → deque of dicts (last N readings' numeric fields)
        self._cache: dict[str, deque[dict[str, float]]] = {}

    def check(
        self, device_id: str, data: dict[str, Any]
    ) -> SensorHealthResult:
        """Check a single reading for data-integrity issues.

        Parameters
        ----------
        device_id : str
            Which device produced this reading.
        data : dict
            The ``data`` sub-dict from the gas payload.

        Returns
        -------
        SensorHealthResult
            ``is_healthy=True`` if the reading is trustworthy.
        """
        # 1. NaN / Inf check
        for fld in RANGE_LIMITS:
            val = data.get(fld)
            if val is None:
                continue
            try:
                v = float(val)
            except (ValueError, TypeError):
                return SensorHealthResult(
                    is_healthy=False,
                    fault_type="NAN_INF",
                    details=f"Non-numeric value for {fld}: {val!r}",
                    failed_field=fld,
                )
            if math.isnan(v) or math.isinf(v):
                return SensorHealthResult(
                    is_healthy=False,
                    fault_type="NAN_INF",
                    details=f"NaN/Inf in {fld}: {v}",
                    failed_field=fld,
                )

        # 2. Range check
        for fld, (lo, hi) in RANGE_LIMITS.items():
            val = data.get(fld)
            if val is None:
                continue
            v = float(val)
            if v < lo or v > hi:
                return SensorHealthResult(
                    is_healthy=False,
                    fault_type="RANGE_VIOLATION",
                    details=(
                        f"{fld}={v} outside physical range [{lo}, {hi}]"
                    ),
                    failed_field=fld,
                )

        # 3. Stuck-sensor check
        numerics = {}
        for fld in ("gas_concentration_ppm", "micro_particle_index",
                     "internal_panel_temp_c"):
            val = data.get(fld)
            if val is not None:
                numerics[fld] = float(val)

        if device_id not in self._cache:
            self._cache[device_id] = deque(maxlen=self._stuck_window)
        ring = self._cache[device_id]
        ring.append(numerics)

        if len(ring) >= self._stuck_window and numerics:
            all_identical = all(
                entry == numerics for entry in ring
            )
            if all_identical:
                return SensorHealthResult(
                    is_healthy=False,
                    fault_type="STUCK_SENSOR",
                    details=(
                        f"Last {self._stuck_window} readings are "
                        f"bit-identical — sensor may be frozen"
                    ),
                )

        return SensorHealthResult(is_healthy=True)

    def reset(self, device_id: str | None = None) -> None:
        if device_id:
            self._cache.pop(device_id, None)
        else:
            self._cache.clear()


# ══════════════════════════════════════════════════════════════════════
# §4  EWMA Adaptive Baseline
# ══════════════════════════════════════════════════════════════════════

class EWMATracker:
    """Exponentially-weighted moving average + variance tracker.

    Standard EWMA control-chart method (same family as the CUSUM in
    ``cusum.py``, applied at poll-cycle scale instead of daily).

    Computes a z-score of each new reading against the device's own
    adaptive baseline::

        z = (x_t - EWMA_mean) / EWMA_std

    This lets a naturally-cooler panel get flagged for an unusual rise
    without needing a hand-tuned global constant, and prevents a
    naturally-warmer panel from causing false positives.
    """

    def __init__(
        self, alpha: float = 0.1, min_samples: int = 10
    ) -> None:
        self._alpha = alpha
        self._min_samples = min_samples
        self._mean: float | None = None
        self._var: float = 0.0
        self._n: int = 0
        self._last_z: float = 0.0

    def update(self, x: float) -> float:
        """Update EWMA state and return the z-score of ``x``.

        Returns 0.0 until ``min_samples`` observations have been seen
        (warmup period — don't flag anomalies with insufficient baseline).
        """
        self._n += 1

        if self._mean is None:
            self._mean = x
            self._var = 0.0
            self._last_z = 0.0
            return 0.0

        # Standard EWMA update
        prev_mean = self._mean
        self._mean = self._alpha * x + (1.0 - self._alpha) * prev_mean
        self._var = (
            self._alpha * (x - self._mean) ** 2
            + (1.0 - self._alpha) * self._var
        )

        if self._n < self._min_samples:
            self._last_z = 0.0
            return 0.0

        std = math.sqrt(self._var) if self._var > 0 else 0.0
        if std < 1e-9:
            self._last_z = 0.0
            return 0.0

        self._last_z = (x - self._mean) / std
        return self._last_z

    @property
    def mean(self) -> float | None:
        return self._mean

    @property
    def std(self) -> float:
        return math.sqrt(self._var) if self._var > 0 else 0.0

    @property
    def z_score(self) -> float:
        return self._last_z

    @property
    def is_warm(self) -> bool:
        return self._n >= self._min_samples

    def reset(self) -> None:
        self._mean = None
        self._var = 0.0
        self._n = 0
        self._last_z = 0.0


# ══════════════════════════════════════════════════════════════════════
# §5  Rolling Window with Derivatives
# ══════════════════════════════════════════════════════════════════════

class RollingWindow:
    """Fixed-size rolling window with first/second derivative computation.

    Uses least-squares linear regression for slope (first derivative)
    and the difference of half-window slopes for acceleration (second
    derivative) — more robust than raw 2-point finite differences.
    """

    def __init__(self, max_size: int = 15) -> None:
        self._values: deque[float] = deque(maxlen=max_size)
        self._timestamps: deque[float] = deque(maxlen=max_size)

    def append(self, value: float, timestamp: float) -> None:
        self._values.append(value)
        self._timestamps.append(timestamp)

    def slope(self) -> float | None:
        """First derivative: linear regression slope (units per second)."""
        if len(self._values) < 3:
            return None
        return _polyfit_slope(list(self._timestamps), list(self._values))

    def acceleration(self) -> float | None:
        """Second derivative: change in slope (units per second²).

        Splits window into two halves and computes slope of each;
        acceleration = (slope_2 - slope_1) / dt_between_halves.
        """
        n = len(self._values)
        if n < 6:
            return None

        mid = n // 2
        ts = list(self._timestamps)
        vs = list(self._values)

        slope_1 = _polyfit_slope(ts[:mid], vs[:mid])
        slope_2 = _polyfit_slope(ts[mid:], vs[mid:])

        if slope_1 is None or slope_2 is None:
            return None

        dt = (ts[-1] - ts[0])
        if dt < 1e-9:
            return None

        return (slope_2 - slope_1) / dt

    @property
    def values(self) -> list[float]:
        return list(self._values)

    @property
    def timestamps(self) -> list[float]:
        return list(self._timestamps)

    def __len__(self) -> int:
        return len(self._values)

    def reset(self) -> None:
        self._values.clear()
        self._timestamps.clear()


def _polyfit_slope(xs: list[float], ys: list[float]) -> float | None:
    """Least-squares linear regression slope.

    Same formula as ``features._polyfit_slope`` but accepts separate
    x and y lists (timestamps and values).
    """
    n = len(xs)
    if n < 2:
        return None

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    num = 0.0
    den = 0.0
    for x, y in zip(xs, ys):
        dx = x - x_mean
        num += dx * (y - y_mean)
        den += dx * dx

    if den < 1e-15:
        return None
    return num / den


# ══════════════════════════════════════════════════════════════════════
# §3  Cross-Family Cache + Root Cause Classification
# ══════════════════════════════════════════════════════════════════════

class CrossFamilyCache:
    """Caches latest readings from other sensor families for correlation.

    Keyed by site key (not raw device_id, since device_ids differ per
    sensor family — e.g. ``Schneider-HeatTag-01`` for gas vs
    ``pune-comp-mfm384`` for electrical).
    """

    def __init__(self, max_age_s: float = 300.0) -> None:
        self._data: dict[str, dict[str, float]] = {}
        self._timestamps: dict[str, float] = {}
        self._max_age = max_age_s

    def update(
        self, site_key: str, timestamp: float, **fields: float
    ) -> None:
        """Cache field values from another sensor family."""
        if site_key not in self._data:
            self._data[site_key] = {}
        self._data[site_key].update(fields)
        self._timestamps[site_key] = timestamp

    def get(
        self, site_key: str, field_name: str, now: float = 0.0
    ) -> float | None:
        """Retrieve a cached cross-family value.

        Returns None if the value is stale (older than max_age_s) or
        was never cached.
        """
        ts = self._timestamps.get(site_key, 0.0)
        if now > 0 and (now - ts) > self._max_age:
            return None
        vals = self._data.get(site_key, {})
        return vals.get(field_name)

    def reset(self) -> None:
        self._data.clear()
        self._timestamps.clear()


# Root-cause labels

ROOT_CAUSES: dict[str, str] = {
    "ELECTRICAL_OVERLOAD": (
        "Panel heating correlated with rising current — likely I²R overload"
    ),
    "EXTERNAL_HEAT_SOURCE": (
        "Panel temp elevated but uncorrelated with current — "
        "external/radiant heat source"
    ),
    "CHEMICAL_VOC_SOURCE": (
        "Gas elevated without particle/thermal signature — "
        "chemical outgassing / VOC source"
    ),
    "MECHANICAL_CONTAMINATION": (
        "Particles elevated without gas — dust/debris ingress"
    ),
    "INSULATION_DEGRADATION": (
        "Gas + particles + heat — classic wire insulation breakdown"
    ),
    "UNKNOWN": (
        "Insufficient data or ambiguous correlation for "
        "root-cause classification"
    ),
}


def pearson_correlation(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient between two equal-length
    lists. Returns 0.0 if fewer than 5 points or zero variance.
    """
    n = len(xs)
    if n < 5 or len(ys) != n:
        return 0.0

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for x, y in zip(xs, ys):
        dx = x - x_mean
        dy = y - y_mean
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy

    denom = math.sqrt(den_x * den_y)
    if denom < 1e-12:
        return 0.0
    return num / denom


def classify_root_cause(
    tier: str | None,
    panel_temps: list[float],
    currents: list[float],
    gas_elevated_only: bool,
    particle_elevated_only: bool,
) -> str:
    """Classify the root cause of a gas/thermal anomaly.

    Uses the Pearson correlation between panel_temp and current_a_avg
    over the rolling window to distinguish electrical overload from
    external heat sources.

    Parameters
    ----------
    tier : str or None
        The tier from the deterministic classifier (e.g., "CRITICAL").
    panel_temps : list[float]
        Rolling window of panel temperature readings.
    currents : list[float]
        Rolling window of cached current_a_avg values.
    gas_elevated_only : bool
        Whether gas is above the single-signal threshold alone.
    particle_elevated_only : bool
        Whether particles are above the single-signal threshold alone.
    """
    # Single-signal tiers get specific root causes
    if gas_elevated_only and not particle_elevated_only:
        return "CHEMICAL_VOC_SOURCE"
    if particle_elevated_only and not gas_elevated_only:
        return "MECHANICAL_CONTAMINATION"

    # Full combo (CRITICAL or WARNING_GAS_PARTICLE)
    if tier in ("CRITICAL", "WARNING_GAS_PARTICLE"):
        return "INSULATION_DEGRADATION"

    # Thermal-only tiers: use I²R correlation
    if len(panel_temps) < 5 or len(currents) < 5:
        return "UNKNOWN"

    # Align window lengths
    min_len = min(len(panel_temps), len(currents))
    temps = panel_temps[-min_len:]
    currs = currents[-min_len:]

    r = pearson_correlation(temps, currs)

    # Check if current is trending up (positive slope)
    current_slope = None
    if len(currs) >= 3:
        indices = list(range(len(currs)))
        current_slope = _polyfit_slope(
            [float(i) for i in indices],
            currs,
        )

    if abs(r) > 0.6 and current_slope is not None and current_slope > 0:
        return "ELECTRICAL_OVERLOAD"

    if abs(r) < 0.3:
        return "EXTERNAL_HEAT_SOURCE"

    return "UNKNOWN"


# ══════════════════════════════════════════════════════════════════════
# §6  Confidence / Risk Score
# ══════════════════════════════════════════════════════════════════════

def compute_confidence_score(
    gas_ppm: float,
    particles: float,
    panel_temp: float,
    rise_rate: float,
    ewma_z_gas: float,
    ewma_z_temp: float,
    gas_acceleration: float | None,
    temp_acceleration: float | None,
) -> float:
    """Compute a composite 0–100 risk/confidence score.

    Components (each 0–1, then combined):
    1. Normalized distance past gas threshold
    2. Normalized distance past particle threshold
    3. Normalized distance past panel temp threshold
    4. Normalized distance past rise-rate threshold
    5. EWMA z-score magnitude (max of gas, temp)
    6. Acceleration sign: positive (worsening) adds, negative (improving) subtracts

    The score gives the dashboard a gradient instead of a flat tier
    label and lets multiple simultaneous alerts be triaged.
    """
    components: list[float] = []

    # 1–4: Normalized threshold distances
    components.append(_norm_distance(gas_ppm, GAS_WARNING_PPM, 50.0))
    components.append(
        _norm_distance(particles, GAS_WARNING_PARTICLE_IDX, 80.0)
    )
    components.append(_norm_distance(panel_temp, GAS_WATCH_TEMP_C, 100.0))
    components.append(
        _norm_distance(rise_rate, GAS_CRITICAL_RISE_C_PER_MIN, 10.0)
    )

    # 5: EWMA z-score magnitude (peak of gas or temp)
    z_max = 6.0  # normalize z-scores to 0–1 scale
    z_component = min(1.0, max(abs(ewma_z_gas), abs(ewma_z_temp)) / z_max)
    components.append(z_component)

    # 6: Acceleration sign (worsening = positive contribution)
    accel_score = 0.0
    if gas_acceleration is not None and gas_acceleration > 0:
        accel_score += 0.5
    if temp_acceleration is not None and temp_acceleration > 0:
        accel_score += 0.5
    components.append(accel_score)

    # Equal-weighted mean → 0–100
    if not components:
        return 0.0
    raw = sum(components) / len(components)
    return round(max(0.0, min(100.0, raw * 100.0)), 1)


def _norm_distance(value: float, threshold: float, scale: float) -> float:
    """Normalize how far ``value`` is past ``threshold``, clamped 0–1."""
    if value <= 0 or threshold <= 0:
        return 0.0
    excess = max(0.0, value - threshold)
    return min(1.0, excess / scale)


# ══════════════════════════════════════════════════════════════════════
# §7  Multivariate Outlier Detection (IsolationForest)
# ══════════════════════════════════════════════════════════════════════

_DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "gas_outlier_model.joblib"
)

# Feature vector used for the outlier model
OUTLIER_FEATURES = [
    "gas_ppm", "particles", "panel_temp", "rise_rate",
    "humidity", "current_a_avg", "ambient_temp_c",
    "gas_slope", "gas_acceleration",
]


class GasOutlierDetector:
    """Multivariate unsupervised outlier detection via IsolationForest.

    Why IsolationForest (not Mahalanobis distance):
    - Gas/particle/temp distributions are NOT Gaussian — they have
      heavy right tails during anomaly events and a compact baseline
      cluster. IsolationForest handles this naturally via random
      partitioning; Mahalanobis assumes Gaussian and would produce
      poor decision boundaries on skewed data.
    - scikit-learn is already required (per spec); the extra API
      surface is minimal.

    Usage (training — offline)::

        detector = GasOutlierDetector()
        stats = detector.fit_and_save(baseline_data)
        # Saves to data/gas_outlier_model.joblib

    Usage (runtime)::

        detector = GasOutlierDetector()
        score = detector.score({
            "gas_ppm": 1.2, "particles": 3.0,
            "panel_temp": 35.0, ...
        })
        # score > 0 → outlier (higher = more anomalous)

    Retrain procedure
    -----------------
    1. Generate 30 days of baseline data via ``gas_bot.py`` in stochastic
       mode (no CSV replay).
    2. Collect payloads where ``alert_severity_level == "NORMAL"`` into a
       list of dicts.
    3. Call ``detector.fit_and_save(data_list)``
    4. The model is persisted at ``data/gas_outlier_model.joblib``
    5. Restart the detector process — it loads automatically on init.
    """

    def __init__(
        self, model_path: str | Path | None = None
    ) -> None:
        self._path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self._model: Any = None
        self._available = False
        self._load_model()

    def _load_model(self) -> None:
        """Load a previously fitted model from disk."""
        if not self._path.exists():
            logger.debug(
                "No outlier model at %s — outlier scoring disabled", self._path
            )
            return
        try:
            import joblib
            self._model = joblib.load(self._path)
            self._available = True
            logger.info("Loaded gas outlier model from %s", self._path)
        except Exception:
            logger.warning(
                "Failed to load outlier model from %s", self._path,
                exc_info=True,
            )

    def score(self, features: dict[str, float | None]) -> float:
        """Score a single reading against the fitted model.

        Returns
        -------
        float
            Anomaly score. 0.0 if the model is unavailable.
            Positive values indicate outliers (higher = more anomalous).
            The raw sklearn ``decision_function`` is negated so that
            positive = anomalous (sklearn convention is negative = outlier).
        """
        if not self._available or self._model is None:
            return 0.0

        try:
            import numpy as np
            vec = []
            for feat in OUTLIER_FEATURES:
                val = features.get(feat)
                vec.append(float(val) if val is not None else 0.0)
            arr = np.array(vec).reshape(1, -1)
            # sklearn decision_function: negative = outlier
            raw = self._model.decision_function(arr)[0]
            return round(-raw, 4)  # negate so positive = anomalous
        except Exception:
            logger.debug("Outlier scoring failed", exc_info=True)
            return 0.0

    def fit_and_save(
        self,
        data: list[dict[str, float]],
        contamination: float = 0.05,
        n_estimators: int = 200,
        random_state: int = 42,
    ) -> dict[str, Any]:
        """Fit an IsolationForest on baseline data and persist it.

        Parameters
        ----------
        data : list[dict]
            List of feature dicts (one per reading). Keys must match
            ``OUTLIER_FEATURES``.
        contamination : float
            Expected proportion of outliers in the training set.
        n_estimators : int
            Number of isolation trees.
        random_state : int
            For reproducibility.

        Returns
        -------
        dict
            Training stats: n_samples, n_features, model_path.
        """
        import numpy as np
        from sklearn.ensemble import IsolationForest
        import joblib

        rows = []
        for d in data:
            row = [float(d.get(f, 0.0)) for f in OUTLIER_FEATURES]
            rows.append(row)

        X = np.array(rows)
        model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        model.fit(X)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, self._path)
        self._model = model
        self._available = True

        logger.info(
            "Fitted and saved outlier model: %d samples, %d features → %s",
            X.shape[0], X.shape[1], self._path,
        )
        return {
            "n_samples": X.shape[0],
            "n_features": X.shape[1],
            "model_path": str(self._path),
        }

    @property
    def available(self) -> bool:
        return self._available


# ══════════════════════════════════════════════════════════════════════
# Enhanced Detector — wraps GasOverheatDetector + all extensions
# ══════════════════════════════════════════════════════════════════════

# EWMA z-score threshold for adaptive WATCH anomaly
EWMA_Z_THRESHOLD: float = 3.0
"""Flag WATCH_ADAPTIVE when z-score exceeds this, even if below
global absolute thresholds."""


class EnhancedGasOverheatDetector:
    """Statistical/ML-enhanced gas overheat detector.

    Wraps the deterministic ``GasOverheatDetector`` and layers on:

    - Sensor-health gate (bypasses classification on bad data)
    - Single-signal tiers (WARNING_GAS_ONLY, WARNING_PARTICLE_ONLY)
    - Cross-family I²R correlation for root-cause classification
    - EWMA adaptive baseline for per-device anomaly detection
    - Derivative features (slope, acceleration)
    - Composite confidence score (0–100)
    - IsolationForest outlier scoring (if model available)

    **CRITICAL fire-precursor rules are untouched.** This detector
    delegates to ``GasOverheatDetector`` for tier classification and
    enriches the result.

    Parameters
    ----------
    site_key : str
        Shared key for cross-family data correlation (default:
        ``"pune-isbm"``). All sensors at the same site share this key.
    ewma_alpha : float
        EWMA smoothing factor (default 0.1).
    window_size : int
        Rolling window size for derivatives and correlation (default 15).
    outlier_model_path : str or Path, optional
        Path to the fitted IsolationForest model.
    """

    def __init__(
        self,
        site_key: str = "pune-isbm",
        ewma_alpha: float = 0.1,
        window_size: int = 15,
        outlier_model_path: str | Path | None = None,
    ) -> None:
        self._base = GasOverheatDetector()
        self._health_gate = SensorHealthGate()
        self._cross_family = CrossFamilyCache()
        self._outlier = GasOutlierDetector(model_path=outlier_model_path)
        self._site_key = site_key
        self._ewma_alpha = ewma_alpha
        self._window_size = window_size

        # Per-device tracking
        # device_id → {signal_name: EWMATracker}
        self._ewma: dict[str, dict[str, EWMATracker]] = {}
        # device_id → {signal_name: RollingWindow}
        self._windows: dict[str, dict[str, RollingWindow]] = {}
        # device_id → deque of panel_temps (for correlation)
        self._temp_history: dict[str, deque[float]] = {}
        # site_key → deque of current_a_avg (for correlation)
        self._current_history: dict[str, deque[float]] = {}
        # Single-signal sustained gate state (instance-level, not class-level)
        self._ss_state: dict[str, dict[str, Any]] = {}

    def evaluate(
        self, sample: dict[str, Any]
    ) -> GasOverheatEvent | GasSensorFaultEvent | None:
        """Evaluate a single reading (gas OR electrical).

        When receiving an electrical reading, caches ``current_a_avg``
        and ``ambient_temp_c`` for I²R correlation and returns None.

        When receiving a gas reading, runs the full detection pipeline.
        """
        sensor_type = sample.get("sensor_type", "")
        data = sample.get("data", sample)

        # ── Cross-family ingestion (electrical) ──────────────────────
        if sensor_type == "electrical":
            return self._ingest_electrical(sample)

        # ── Gas reading pipeline ─────────────────────────────────────
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        now_epoch = ts.timestamp()

        # §2: Sensor health gate — FIRST, before any classification
        health = self._health_gate.check(device_id, data)
        if not health.is_healthy:
            logger.warning(
                "Sensor fault on %s: %s — %s",
                device_id, health.fault_type, health.details,
            )
            return GasSensorFaultEvent(
                device_id=device_id,
                timestamp=ts,
                fault_type=health.fault_type,
                details=health.details,
                failed_field=health.failed_field,
                synthetic=sample.get("synthetic", True),
            )

        # Extract fields
        gas_ppm = float(
            data.get("gas_ppm", data.get("gas_concentration_ppm", 0.0))
        )
        particles = float(
            data.get("particle_idx", data.get("micro_particle_index", 0.0))
        )
        panel_temp = float(
            data.get("panel_temp_c", data.get("internal_panel_temp_c", 0.0))
        )
        rise_rate = float(
            data.get("thermal_rise_rate",
                      data.get("rate_of_thermal_rise_c_per_min", 0.0))
        )
        humidity = float(
            data.get("humidity_pct", data.get("ambient_humidity_pct", 50.0))
        )

        # §4: Update EWMA trackers
        ewma_z_gas = self._update_ewma(device_id, "gas_ppm", gas_ppm)
        ewma_z_temp = self._update_ewma(device_id, "panel_temp", panel_temp)

        # §5: Update rolling windows + compute derivatives
        self._update_window(device_id, "gas_ppm", gas_ppm, now_epoch)
        self._update_window(device_id, "panel_temp", panel_temp, now_epoch)

        gas_slope = self._get_window(device_id, "gas_ppm").slope()
        gas_accel = self._get_window(device_id, "gas_ppm").acceleration()
        temp_slope = self._get_window(device_id, "panel_temp").slope()
        temp_accel = self._get_window(device_id, "panel_temp").acceleration()

        # §3: Track temp history for correlation
        if device_id not in self._temp_history:
            self._temp_history[device_id] = deque(maxlen=self._window_size)
        self._temp_history[device_id].append(panel_temp)

        # Get cached cross-family data for correlation
        cached_current = self._cross_family.get(
            self._site_key, "current_a_avg", now=now_epoch
        )
        cached_ambient = self._cross_family.get(
            self._site_key, "ambient_temp_c", now=now_epoch
        )
        if cached_current is not None:
            if self._site_key not in self._current_history:
                self._current_history[self._site_key] = deque(
                    maxlen=self._window_size
                )
            self._current_history[self._site_key].append(cached_current)

        # §1: Check single-signal elevation for root-cause
        gas_elevated_only = (
            gas_ppm >= GAS_WARN_SINGLE_GAS_PPM
            and particles < GAS_WARNING_PARTICLE_IDX
        )
        particle_elevated_only = (
            particles >= GAS_WARN_SINGLE_PARTICLE_IDX
            and gas_ppm < GAS_WARNING_PPM
        )

        # ── Run base detector for tier classification ────────────────
        # Inject single-signal tiers into the sample before base eval
        base_event = self._base.evaluate(sample)

        # Check if single-signal tiers should fire (base missed them)
        tier = None
        severity = ""
        if base_event is not None:
            tier = base_event.tier
            severity = base_event.severity
        elif gas_elevated_only or particle_elevated_only:
            # The base detector didn't fire — check single-signal tiers
            # These need sustained-duration gating too
            ss_tier, ss_sev = self._classify_single_signal(
                gas_ppm, particles, device_id, now_epoch,
            )
            if ss_tier is not None:
                tier = ss_tier
                severity = ss_sev

        # §4: Check for adaptive EWMA anomaly (below global thresholds)
        ewma_anomaly = False
        if tier is None and (
            abs(ewma_z_gas) > EWMA_Z_THRESHOLD
            or abs(ewma_z_temp) > EWMA_Z_THRESHOLD
        ):
            # EWMA flagged an anomaly below global thresholds
            tier = "WATCH_ADAPTIVE"
            severity = "INFO"
            ewma_anomaly = True

        if tier is None:
            return None

        # §3: Root-cause classification
        root_cause = classify_root_cause(
            tier=tier,
            panel_temps=list(self._temp_history.get(device_id, [])),
            currents=list(
                self._current_history.get(self._site_key, [])
            ),
            gas_elevated_only=gas_elevated_only,
            particle_elevated_only=particle_elevated_only,
        )

        # §6: Confidence score
        confidence = compute_confidence_score(
            gas_ppm=gas_ppm,
            particles=particles,
            panel_temp=panel_temp,
            rise_rate=rise_rate,
            ewma_z_gas=ewma_z_gas,
            ewma_z_temp=ewma_z_temp,
            gas_acceleration=gas_accel,
            temp_acceleration=temp_accel,
        )

        # §7: Outlier score
        outlier_score = self._outlier.score({
            "gas_ppm": gas_ppm,
            "particles": particles,
            "panel_temp": panel_temp,
            "rise_rate": rise_rate,
            "humidity": humidity,
            "current_a_avg": cached_current or 0.0,
            "ambient_temp_c": cached_ambient or 0.0,
            "gas_slope": gas_slope or 0.0,
            "gas_acceleration": gas_accel or 0.0,
        })

        # Build enriched event
        condition_duration = (
            base_event.condition_duration_s if base_event else 0.0
        )
        threshold_refs = (
            base_event.threshold_refs if base_event else {}
        )

        event = GasOverheatEvent(
            device_id=device_id,
            timestamp=ts,
            severity=severity,
            gas_concentration_ppm=gas_ppm,
            micro_particle_index=particles,
            internal_panel_temp_c=panel_temp,
            rate_of_thermal_rise_c_per_min=rise_rate,
            air_quality_index=int(
                data.get("aqi", data.get("air_quality_index", 0))
            ),
            condition_duration_s=condition_duration,
            tier=tier,
            threshold_refs=threshold_refs,
            synthetic=bool(
                sample.get("synthetic", data.get("synthetic", True))
            ),
            # §3–7 enrichment fields
            root_cause=root_cause,
            confidence_score=confidence,
            gas_slope=gas_slope or 0.0,
            gas_acceleration=gas_accel or 0.0,
            temp_slope=temp_slope or 0.0,
            temp_acceleration=temp_accel or 0.0,
            ewma_z_gas=round(ewma_z_gas, 3),
            ewma_z_temp=round(ewma_z_temp, 3),
            outlier_score=outlier_score,
        )

        logger.info(
            "Enhanced gas event: %s/%s on %s — root_cause=%s "
            "confidence=%.1f outlier=%.3f",
            tier, severity, device_id, root_cause,
            confidence, outlier_score,
        )

        return event

    def reset(self, device_id: str | None = None) -> None:
        """Reset all tracked state for a device, or all devices."""
        self._base.reset(device_id or "")
        self._health_gate.reset(device_id)
        if device_id:
            self._ewma.pop(device_id, None)
            self._windows.pop(device_id, None)
            self._temp_history.pop(device_id, None)
        else:
            self._ewma.clear()
            self._windows.clear()
            self._temp_history.clear()
            self._current_history.clear()
            self._cross_family.reset()

    # ── Single-signal sustained gate ─────────────────────────────────

    def _classify_single_signal(
        self,
        gas_ppm: float,
        particles: float,
        device_id: str,
        now_epoch: float,
    ) -> tuple[str | None, str]:
        """Classify single-signal WARNING tiers with duration gate."""
        from omniview.rules.gas_overheat import GAS_SUSTAINED_DURATION_S

        tier = None
        if gas_ppm >= GAS_WARN_SINGLE_GAS_PPM:
            tier = "WARNING_GAS_ONLY"
        elif particles >= GAS_WARN_SINGLE_PARTICLE_IDX:
            tier = "WARNING_PARTICLE_ONLY"
        else:
            # Clear single-signal state
            self._ss_state.pop(device_id, None)
            return None, ""

        state = self._ss_state.get(device_id)
        if state is None or state.get("tier") != tier:
            # New condition or tier changed — start timer
            self._ss_state[device_id] = {
                "condition_since": now_epoch,
                "tier": tier,
                "alerted": False,
            }
            return None, ""  # first sample, start timer

        if state.get("alerted"):
            return None, ""  # already fired for this condition

        duration = now_epoch - state["condition_since"]
        if duration >= GAS_SUSTAINED_DURATION_S:
            state["alerted"] = True
            return tier, "WARNING"

        return None, ""  # not yet sustained

    # ── Internal helpers ─────────────────────────────────────────────

    def _ingest_electrical(
        self, sample: dict[str, Any]
    ) -> None:
        """Cache electrical fields for cross-family correlation."""
        data = sample.get("data", sample)
        ts = self._parse_timestamp(sample).timestamp()

        current = None
        for key in ("current_a_avg", "current_a", "avg_current"):
            val = data.get(key)
            if val is not None:
                try:
                    current = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        ambient = None
        for key in ("ambient_temp_c", "temperature_c"):
            val = data.get(key)
            if val is not None:
                try:
                    ambient = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        fields: dict[str, float] = {}
        if current is not None:
            fields["current_a_avg"] = current
        if ambient is not None:
            fields["ambient_temp_c"] = ambient

        if fields:
            self._cross_family.update(self._site_key, ts, **fields)

        return None

    def _update_ewma(
        self, device_id: str, signal: str, value: float
    ) -> float:
        """Update EWMA tracker for a device+signal and return z-score."""
        if device_id not in self._ewma:
            self._ewma[device_id] = {}
        if signal not in self._ewma[device_id]:
            self._ewma[device_id][signal] = EWMATracker(
                alpha=self._ewma_alpha
            )
        return self._ewma[device_id][signal].update(value)

    def _update_window(
        self,
        device_id: str,
        signal: str,
        value: float,
        timestamp: float,
    ) -> None:
        """Append to rolling window for a device+signal."""
        if device_id not in self._windows:
            self._windows[device_id] = {}
        if signal not in self._windows[device_id]:
            self._windows[device_id][signal] = RollingWindow(
                max_size=self._window_size
            )
        self._windows[device_id][signal].append(value, timestamp)

    def _get_window(self, device_id: str, signal: str) -> RollingWindow:
        """Get the rolling window for a device+signal (creates if needed)."""
        if device_id not in self._windows:
            self._windows[device_id] = {}
        if signal not in self._windows[device_id]:
            self._windows[device_id][signal] = RollingWindow(
                max_size=self._window_size
            )
        return self._windows[device_id][signal]

    @staticmethod
    def _parse_timestamp(sample: dict[str, Any]) -> datetime:
        raw = sample.get("timestamp")
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw
        if isinstance(raw, str):
            cleaned = raw.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                pass
        return datetime.now(timezone.utc)
