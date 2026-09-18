"""
omniview.predictive.priors — Equipment-Class Population Baselines
=================================================================

Loads per-equipment-class signal priors (mean, std, direction) from
``config/layer0_priors.yaml`` (OI-63). Used by the Health Index to
compute z-score deviations — "how far is this machine's trend from
what's normal for its equipment class?"

The priors are PLACEHOLDER until real site calibration. After 30+ days
of real data, recalibrate from the site's own population statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default path relative to repo root
_DEFAULT_PRIORS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "layer0_priors.yaml"
)


@dataclass(frozen=True)
class SignalPrior:
    """Baseline statistics for a single tracked signal.

    Parameters
    ----------
    name : str
        Signal field name (e.g. ``current_a_avg``).
    mean : float
        Expected baseline mean for this equipment class.
    std : float
        Expected baseline standard deviation.
    direction : str
        Direction of concern: ``"rising"``, ``"falling"``, or ``"both"``.
    description : str
        Human-readable description of what this signal measures.
    """

    name: str
    mean: float
    std: float
    direction: str = "both"
    description: str = ""

    def z_score(self, value: float) -> float:
        """Compute the z-score of a raw value against this prior.

        Returns 0.0 if std is zero (prevents division by zero).
        """
        if self.std == 0.0:
            return 0.0
        return (value - self.mean) / self.std

    def slope_z_score(self, slope: float) -> float:
        """Compute the z-score of a *slope* (rate of change).

        For slopes, the healthy baseline is 0 (no trend). We
        normalize by the prior's std so the z-score is on the
        same scale as raw-value deviations:
        a slope of ``std`` units/day is a 1-σ event.

        Returns 0.0 if std is zero.
        """
        if self.std == 0.0:
            return 0.0
        return slope / self.std

    def directional_z_score(self, slope: float) -> float:
        """Compute a direction-aware z-score for a slope value.

        Only counts deviations in the direction of concern:
        - ``"rising"``: only positive slopes count (slope > 0 → bad)
        - ``"falling"``: only negative slopes count (slope < 0 → bad)
        - ``"both"``: absolute z-score

        The baseline for slopes is always 0 (healthy = no change).

        Returns the absolute z-score in the concerning direction,
        or 0.0 if the slope is in the healthy direction.
        """
        z = self.slope_z_score(slope)

        if self.direction == "rising":
            return max(0.0, z)  # Only positive slope counts
        elif self.direction == "falling":
            return max(0.0, -z)  # Only negative slope counts
        else:
            return abs(z)


@dataclass
class EquipmentPriors:
    """All signal priors for one equipment class.

    Parameters
    ----------
    class_name : str
        Equipment class identifier (e.g. ``isbm_pet_moulding``).
    description : str
        Human-readable description.
    machines : list[str]
        Machine IDs that belong to this class.
    signals : dict[str, SignalPrior]
        Per-signal baseline statistics.
    """

    class_name: str
    description: str = ""
    machines: list[str] = field(default_factory=list)
    signals: dict[str, SignalPrior] = field(default_factory=dict)


@dataclass
class HealthIndexParams:
    """Configuration for the Health Index computation."""

    z_scale: float = 15.0
    slope_window_days: int = 7
    min_warmup_days: int = 7
    risk_tiers: dict[str, int] = field(
        default_factory=lambda: {"high": 40, "medium": 70, "low": 100}
    )


@dataclass
class CUSUMParams:
    """Configuration for the CUSUM change-point detector."""

    slack: float = 2.0
    threshold: float = 8.0
    reset_on_alert: bool = True


class PriorStore:
    """Load and resolve equipment-class priors from YAML config.

    Usage::

        store = PriorStore()  # loads default config
        priors = store.get_priors("isbm-main-feed")
        print(priors.signals["current_a_avg"].mean)

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the YAML config file. Defaults to
        ``config/layer0_priors.yaml`` at the repo root.
    """

    def __init__(self, config_path: str | Path | None = None):
        self._path = Path(config_path) if config_path else _DEFAULT_PRIORS_PATH
        self._classes: dict[str, EquipmentPriors] = {}
        self._machine_lookup: dict[str, str] = {}  # machine_id → class_name
        self._hi_params = HealthIndexParams()
        self._cusum_params = CUSUMParams()
        self._load()

    def _load(self) -> None:
        """Parse the YAML config and build the lookup structures."""
        if not self._path.exists():
            logger.warning(
                "Priors config not found at %s — using empty defaults",
                self._path,
            )
            return

        with open(self._path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        # Parse equipment classes
        for class_name, class_data in raw.get("equipment_classes", {}).items():
            signals: dict[str, SignalPrior] = {}
            for sig_name, sig_data in class_data.get("signals", {}).items():
                signals[sig_name] = SignalPrior(
                    name=sig_name,
                    mean=float(sig_data.get("mean", 0.0)),
                    std=float(sig_data.get("std", 1.0)),
                    direction=sig_data.get("direction", "both"),
                    description=sig_data.get("description", ""),
                )

            eq_priors = EquipmentPriors(
                class_name=class_name,
                description=class_data.get("description", ""),
                machines=class_data.get("machines", []),
                signals=signals,
            )
            self._classes[class_name] = eq_priors

            # Build machine → class lookup
            for machine_id in eq_priors.machines:
                self._machine_lookup[machine_id] = class_name

        # Parse HI parameters
        hi_raw = raw.get("health_index", {})
        if hi_raw:
            self._hi_params = HealthIndexParams(
                z_scale=float(hi_raw.get("z_scale", 15.0)),
                slope_window_days=int(hi_raw.get("slope_window_days", 7)),
                min_warmup_days=int(hi_raw.get("min_warmup_days", 7)),
                risk_tiers=hi_raw.get(
                    "risk_tiers", {"high": 40, "medium": 70, "low": 100}
                ),
            )

        # Parse CUSUM parameters
        cusum_raw = raw.get("cusum", {})
        if cusum_raw:
            self._cusum_params = CUSUMParams(
                slack=float(cusum_raw.get("slack", 2.0)),
                threshold=float(cusum_raw.get("threshold", 8.0)),
                reset_on_alert=cusum_raw.get("reset_on_alert", True),
            )

        logger.info(
            "Loaded %d equipment classes, %d machine mappings from %s",
            len(self._classes),
            len(self._machine_lookup),
            self._path,
        )

    @property
    def hi_params(self) -> HealthIndexParams:
        """Health Index computation parameters."""
        return self._hi_params

    @property
    def cusum_params(self) -> CUSUMParams:
        """CUSUM detector parameters."""
        return self._cusum_params

    def get_class(self, class_name: str) -> EquipmentPriors | None:
        """Look up priors by equipment class name."""
        return self._classes.get(class_name)

    def get_priors(self, machine_id: str) -> EquipmentPriors:
        """Resolve priors for a machine ID.

        Looks up the machine's equipment class; falls back to
        ``generic_industrial_motor`` if no mapping exists.
        """
        class_name = self._machine_lookup.get(machine_id)
        if class_name and class_name in self._classes:
            return self._classes[class_name]

        # Fallback
        fallback = self._classes.get("generic_industrial_motor")
        if fallback:
            logger.debug(
                "No class mapping for machine '%s' — using generic fallback",
                machine_id,
            )
            return fallback

        # Last resort: return empty priors
        logger.warning(
            "No priors found for machine '%s' and no fallback configured",
            machine_id,
        )
        return EquipmentPriors(class_name="unknown", description="No priors")

    @property
    def all_classes(self) -> dict[str, EquipmentPriors]:
        """All loaded equipment classes."""
        return dict(self._classes)

    @property
    def machine_lookup(self) -> dict[str, str]:
        """Machine ID → equipment class name mapping."""
        return dict(self._machine_lookup)
