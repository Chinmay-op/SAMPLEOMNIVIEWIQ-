# OI-69 Worklog — Action-Card Generator from Rule / PdM Events

**Epic:** [OI-36](https://mightium.atlassian.net/browse/OI-36) (Dashboard / Alerts)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-20  
**Depends on:** OI-60 (conflict arbitration — Lead, not yet shipped; handled with plug-in-ready pattern)

---

## Summary

Implemented the action-card generator that converts rule / PdM events into
human-readable action cards with recommended actions, anti-actions ("Do NOT"),
₹ impact, urgency windows, and physical rationale. Cards are rendered in the
Streamlit dashboard and are internally reviewable for physical soundness.

**Design philosophy:** Cards recommend — they never auto-actuate (PRD §5,
Architecture §3.5). Every card includes a "Do NOT" anti-action to prevent the
most common wrong response (Architecture §3.2 conflict arbitration example).

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/rules/action_cards.py` | Core generator: `ActionCard` dataclass + `ActionCardGenerator` with 5 event-type templates |
| **NEW** | `src/omniview/dashboard/action_card_ui.py` | Streamlit UI components for rendering action cards |
| **MOD** | `src/omniview/dashboard/queries.py` | Added `get_action_cards()` query function |
| **MOD** | `src/omniview/dashboard/app.py` | Added "🎯 Action Cards" section between HI trend and footer |
| **MOD** | `src/omniview/dashboard/__init__.py` | Export `get_action_cards` |
| **MOD** | `src/omniview/rules/__init__.py` | Export `ActionCard`, `ActionCardGenerator`, `CARD_TEMPLATES` |
| **NEW** | `tests/test_action_cards.py` | 35 unit tests — all self-contained, no DB needed |
| **NEW** | `Docs/OI-69_Worklog.md` | This file |
| **NEW** | `Docs/Requisites_From_Lead_OI60.md` | Integration guide for Dnyandev's OI-60 conflict arbitration |

---

## Action Card Templates Implemented

| Event Type | Severity | Target Role | Card Example |
|------------|----------|-------------|-------------|
| `md_nearmiss` | CRITICAL | Plant Manager | "Shed non-critical load within ~4 min; Do NOT shut down compressor" |
| `lazy_idle` | WARNING | Maintenance Engineer | "Investigate idle machine with hot barrel; Do NOT power-cycle" |
| `leak_proxy` | WARNING | Maintenance Engineer | "Inspect air lines for leak; Do NOT increase compressor setpoint" |
| `critical_vibration` | CRITICAL | Plant Manager | "Stagger decel over 4 min + shed 50kW; Do NOT hard-stop" |
| `maintenance_risk` | WARNING | Maintenance Engineer | "Schedule preventive maintenance within N days" |

---

## Action Card Anatomy

```
┌─────────────────────────────────────────────────────────────┐
│ [CRITICAL]  pune-comp-mfm384 · 10:30                       │
│                                                             │
│ ⚡ MD Near-Miss — Demand Approaching Contract Limit         │
│                                                             │
│ Rolling 15-min kVA average has reached 478 kVA — 96% of    │
│ the 500 kVA contract limit. Only 22 kVA headroom remains.  │
│                                                             │
│ 💰 ₹700 penalty risk if 500 kVA breached                   │
│ ⏱️ ~4 min remaining in current 15-min billing window        │
│                                                             │
│ ┌ ✅ Recommended Action ──────────────────────────────────┐ │
│ │ Shed non-critical load (HVAC, aux lighting, pumps)      │ │
│ │ immediately. Target shedding ≥50 kVA within 4 min.      │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌ 🚫 Do NOT ─────────────────────────────────────────────┐ │
│ │ Do NOT shut down compressor or ISBM main drive — the   │ │
│ │ sudden restart will spike inrush current and guarantee  │ │
│ │ a demand overshoot worse than current trajectory.       │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Route to: 👔 Plant Manager                                  │
│                                                             │
│ ▸ 🔬 Physical Rationale (expandable)                        │
│ ▸ 📊 Source Sensor Readings (expandable)                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture Fit

```
Event Sources (current)                    Event Sources (future — OI-60)
─────────────────────                      ──────────────────────────────
scenario_label in TSDB JSONB ───┐          Rule engine (OI-56–61) ──────┐
(seeded by OI-55)               │          Conflict arbitration (OI-60) ┤
                                ▼          PdM maintenance_risk (OI-62) ┘
                    ┌───────────────────┐           │
                    │ ActionCardGenerator│◀──────────┘
                    │ (stateless)       │   (plug-in ready)
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │  get_action_cards()│
                    │  (queries.py)     │
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │  Dashboard UI     │
                    │  (action_card_ui) │
                    └───────────────────┘
```

---

## OI-60 Dependency Handling

OI-60 (conflict arbitration) is a Lead-track dependency that isn't shipped yet.
Rather than blocking, this implementation:

1. **Works standalone** using the existing `scenario_label` events from OI-55 seed data
2. **Is plug-in ready** for OI-60 — the `ActionCardGenerator.generate_card()` accepts any
   event dict, so Lead's arbitration output just becomes another event source
3. **Created integration guide** (`Docs/Requisites_From_Lead_OI60.md`) documenting
   the exact contract Lead's code must satisfy

---

## Test Results

```
35 passed in 0.23s (test_action_cards.py)
```

Test groups:
- `ActionCard` dataclass (4 tests: creation, immutability, serialization, defaults)
- Card ID generation (2 tests: deterministic, uniqueness)
- MD near-miss template (5 tests)
- Lazy-idle template (4 tests)
- Leak proxy template (3 tests)
- Critical vibration template (3 tests)
- Maintenance risk template (3 tests)
- Unknown event fallback (2 tests)
- Scenario label compatibility (2 tests)
- Batch generation + deduplication (4 tests)
- Template coverage (3 tests)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Card generated from injected or live event | ✅ | Cards generated from OI-55 scenario-labeled TSDB events (`md_nearmiss`, `lazy_idle`, `leak_proxy`) |
| Internally reviewable for physical soundness | ✅ | Every card has expandable "Physical Rationale" section with ISO references and engineering logic |
| Include recommended human action (no auto-actuation) | ✅ | "Recommended Action" box + "Do NOT" anti-action box on every card |
| Generate at least one action card from detected conditions | ✅ | 3 card types generate from seeded scenarios; 5 templates total |

---

## How to Run

```bash
# Ensure TSDB has data (seed if needed)
python -m omniview.ingest.seed

# Launch dashboard — action cards appear in new section
streamlit run src/omniview/dashboard/app.py

# Run tests
pytest tests/test_action_cards.py -v
```

---

## Dependencies

- **OI-55** (seed script with scenario labels) ✅
- **OI-68** (dashboard + queries.py) ✅
- **OI-60** (conflict arbitration) — NOT shipped; handled with plug-in-ready design

## What's Unblocked Next

| Person | Ticket | Work | How OI-69 Helps |
|--------|--------|------|----------------|
| **Dnyandev** | OI-60 | Conflict arbitration | Integration doc provided — arbitration output → `ActionCardGenerator.generate_card()` |
| **Chinmay** | OI-71 | Alert routing stub | Action cards have `target_role` field ready for routing |
| **Chinmay** | OI-72 | Jumbo display feed | Action card titles/summaries can drive floor display |

---

*Session completed: 20 August 2026, 12:50 PM IST*
