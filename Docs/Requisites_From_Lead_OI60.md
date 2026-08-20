# OI-60 Conflict Arbitration — Integration Guide for Lead (Dnyandev)

**From:** Chinmay Wadettiwar (DevC — Platform)  
**To:** Dnyandev Sawarkar (Lead — AI / Rules)  
**Re:** How OI-60 (conflict arbitration) should integrate with OI-69 (action-card generator)  
**Date:** 2026-08-20

---

## Context

I've shipped OI-69: the **action-card generator** that turns detected conditions into human-readable action cards for the dashboard. Your OI-60 (conflict arbitration) is the main upstream producer for this system.

This document tells your agent **exactly what contract to satisfy** so that your arbitration output flows into action cards with zero rework on my side.

---

## What's Already Built (OI-69)

```
Your code (OI-60)                              My code (OI-69)
─────────────────                              ────────────────
                                               ┌──────────────────────┐
Rule engine detects anomaly ──────────────────▶│ ActionCardGenerator   │
                              event dict       │ .generate_card(event) │
Arbitration resolves conflict ────────────────▶│                      │
                              event dict       │ Templates:            │
PdM maintenance_risk ─────────────────────────▶│  • md_nearmiss        │
                              event dict       │  • lazy_idle          │
                                               │  • leak_proxy         │
                                               │  • critical_vibration │
                                               │  • maintenance_risk   │
                                               └──────┬───────────────┘
                                                      │
                                                      ▼
                                               Dashboard UI (Streamlit)
```

