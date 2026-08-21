# OI-71 Worklog — Alert Routing Stub (Operator / Maintenance / Manager)

**Epic:** [OI-36](https://mightium.atlassian.net/browse/OI-36) (Dashboard / Alerts)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-21  
**Depends on:** OI-69 (action cards — `target_role` field ✅ shipped)

---

## Summary

Implemented the Layer 6 "Deliver & Act" alert routing stub that takes action
cards (from OI-69) and dispatches them to the correct persona via the correct
channel. The routing table maps `(severity, target_role)` → channels, with
3 channel stubs (Log, Email, Webhook) ready for production swap-in.

**Design philosophy:** Route alerts to the person who can *actually act* —
not blast to everyone. A system that sends every alert to every stakeholder
trains people to ignore all of them within a week (Architecture §3.3).

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/dashboard/alert_router.py` | Core routing: `AlertChannel` enum, `RoutingRule`, `ROUTING_TABLE`, 3 channel stubs (`LogChannel`, `EmailChannel`, `WebhookChannel`), `AlertRouter` class |
| **MOD** | `src/omniview/config.py` | Added `ALERT_ROUTING_ENABLED`, `ALERT_WEBHOOK_URL`, `ALERT_EMAIL_RECIPIENT_MAP` |
| **MOD** | `src/omniview/dashboard/app.py` | Added "🔔 Alert Routing Log" section with dispatch metrics and audit table |
| **MOD** | `src/omniview/dashboard/__init__.py` | Export `AlertRouter`, `AlertChannel`, `ROUTING_TABLE`, `RoutingResult` |
| **NEW** | `tests/test_alert_router.py` | 56 unit tests — all self-contained, no DB/MQTT needed |
| **NEW** | `Docs/OI-71_Worklog.md` | This file |

---

## Routing Table (Documented Contract)

| Severity | Target Role | Channels | Description |
|----------|-------------|----------|-------------|
| CRITICAL | plant_manager | webhook, log | MD near-miss / critical vibration → push alert to plant manager |
| CRITICAL | operator | webhook, log | Immediate floor action (breakdown / safety) → push to operator display |
| CRITICAL | maintenance_engineer | webhook, email, log | Critical equipment failure → push + email to maintenance |
| WARNING | maintenance_engineer | email, log | Lazy-idle / leak / HI decline → email maintenance for scheduled action |
| WARNING | plant_manager | email, log | Demand trending up / cost warning → email plant manager |
| WARNING | operator | log | Floor-level warning → log only (operator sees dashboard) |
| INFO | plant_manager | log | Informational update → log only |
| INFO | maintenance_engineer | log | Informational update → log only |
| INFO | operator | log | Informational update → log only |

---

## Channel Stubs

| Channel | POC Behavior | Production Replacement |
|---------|-------------|----------------------|
| **LogChannel** | Structured Python log (`logging.info`/`warning`) with JSON entry | Same (always active as audit trail) |
| **EmailChannel** | Logs mock email: recipient, subject, body preview | SMTP / SendGrid / SES |
| **WebhookChannel** | Logs mock POST: URL, JSON payload | `httpx.post()` / `requests.post()` |
| SMS (reserved) | Not implemented | Twilio / MSG91 |
| CMMS (reserved) | Not implemented | CMMS ticket API |

All stubs implement a `ChannelBackend` protocol — swap by replacing the class, not the routing logic.

---

## Architecture Fit

```
ActionCardGenerator (OI-69)
        │ ActionCard with target_role + severity
        ▼
┌───────────────────────┐
│ AlertRouter (OI-71)   │ ← NEW
│ route(card) → results │
└───────┬───────────────┘
        │ looks up ROUTING_TABLE
        ├──────────┬───────────────┐
        ▼          ▼               ▼
┌──────────┐ ┌──────────────┐ ┌───────────────┐
│LogChannel│ │ EmailChannel │ │WebhookChannel │
│(always)  │ │(WARNING+)    │ │(CRITICAL only)│
└──────────┘ └──────────────┘ └───────────────┘
        │
        ▼
┌───────────────────────┐
│ Dashboard Audit Table │ ← dispatches shown in UI
│ (app.py routing log)  │
└───────────────────────┘
```

---

## Configuration Added

| Variable | Default | Purpose |
|----------|---------|---------|
| `ALERT_ROUTING_ENABLED` | `true` | Feature flag — disable routing without code change |
| `ALERT_WEBHOOK_URL` | `http://localhost:9999/alerts` | Webhook endpoint for push alerts |
| `ALERT_EMAIL_RECIPIENT_MAP` | `{}` (uses defaults) | JSON map: `{"plant_manager": "pm@co.com", ...}` |

---

## Test Results

```
56 passed in 0.77s (test_alert_router.py)
427 passed in 6.75s (full regression)
```

Test groups:
- `TestRoutingTable` (9 tests: structure, completeness, severity coverage, log-always, webhook-critical, email-warning, no-dupes)
- `TestLookupChannels` (6 tests: all severity+role combos, unknown fallback)
- `TestLogChannel` (4 tests: result type, log levels, JSON validity)
- `TestEmailChannel` (7 tests: recipients per role, custom map, fallback, subject format, JSON)
- `TestWebhookChannel` (4 tests: result, default/custom URL, payload)
- `TestAlertRouter` (12 tests: dispatch correctness for all 5 event types via real `ActionCardGenerator`, custom URL/email, feature flag)
- `TestAlertRouterBatch` (3 tests: multi-card, empty, status)
- `TestRoutingResult` (2 tests: serialization, JSON-safe)
- `TestRoutingTableDocumentation` (3 tests: markdown output)
- `TestAlertChannelEnum` (6 tests: values, string enum)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Routing table documented | ✅ | `ROUTING_TABLE` tuple in code + markdown table in this worklog |
| Stub emits to correct channel mock | ✅ | 12 integration tests route real `ActionCardGenerator` output through the router and verify correct channels |
| Severity→persona routing stub | ✅ | 9 routing rules covering CRITICAL/WARNING/INFO × 3 personas |
| log/email/webhook placeholder OK for POC | ✅ | 3 channel stubs implement `ChannelBackend` protocol with structured logging |

---

## How to Run

```bash
# Run alert routing tests
pytest tests/test_alert_router.py -v

# Launch dashboard — routing log section appears after action cards
streamlit run src/omniview/dashboard/app.py

# Full regression
pytest tests/ -v
```

---

## Dependencies

- **OI-69** (action cards with `target_role`) ✅
- **OI-68** (dashboard + queries.py) ✅
- **OI-55** (seed script with scenario labels) ✅

## What's Unblocked Next

| Person | Ticket | Work | How OI-71 Helps |
|--------|--------|------|-----------------|
| **Chinmay** | OI-72 | Jumbo display feed | Routing results provide the data pipe — operator alerts flow to floor display |
| **Dnyandev** | OI-56–61 | Rule engine | Rule events → `ActionCardGenerator` → `AlertRouter` pipeline is end-to-end ready |
| **Dnyandev** | OI-60 | Conflict arbitration | Arbitration output → action card → routed to correct persona automatically |

---

*Session completed: 21 August 2026, 10:55 PM IST*
