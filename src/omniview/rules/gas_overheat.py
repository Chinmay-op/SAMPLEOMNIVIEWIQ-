"""
Gas / Switchboard Overheating Rule — S1 "Fire Forecast"
========================================================

Deterministic thermal-rise-before-smoke detector for electrical panel
switchboards.  Consumes ``gas`` family readings from
``readings_gas`` (TSDB) or a live MQTT stream and emits a
``gas_overheat`` Layer 3 event when pre-fire conditions are detected.

Three detection tiers
---------------------
1. **CRITICAL — fire precursor** (immediate, no duration gate):
   Thermal rise ≥ 3.0 °C/min *and* (gas ≥ 25 ppm *or* particles ≥ 40).
2. **WARNING — panel overheat** (sustained ≥ 120 s):
   Panel temp ≥ 65 °C, *or* (gas ≥ 15 ppm *and* particles ≥ 20).
3. **INFO — watch** (sustained ≥ 120 s):
   Panel temp ≥ 50 °C *and* thermal rise ≥ 1.0 °C/min.

Design rationale
----------------
- **Deterministic rule, no ML** — fire-precursor physics is
  unambiguous (gas + particles + thermal rise = insulation
  degradation).  A model would add opacity to a safety-critical
  detection.
- **Sustained-duration gate** — WARNING/INFO require the condition
  to persist for ``GAS_SUSTAINED_DURATION_S`` (default 120 s) to
  filter transient spikes.  CRITICAL fires immediately — no delay
  on a fire precursor.
- **Benign-glitch filter** — ``gas_bot.py`` has a 0.1 % chance of a
  sensor glitch (1 000 ppm spike).  Single-sample spikes without a
  concurrent thermal rise are suppressed at the WARNING/INFO tier
  by the sustained gate.

Integration
-----------
Standalone today; plug-in-ready for ``detectors_live.py`` (Phase C/D)
via the same ``evaluate(sample)`` API used by the action-card
generator pipeline (OI-69 → OI-71).

Usage::

    from omniview.rules.gas_overheat import GasOverheatDetector

    detector = GasOverheatDetector()
    event = detector.evaluate({
        "device_id": "pune-comp-gas01",
        "timestamp": "2026-09-15T10:30:00+05:30",
        "sensor_type": "gas",
        "data": {
            "gas_concentration_ppm": 35.0,
            "micro_particle_index": 55.0,
            "internal_panel_temp_c": 72.0,
            "rate_of_thermal_rise_c_per_min": 4.2,
            "ambient_humidity_pct": 52.0,
            "air_quality_index": 7,
            "alert_severity_level": "CRITICAL",
        },
    })
    if event:
        print(event.severity)  # "CRITICAL"
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds (labelled PLACEHOLDER — pending Phase 0 site data) ────────

# PLACEHOLDER: calibrated against gas_bot.py physics model where
# smoldering triggers at 65 °C.  Must be validated against the real
# Schneider HeatTag datasheet during Phase 0 site data collection.

GAS_CRITICAL_RISE_C_PER_MIN: float = 3.0
"""Thermal rise rate that indicates active smoldering / insulation melt."""

GAS_CRITICAL_PPM: float = 25.0
"""Gas concentration (ppm) threshold for fire-precursor tier."""

GAS_CRITICAL_PARTICLE_IDX: float = 40.0
"""Micro-particle index threshold for fire-precursor tier."""

GAS_WARNING_TEMP_C: float = 65.0
"""Panel temperature (°C) threshold for overheat tier."""

GAS_WARNING_PPM: float = 15.0
"""Gas concentration (ppm) threshold for overheat tier (with particles)."""

GAS_WARNING_PARTICLE_IDX: float = 20.0
"""Micro-particle index threshold for overheat tier (with gas)."""

GAS_WATCH_TEMP_C: float = 50.0
"""Panel temperature (°C) threshold for watch tier."""

GAS_WATCH_RISE_C_PER_MIN: float = 1.0
"""Thermal rise rate for watch tier (requires elevated temp)."""

GAS_SUSTAINED_DURATION_S: float = 120.0
"""Minimum sustained seconds before WARNING/INFO events fire (2 min)."""

GAS_STALE_TIMEOUT_S: float = 300.0
"""If no reading arrives for this many seconds, reset device state."""


# ── Event dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class GasOverheatEvent:
    """Immutable Layer 3 event emitted when gas / overheat conditions are met.

    Follows the Layer 3 event envelope from the contract:
    ``event_id · machine_id · device_id · timestamp · source_unit ·
    event_type · severity · synthetic · payload``.
    """

    device_id: str
    timestamp: datetime
    event_type: str = "gas_overheat"
    severity: str = "WARNING"
    gas_concentration_ppm: float = 0.0
    micro_particle_index: float = 0.0
    internal_panel_temp_c: float = 0.0
    rate_of_thermal_rise_c_per_min: float = 0.0
    air_quality_index: int = 0
    condition_duration_s: float = 0.0
    tier: str = ""
    threshold_refs: dict[str, Any] = field(default_factory=dict)
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe plain dict."""
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