The generator is in:
- **Module:** [`src/omniview/rules/action_cards.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/action_cards.py)
- **Class:** `ActionCardGenerator`
- **Method:** `generate_card(event: dict) → ActionCard`

---

## The Contract: Event Dict Format

Your code needs to produce a Python `dict` with these fields. Pass it to `ActionCardGenerator().generate_card(event)` and you'll get a fully rendered `ActionCard` back.

### Required Fields (all event types)

```python
event = {
    "event_type": str,       # One of the registered types (see below)
    "device_id": str,        # e.g. "pune-comp-mfm384"
    "timestamp": str | datetime,  # ISO 8601 or datetime object
}
```

### Event-Type-Specific Fields

#### `md_nearmiss` — Demand approaching contract limit

```python
{
    "event_type": "md_nearmiss",
    "device_id": "pune-comp-mfm384",
    "timestamp": "2026-08-20T10:30:00+05:30",
    # ── Specific fields ──
    "kva": 478.5,                    # Current rolling 15-min kVA average
    "md_proximity_percent": 95.7,    # kVA / contract × 100
    "contract_kva": 500.0,           # Optional, defaults to 500
    "penalty_rate": 350.0,           # Optional, ₹/kVA (defaults to config)
}
```

#### `lazy_idle` — Heat without work

```python
{
    "event_type": "lazy_idle",
    "device_id": "pune-isbm-mfm384",
    "timestamp": "2026-08-20T14:15:00+05:30",
    # ── Specific fields ──
    "current_a_avg": 5.2,            # Current draw (low = idle)
    "barrel_temp_c": 248.0,          # Barrel temp (high = wasting energy)
    "active_power_kw_total": 3.1,    # Idle power draw
    "idle_duration_min": 15,         # How long the idle state has lasted
}
```

#### `leak_proxy` — Pressure decay

```python
{
    "event_type": "leak_proxy",
    "device_id": "pune-comp-wika01",
    "timestamp": "2026-08-20T16:05:00+05:30",
    # ── Specific fields ──
    "pressure_bar": 25.3,            # Current pressure
    "decay_rate_bar_per_min": 0.8,   # Rate of pressure loss
}
```

#### `critical_vibration` — ISO Zone D

```python
{
    "event_type": "critical_vibration",
    "device_id": "pune-comp-vib01",
    "timestamp": "2026-08-20T11:00:00+05:30",
    # ── Specific fields ──
    "z_rms": 22.5,                   # RMS velocity mm/s
    "iso_zone": "ZONE_D",           # ISO 10816-3 zone
}
```

#### `maintenance_risk` — PdM HI threshold breach

```python
{
    "event_type": "maintenance_risk",
    "device_id": "pune-comp-vib01",
    "timestamp": "2026-08-20T09:00:00+05:30",
    # ── Specific fields ──
    "hi_score": 45,                  # Health Index (0–100)
    "equipment_name": "Air Compressor",
    "estimated_days_to_failure": 10,
}
```

---

## How to Call It

### Option A: Direct call (simplest)

```python
from omniview.rules.action_cards import ActionCardGenerator

gen = ActionCardGenerator()

# Your rule/arbitration detects a condition → build the event dict
event = {
    "event_type": "md_nearmiss",
    "device_id": "pune-comp-mfm384",
    "timestamp": datetime.now(IST),
    "kva": 478.5,
    "md_proximity_percent": 95.7,
}

card = gen.generate_card(event)
# card is an ActionCard dataclass — frozen, immutable
print(card.title)               # "⚡ MD Near-Miss — Demand Approaching Contract Limit"
print(card.recommended_action)   # "Shed non-critical load..."
print(card.do_not)              # "Do NOT shut down compressor..."
```

### Option B: Batch processing (for multiple events)

```python
events = [event1, event2, event3]
cards = gen.generate_cards_from_alerts(events)
# Returns deduplicated list[ActionCard]
```

### Option C: Publish to TSDB and let dashboard pick it up

If you prefer not to call the generator directly, you can publish your events
to TSDB with a `scenario_label` field in the JSONB data column. The dashboard's
`get_action_cards()` query function already scans for these labels and
generates cards automatically.

```python
# In your rule engine output:
data = {
    "scenario_label": "md_nearmiss",    # ← this triggers card generation
    "kva": 478.5,
    "md_proximity_percent": 95.7,
    # ... other sensor data ...
}
```

This is how it currently works with the OI-55 seed data.

---

## Adding New Event Types

If you create a new event type (e.g., for arbitrated multi-goal conflicts), you can:

### 1. Register a new template

Add a template function to `CARD_TEMPLATES` in `action_cards.py`:

```python
def _your_new_template(event: dict) -> dict:
    return {
        "severity": "CRITICAL",
        "title": "Your title here",
        "summary": "What happened and why it matters",
        "recommended_action": "What to do",
        "do_not": "What NOT to do",
        "rupee_impact": "₹ figure",
        "urgency_window": "How long to act",
        "target_role": "plant_manager",  # or "maintenance_engineer"
        "physical_rationale": "Why this recommendation is physically sound",
    }

# Register it:
CARD_TEMPLATES["your_event_type"] = _your_new_template
```

### 2. Or just use the generic fallback

If you pass an unrecognised `event_type`, the generator won't crash — it produces
a generic INFO card with the raw sensor readings attached. This is fine for prototyping;
register a proper template when the event type is stable.

---

## Conflict Arbitration Specifics (OI-60)

The architecture doc (§3.2 step 5, §3.5) defines a specific pattern for arbitrated events.
Here's how I'd suggest structuring the arbitration output:

```python
# After your what-if sandbox resolves competing goals:
arbitrated_event = {
    "event_type": "critical_vibration",    # or whatever the primary risk is
    "device_id": "pune-comp-vib01",
    "timestamp": datetime.now(IST),

    # Primary risk data
    "z_rms": 22.5,
    "iso_zone": "ZONE_D",

    # Arbitration context (optional — used if you extend the template)
    "arbitration_result": {
        "competing_goals": ["safety", "compliance"],
        "resolution": "staggered_deceleration",
        "load_shed_kw": 50,
        "decel_minutes": 4,
    },
}
```

The current `critical_vibration` template already handles the staggered-decel
recommendation (Architecture §3.2 example: "4-min staggered deceleration + shed
50kW non-critical load"). If you need to customize the card text based on the
actual arbitration result, add a new template or extend the existing one.

---

## The Priority Order (Already Encoded)

The card templates encode the architecture's priority order:

| Priority | Concern | Card Behavior |
|:--------:|---------|---------------|
| 1 | **Safety** | CRITICAL severity, immediate action, targets plant_manager |
| 2 | **Compliance** | CRITICAL severity, urgency window, targets plant_manager |
| 3 | **Cost** | WARNING severity, ₹ impact, targets maintenance_engineer |

Cards are sorted CRITICAL → WARNING → INFO in the dashboard, so safety always appears first.

---

## Testing Your Integration

```bash
# Run existing tests to make sure nothing breaks
pytest tests/test_action_cards.py -v

# Quick smoke test for your event:
python -c "
from omniview.rules.action_cards import ActionCardGenerator
gen = ActionCardGenerator()
card = gen.generate_card({
    'event_type': 'md_nearmiss',
    'device_id': 'test-01',
    'kva': 480,
})
print(card.title)
print(card.recommended_action)
print(card.do_not)
"
```

---

## Files You'll Want to Read

| File | Why |
|------|-----|
| [`src/omniview/rules/action_cards.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/rules/action_cards.py) | The generator and all templates — this is what your output feeds into |
| [`src/omniview/dashboard/queries.py`](file:///d:/OmniView%20iq/omniview-iq-poc/src/omniview/dashboard/queries.py) | `get_action_cards()` — how the dashboard currently sources events from TSDB |
| [`tests/test_action_cards.py`](file:///d:/OmniView%20iq/omniview-iq-poc/tests/test_action_cards.py) | All 35 tests — shows expected inputs/outputs for every event type |
| [`Docs/OI-69_Worklog.md`](file:///d:/OmniView%20iq/omniview-iq-poc/Docs/OI-69_Worklog.md) | Full worklog with architecture diagram and acceptance criteria |

---

## TL;DR for Your Agent

> **Build OI-60 (conflict arbitration) to output a Python dict with `event_type`,
> `device_id`, `timestamp`, and event-specific sensor values.** Pass this dict to
> `ActionCardGenerator().generate_card(event)` to get a fully rendered `ActionCard`.
> Five event types are already templated. Unknown types get a generic fallback card.
> See the "Event-Type-Specific Fields" section above for the exact keys each template expects.

---

*Questions? Check the tests first — `tests/test_action_cards.py` is the best documentation.*
