"""
Action-Card Generator — OI-69
================================

Generates human-readable action cards from detected rule / PdM events.

An **action card** is the system's single recommendation to a specific
stakeholder.  It tells them *what* happened, *why* it matters (physically),
*what to do*, *what NOT to do*, and *what the ₹ impact is*.

**Key design principle:** action cards **never auto-actuate**.  They only
recommend — a human decides and acts (PRD §5, architecture §3.5).

Current event sources
---------------------
- **Scenario-labeled TSDB readings** (``scenario_label`` in JSONB data)
  from the OI-55 seed script or live ingest.

Future event sources (plug-in ready)
------------------------------------
- **Rule-engine events** (OI-56–61) — when Lead ships the rule engine.
- **Conflict arbitration output** (OI-60) — resolved multi-goal events.
- **PdM maintenance_risk events** (OI-62–67) — HI threshold breaches.

Usage::

    from omniview.rules.action_cards import ActionCardGenerator

    gen = ActionCardGenerator()

    # From a raw event dict (e.g., from alert feed or rule engine)
    card = gen.generate_card({
        "event_type": "md_nearmiss",
        "device_id": "pune-comp-mfm384",
        "kva": 478.5,
        "md_proximity_percent": 95.7,
        "timestamp": "2026-08-20T10:30:00+05:30",
    })

    print(card.title)               # "⚡ MD Near-Miss — Demand Approaching Contract Limit"
    print(card.recommended_action)   # "Shed non-critical load (HVAC, lighting) within ~4 min..."
    print(card.do_not)              # "Do NOT shut down compressor — backup load spike..."
    print(card.rupee_impact)        # "₹17,475 penalty risk if 500 kVA breached"
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Timezone ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


# ── ActionCard dataclass ────────────────────────────────────────────────


@dataclass(frozen=True)
class ActionCard:
    """Immutable human-readable action card from a detected condition.

    Every field is populated by the generator — nothing is left as TBD.
    The card is self-contained: a plant manager should be able to act on
    it without looking up additional context.

    Attributes
    ----------
    card_id : str
        Unique hash-based ID for deduplication and tracking.
    timestamp : datetime
        When the condition was detected.
    event_type : str
        Machine-readable event category (e.g., ``"md_nearmiss"``).
    severity : str
        ``"CRITICAL"`` | ``"WARNING"`` | ``"INFO"``.
    title : str
        One-line title with icon (e.g., "⚡ MD Near-Miss — ...").
    summary : str
        2–3 sentence human-readable explanation of what happened and why
        it matters physically.
    recommended_action : str
        Specific, actionable instruction (what to do).
    do_not : str
        Anti-action — what the operator must NOT do (prevents the most
        common wrong response).  Empty string if not applicable.
    rupee_impact : str
        Financial impact in ₹, or empty if not quantifiable yet.
    urgency_window : str
        How much time the operator has to act (e.g., "~4 min before
        billing window closes").  Empty if not time-critical.
    target_role : str
        Who should receive this card: ``"plant_manager"``,
        ``"maintenance_engineer"``, ``"operator"``, ``"finance"``.
    device_id : str
        The device that triggered this card.
    sensor_readings : dict[str, Any]
        Raw sensor values backing this card (for internal review).
    physical_rationale : str
        Engineering explanation of why this recommendation is physically
        sound — for internal reviewability per acceptance criteria.
    source_event : dict[str, Any]
        The original event dict that produced this card (audit trail).
    """

    card_id: str
    timestamp: datetime
    event_type: str
    severity: str
    title: str
    summary: str
    recommended_action: str
    do_not: str = ""
    rupee_impact: str = ""
    urgency_window: str = ""
    target_role: str = "plant_manager"
    device_id: str = ""
    sensor_readings: dict[str, Any] = field(default_factory=dict)
    physical_rationale: str = ""
    source_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (JSON-safe with string timestamps)."""
        d = asdict(self)
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


# ── Card templates ──────────────────────────────────────────────────────

# Each template is a callable that takes an event dict and returns the
# field values for an ActionCard.  This keeps the generator stateless.


def _md_nearmiss_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Template for MD (Maximum Demand) near-miss events."""
    kva = event.get("kva", 0.0)
    contract = event.get("contract_kva", 500.0)
    proximity = event.get("md_proximity_percent", 0.0)
    if proximity == 0.0 and contract > 0:
        proximity = (kva / contract) * 100

    headroom_kva = max(0, contract - kva)
    penalty_per_kva = event.get("penalty_rate", 350.0)
    # Penalty if breached: excess kVA × rate
    excess_risk = max(0, kva - contract + 20)  # project 20 kVA overshoot
    penalty_risk = excess_risk * penalty_per_kva

    return {
        "severity": "CRITICAL",
        "title": "⚡ MD Near-Miss — Demand Approaching Contract Limit",
        "summary": (
            f"Rolling 15-min kVA average has reached {kva:.0f} kVA — "
            f"{proximity:.0f}% of the {contract:.0f} kVA contract limit. "
            f"Only {headroom_kva:.0f} kVA headroom remains. If the current "
            f"trajectory holds, the billing window will lock in a breach."
        ),
        "recommended_action": (
            f"Shed non-critical load (HVAC, auxiliary lighting, non-essential "
            f"pumps) immediately. Target shedding ≥{max(20, kva - contract + 30):.0f} kVA "
            f"within the next 4 minutes to keep the 15-minute rolling "
            f"average below {contract:.0f} kVA."
        ),
        "do_not": (
            "Do NOT shut down the compressor or ISBM main drive — "
            "the sudden restart will spike inrush current and guarantee "
            "a demand overshoot worse than the current trajectory."
        ),
        "rupee_impact": f"₹{penalty_risk:,.0f} penalty risk if {contract:.0f} kVA breached",
        "urgency_window": "~4 min remaining in current 15-min billing window",
        "target_role": "plant_manager",
        "physical_rationale": (
            f"MSEDCL bills demand penalty on the peak 15-min kVA average per "
            f"billing cycle. At {kva:.0f}/{contract:.0f} kVA, the system is in "
            f"the final ~4 minutes of a billing window (minute 11+ trigger). "
            f"Load shedding now reduces the rolling average before the window "
            f"closes. Hard shutdown is counter-productive because motor inrush "
            f"current (6–8× rated) during restart will spike apparent power "
            f"beyond the contract limit."
        ),
    }


def _lazy_idle_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Template for lazy-idle (heat without work) events."""
    current = event.get("current_a_avg", 0.0)
    barrel_temp = event.get("barrel_temp_c", 0.0)
    # Try alternate thermal field names
    if barrel_temp == 0.0:
        barrel_temp = event.get("process_variable_c", 0.0)
    if barrel_temp == 0.0:
        barrel_temp = event.get("temperature_c", 0.0)
    idle_minutes = event.get("idle_duration_min", 15)

    # Energy waste: idle power × duration
    idle_kw = event.get("active_power_kw_total", 3.0)
    waste_kwh = idle_kw * (idle_minutes / 60.0)
    tariff_rate = event.get("tariff_rate_per_kwh", 8.5)  # ₹/kWh estimate
    waste_rupees = waste_kwh * tariff_rate

    return {
        "severity": "WARNING",
        "title": "🔥 Lazy Idle — Machine Drawing Power Without Producing",
        "summary": (
            f"ISBM machine has been idle for {idle_minutes} minutes "
            f"(current: {current:.1f} A) but barrel temperature is still "
            f"at {barrel_temp:.0f}°C. Energy is being wasted maintaining "
            f"thermal mass with no production output."
        ),
        "recommended_action": (
            f"Investigate production floor: if the idle state is an unplanned "
            f"gap (mold change, material wait), either resume production or "
            f"initiate controlled barrel cool-down. If changeover is expected "
            f"to last >20 min, reduce barrel heater setpoint to standby "
            f"(180°C) to cut idle energy waste."
        ),
        "do_not": (
            "Do NOT power-cycle the ISBM machine without confirming "
            "barrel temperature is below safe mold-contact threshold — "
            "thermal shock to the barrel can damage heater bands and "
            "requires 45+ min reheat."
        ),
        "rupee_impact": (
            f"₹{waste_rupees:,.0f} wasted so far "
            f"({waste_kwh:.1f} kWh × ₹{tariff_rate}/kWh)"
        ),
        "urgency_window": "",  # Not time-critical in the billing sense
        "target_role": "maintenance_engineer",
        "physical_rationale": (
            f"A machine drawing <{current:.1f} A while barrel temp remains "
            f">{barrel_temp:.0f}°C indicates idle-with-heaters-on. The "
            f"heater bands maintain thermal mass (~15 kW for a typical ISBM "
            f"barrel) continuously, converting electricity to waste heat with "
            f"no corresponding bottle output. ISO 50001 classifies this as "
            f"avoidable energy waste."
        ),
    }


def _leak_proxy_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Template for pressure-decay leak proxy events."""
    pressure_bar = event.get("pressure_bar", 0.0)
    decay_rate = event.get("decay_rate_bar_per_min", 0.0)

    # Estimate compressed air waste
    # Rough: 1 bar loss ≈ 7 kW compressor compensation
    waste_kw = abs(decay_rate) * 7.0
    waste_kwh_day = waste_kw * 24
    tariff = event.get("tariff_rate_per_kwh", 8.5)
    waste_rupees_day = waste_kwh_day * tariff

    return {
        "severity": "WARNING",
        "title": "💨 Pressure Decay — Possible Compressed Air Leak",
        "summary": (
            f"Compressor discharge pressure is decaying at "
            f"{abs(decay_rate):.2f} bar/min (current: {pressure_bar:.1f} bar) "
            f"while the compressor is loaded. This pattern is consistent "
            f"with a leak in the air distribution network."
        ),
        "recommended_action": (
            f"Inspect compressed air lines, fittings, and downstream "
            f"equipment for audible or soap-bubble-detectable leaks. "
            f"Priority areas: hose connections at ISBM blow stations, "
            f"FRL units, and manifold joints. Tag and schedule repair "
            f"for next maintenance window."
        ),
        "do_not": (
            "Do NOT increase compressor setpoint to compensate — "
            "this masks the leak and increases energy consumption. "
            "The root cause (leak) must be fixed, not the symptom "
            "(low pressure)."
        ),
        "rupee_impact": (
            f"₹{waste_rupees_day:,.0f}/day estimated waste "
            f"({waste_kw:.1f} kW continuous compressor compensation)"
        ),
        "urgency_window": "Schedule inspection within current shift",
        "target_role": "maintenance_engineer",
        "physical_rationale": (
            f"A loaded compressor should maintain discharge pressure at "
            f"setpoint (typically 7–8 bar for ISBM). Sustained decay at "
            f"{abs(decay_rate):.2f} bar/min with the compressor loaded "
            f"indicates flow loss downstream — most commonly a leak. "
            f"Compressed air leaks account for 20–30% of compressor energy "
            f"in typical manufacturing facilities (DOE estimates)."
        ),
    }


def _critical_vibration_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Template for critical vibration (ISO Zone D) events."""
    z_rms = event.get("z_rms", event.get("z_axis_rms_velocity_mm_sec", 0.0))
    iso_zone = event.get("iso_zone", event.get("iso_health_zone", "ZONE_D"))

    return {
        "severity": "CRITICAL",
        "title": "🔴 Critical Vibration — Compressor Bearing at Risk",
        "summary": (
            f"Compressor vibration has entered ISO 10816-3 {iso_zone} "
            f"(RMS velocity: {z_rms:.1f} mm/s, threshold: 18.0 mm/s). "
            f"Continued operation at this level risks catastrophic bearing "
            f"failure."
        ),
        "recommended_action": (
            f"Initiate a 4-minute staggered deceleration of the compressor. "
            f"Simultaneously shed ≥50 kW of non-critical load (HVAC, "
            f"auxiliary systems) to prevent the demand spike from backup "
            f"equipment triggering an MD breach. Monitor vibration during "
            f"deceleration — if it exceeds 25 mm/s, emergency stop."
        ),
        "do_not": (
            "Do NOT hard-stop the compressor immediately — the sudden "
            "load transfer to backup pumps will spike demand past the "
            "500 kVA contract limit (estimated +60 kVA from backup "
            "inrush), causing both a safety incident AND a ₹40,000+ "
            "demand penalty."
        ),
        "rupee_impact": (
            "₹40,000+ penalty avoided by staggered deceleration vs. "
            "hard stop; bearing replacement: ₹15,000–25,000 if caught early"
        ),
        "urgency_window": "Act within 4 minutes — bearing damage accelerates exponentially",
        "target_role": "plant_manager",
        "physical_rationale": (
            f"ISO 10816-3 Zone D ({z_rms:.1f} mm/s > 18.0 threshold) "
            f"indicates unacceptable vibration for Group 2 rotating "
            f"machinery. At this level, bearing life reduces exponentially "
            f"(L10 life halves for every ~3 mm/s above Zone C). A staggered "
            f"4-min deceleration allows controlled load transfer without "
            f"the inrush current spike of a cold restart. The 50 kW load "
            f"shed compensates for backup equipment drawing additional "
            f"current during the transition."
        ),
    }


def _maintenance_risk_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Template for PdM maintenance_risk events (HI threshold breach)."""
    hi_score = event.get("hi_score", 50)
    equipment = event.get("equipment_name", "Compressor")
    days_to_failure = event.get("estimated_days_to_failure", 14)

    return {
        "severity": "WARNING",
        "title": f"🔧 Maintenance Risk — {equipment} Health Index Declining",
        "summary": (
            f"{equipment} Health Index has dropped to {hi_score}/100. "
            f"Trend analysis suggests potential failure within "
            f"~{days_to_failure} days if current degradation continues. "
            f"Preventive action now avoids unplanned downtime."
        ),
        "recommended_action": (
            f"Schedule preventive maintenance for {equipment} within "
            f"the next {max(3, days_to_failure - 3)} working days. "
            f"Priority checks: bearing condition (vibration analysis), "
            f"lubrication levels, belt tension, and electrical connections. "
            f"Create CMMS work order with 'predictive' tag."
        ),
        "do_not": (
            "Do NOT ignore this alert and wait for breakdown — "
            "unplanned downtime costs 3–5× more than scheduled "
            "maintenance (parts expediting, overtime, production loss)."
        ),
        "rupee_impact": (
            f"Preventive maintenance: ₹5,000–15,000 | "
            f"Unplanned breakdown: ₹50,000–1,50,000 (estimated)"
        ),
        "urgency_window": f"Schedule within {max(3, days_to_failure - 3)} working days",
        "target_role": "maintenance_engineer",
        "physical_rationale": (
            f"The Health Index is a composite score derived from vibration "
            f"trends (ISO 10816-3 zone progression), temperature drift, and "
            f"current signature analysis. An HI of {hi_score}/100 indicates "
            f"the equipment is in early-stage degradation — still operational "
            f"but trending toward failure. Acting now keeps the repair in the "
            f"'planned' category where parts, labor, and timing can be "
            f"optimized."
        ),
    }


# ── Template registry ───────────────────────────────────────────────────

CARD_TEMPLATES: dict[str, Any] = {
    "md_nearmiss": _md_nearmiss_fields,
    "lazy_idle": _lazy_idle_fields,
    "leak_proxy": _leak_proxy_fields,
    "critical_vibration": _critical_vibration_fields,
    "maintenance_risk": _maintenance_risk_fields,
}

# Map scenario_label values to event_type keys (some may differ)
_SCENARIO_TO_EVENT: dict[str, str] = {
    "md_nearmiss": "md_nearmiss",
    "lazy_idle": "lazy_idle",
    "leak_proxy": "leak_proxy",
    "critical_vibration": "critical_vibration",
    "maintenance_risk": "maintenance_risk",
}


# ── Card ID generation ──────────────────────────────────────────────────


def _generate_card_id(event_type: str, device_id: str, timestamp: datetime) -> str:
    """Generate a deterministic, dedup-safe card ID.

    Same event + device + timestamp always produces the same ID,
    so regenerating cards from the same data is idempotent.
    """
    raw = f"{event_type}:{device_id}:{timestamp.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ── Generator ───────────────────────────────────────────────────────────


class ActionCardGenerator:
    """Stateless generator: event dict → ActionCard.

    The generator is intentionally stateless — it doesn't cache, queue,
    or accumulate cards.  Each call to ``generate_card()`` is independent.

    This design means the generator can be called from:
    - A dashboard query (batch: scan TSDB → generate cards)
    - A rule-engine callback (real-time: event fires → generate card)
    - A conflict-arbitration output (OI-60: resolved event → generate card)

    all without shared state or concurrency concerns.
    """

    def generate_card(self, event: dict[str, Any]) -> ActionCard:
        """Generate a single action card from a detected condition.

        Parameters
        ----------
        event : dict
            Must contain at minimum:
            - ``event_type`` or ``scenario_label`` — the condition type
            - ``device_id`` — which device triggered it

            Additional fields are event-type-specific and used to
            populate the card's details (kVA, temperature, etc.).

        Returns
        -------
        ActionCard
            A fully populated, frozen action card.
        """
        # Resolve event type from either key
        event_type = event.get("event_type") or event.get("scenario_label", "unknown")
        event_type = _SCENARIO_TO_EVENT.get(event_type, event_type)

        device_id = event.get("device_id", "unknown")

        # Parse timestamp
        ts = self._parse_timestamp(event)

        # Look up template
        template_fn = CARD_TEMPLATES.get(event_type)

        if template_fn is not None:
            fields = template_fn(event)
        else:
            # Generic fallback for unknown event types
            fields = self._generic_fields(event, event_type)
            logger.warning(
                "No template for event_type %r — generated generic card",
                event_type,
            )

        # Extract sensor readings for review
        sensor_readings = {
            k: v for k, v in event.items()
            if k not in ("event_type", "scenario_label", "device_id", "timestamp", "time")
        }

        card_id = _generate_card_id(event_type, device_id, ts)

        return ActionCard(
            card_id=card_id,
            timestamp=ts,
            event_type=event_type,
            severity=fields.get("severity", "INFO"),
            title=fields.get("title", f"Alert: {event_type}"),
            summary=fields.get("summary", ""),
            recommended_action=fields.get("recommended_action", ""),
            do_not=fields.get("do_not", ""),
            rupee_impact=fields.get("rupee_impact", ""),
            urgency_window=fields.get("urgency_window", ""),
            target_role=fields.get("target_role", "plant_manager"),
            device_id=device_id,
            sensor_readings=sensor_readings,
            physical_rationale=fields.get("physical_rationale", ""),
            source_event=dict(event),
        )

    def generate_cards_from_alerts(
        self,
        alerts: list[dict[str, Any]],
    ) -> list[ActionCard]:
        """Generate action cards from a list of alert/event dicts.

        Convenience method for batch processing — e.g., called from the
        dashboard query layer with the output of ``get_alerts()``.

        Parameters
        ----------
        alerts : list[dict]
            Each dict should contain ``scenario_label`` or ``event_type``,
            ``device_id``, and any event-specific fields.

        Returns
        -------
        list[ActionCard]
            One card per alert, deduplicated by ``card_id``.
        """
        seen_ids: set[str] = set()
        cards: list[ActionCard] = []

        for alert in alerts:
            try:
                card = self.generate_card(alert)
                if card.card_id not in seen_ids:
                    seen_ids.add(card.card_id)
                    cards.append(card)
            except Exception:
                logger.exception("Failed to generate card from alert: %s", alert)
                continue

        logger.info(
            "Generated %d action cards from %d alerts (%d deduplicated)",
            len(cards),
            len(alerts),
            len(alerts) - len(cards),
        )
        return cards

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(event: dict[str, Any]) -> datetime:
        """Extract and parse timestamp from event dict."""
        ts_raw = event.get("timestamp") or event.get("time")
        if ts_raw is None:
            return datetime.now(IST)
        if isinstance(ts_raw, datetime):
            if ts_raw.tzinfo is None:
                return ts_raw.replace(tzinfo=IST)
            return ts_raw
        if isinstance(ts_raw, str):
            try:
                dt = datetime.fromisoformat(ts_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                return dt
            except ValueError:
                return datetime.now(IST)
        if isinstance(ts_raw, (int, float)):
            return datetime.fromtimestamp(ts_raw, tz=IST)
        return datetime.now(IST)

    @staticmethod
    def _generic_fields(event: dict[str, Any], event_type: str) -> dict[str, Any]:
        """Fallback template for unknown event types."""
        return {
            "severity": "INFO",
            "title": f"ℹ️ Alert — {event_type.replace('_', ' ').title()}",
            "summary": (
                f"An event of type '{event_type}' was detected on device "
                f"'{event.get('device_id', 'unknown')}'. Review the sensor "
                f"readings below for details."
            ),
            "recommended_action": (
                "Review the sensor readings attached to this card and "
                "determine if operator action is required."
            ),
            "do_not": "",
            "rupee_impact": "",
            "urgency_window": "",
            "target_role": "plant_manager",
            "physical_rationale": (
                f"This is a generic card for an unrecognised event type "
                f"('{event_type}'). No specific physical model is available. "
                f"The raw sensor readings are attached for manual review."
            ),
        }