# ── Detector ─────────────────────────────────────────────────────────────


class GasOverheatDetector:
    """Stateful per-device gas / overheat detector.

    Tracks ``condition_since`` per ``device_id`` to implement the
    sustained-duration gate for WARNING/INFO tiers.
    """

    def __init__(self) -> None:
        # device_id → {condition_since: float|None, last_seen: float, last_tier: str}
        self._state: dict[str, dict[str, Any]] = {}

    # ── public API ───────────────────────────────────────────────────

    def evaluate(self, sample: dict[str, Any]) -> GasOverheatEvent | None:
        """Evaluate a single gas reading.

        Parameters
        ----------
        sample : dict
            A gas payload dict with ``device_id``, ``timestamp``, and
            ``data`` (matching ``gas_schema.json``).  Accepts both
            flat and nested shapes (``data.gas_concentration_ppm`` or
            top-level ``gas_concentration_ppm``).

        Returns
        -------
        GasOverheatEvent | None
            An event if conditions are met, else ``None``.
        """
        device_id = sample.get("device_id", "unknown")
        ts = self._parse_timestamp(sample)
        now_epoch = ts.timestamp()
        data = sample.get("data", sample)  # accept flat or nested

        # Extract sensor fields
        gas_ppm = float(data.get("gas_concentration_ppm", 0.0))
        particles = float(data.get("micro_particle_index", 0.0))
        panel_temp = float(data.get("internal_panel_temp_c", 0.0))
        rise_rate = float(data.get("rate_of_thermal_rise_c_per_min", 0.0))
        aqi = int(data.get("air_quality_index", 0))

        # Initialise or refresh device state
        state = self._state.get(device_id)
        if state is None:
            state = {"condition_since": None, "last_seen": now_epoch, "last_tier": ""}
            self._state[device_id] = state

        # Stale-stream reset
        if (now_epoch - state["last_seen"]) > GAS_STALE_TIMEOUT_S:
            self.reset(device_id)
            state = self._state[device_id]

        state["last_seen"] = now_epoch

        # ── Tier classification ──────────────────────────────────────
        tier, severity = self._classify(
            gas_ppm, particles, panel_temp, rise_rate,
        )

        if tier is None:
            # Condition cleared — reset sustained timer
            state["condition_since"] = None
            state["last_tier"] = ""
            return None

        # ── Sustained-duration gate ──────────────────────────────────
        if tier == "CRITICAL":
            # Fire precursor — emit immediately, no gate
            condition_duration = 0.0
        else:
            # WARNING / INFO — require sustained duration
            if state["condition_since"] is None or state["last_tier"] != tier:
                # New condition or tier changed — start timer
                state["condition_since"] = now_epoch
                state["last_tier"] = tier
                return None
            condition_duration = now_epoch - state["condition_since"]
            if condition_duration < GAS_SUSTAINED_DURATION_S:
                return None

        state["last_tier"] = tier

        threshold_refs = self._build_threshold_refs(tier)

        event = GasOverheatEvent(
            device_id=device_id,
            timestamp=ts,
            severity=severity,
            gas_concentration_ppm=gas_ppm,
            micro_particle_index=particles,
            internal_panel_temp_c=panel_temp,
            rate_of_thermal_rise_c_per_min=rise_rate,
            air_quality_index=aqi,
            condition_duration_s=condition_duration,
            tier=tier,
            threshold_refs=threshold_refs,
            synthetic=bool(sample.get("synthetic", data.get("synthetic", True))),
        )

        logger.info(
            "gas_overheat %s on %s — %s (%.1f ppm, %.0f particles, %.1f°C, "
            "%.2f°C/min, sustained %.0fs)",
            severity, device_id, tier,
            gas_ppm, particles, panel_temp, rise_rate, condition_duration,
        )

        return event

    def reset(self, device_id: str) -> None:
        """Reset tracked state for a device (e.g. stream went stale)."""
        self._state[device_id] = {
            "condition_since": None,
            "last_seen": 0.0,
            "last_tier": "",
        }

    # ── internals ────────────────────────────────────────────────────

    @staticmethod
    def _classify(
        gas_ppm: float,
        particles: float,
        panel_temp: float,
        rise_rate: float,
    ) -> tuple[str | None, str]:
        """Return ``(tier, severity)`` or ``(None, "")`` if normal."""

        # Tier 1 — CRITICAL: fire precursor (immediate)
        if rise_rate >= GAS_CRITICAL_RISE_C_PER_MIN and (
            gas_ppm >= GAS_CRITICAL_PPM or particles >= GAS_CRITICAL_PARTICLE_IDX
        ):
            return "CRITICAL", "CRITICAL"

        # Tier 2 — WARNING: panel overheat (sustained)
        if panel_temp >= GAS_WARNING_TEMP_C:
            return "WARNING_TEMP", "WARNING"
        if gas_ppm >= GAS_WARNING_PPM and particles >= GAS_WARNING_PARTICLE_IDX:
            return "WARNING_GAS_PARTICLE", "WARNING"

        # Tier 3 — INFO: watch (sustained)
        if panel_temp >= GAS_WATCH_TEMP_C and rise_rate >= GAS_WATCH_RISE_C_PER_MIN:
            return "WATCH", "INFO"

        return None, ""

    @staticmethod
    def _build_threshold_refs(tier: str) -> dict[str, Any]:
        """Return which thresholds triggered for this tier."""
        refs: dict[str, Any] = {"tier": tier, "placeholder": True}
        if tier == "CRITICAL":
            refs["rise_c_per_min_threshold"] = GAS_CRITICAL_RISE_C_PER_MIN
            refs["gas_ppm_threshold"] = GAS_CRITICAL_PPM
            refs["particle_idx_threshold"] = GAS_CRITICAL_PARTICLE_IDX
        elif tier == "WARNING_TEMP":
            refs["panel_temp_c_threshold"] = GAS_WARNING_TEMP_C
        elif tier == "WARNING_GAS_PARTICLE":
            refs["gas_ppm_threshold"] = GAS_WARNING_PPM
            refs["particle_idx_threshold"] = GAS_WARNING_PARTICLE_IDX
        elif tier == "WATCH":
            refs["panel_temp_c_threshold"] = GAS_WATCH_TEMP_C
            refs["rise_c_per_min_threshold"] = GAS_WATCH_RISE_C_PER_MIN
        return refs

    @staticmethod
    def _parse_timestamp(sample: dict[str, Any]) -> datetime:
        """Extract a timezone-aware datetime from the sample."""
        raw = sample.get("timestamp")
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw
        if isinstance(raw, str):
            # Handle trailing 'Z'
            cleaned = raw.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                pass
        # Fallback: now
        return datetime.now(timezone.utc)
