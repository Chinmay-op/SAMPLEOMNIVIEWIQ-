# OI-53 — NTP Sync Check + Clock-Drift Guard: Session Worklog

**Date:** 19 August 2026  
**Developer:** Chinmay Wadettiwar (DevC — Platform)  
**Jira Epic:** [OI-33](https://mightium.atlassian.net/browse/OI-33) (Edge Gateway)  
**Task:** [OI-52](https://mightium.atlassian.net/browse/OI-52) → **OI-53** (NTP drift guard)  
**Branch:** `chinmay`  
**Depends on:** OI-41 (scaffold) ✅, OI-51 (MQTT) ✅, OI-52 (edge config) ✅

---

## What Was the Task?

The PRD NFR (§2.7) mandates: **"NTP-synced, sub-second; must not drift >5s over the pilot."** The edge config (`edge_nodes.json`) already declared `ntp_enabled: true` and all 7 sensor schemas described timestamps as "NTP-synced" — but **no code existed to check or enforce this**. The goal was to create an NTP drift guard module that periodically verifies the gateway clock against NTP and raises alerts when drift exceeds the 5s threshold.

**Acceptance Criteria (all met ✅):**

- [x] Drift check implemented and logged
- [x] Failure mode documented for pilot
- [x] <5s NFR enforced (configurable threshold, default 5.0s)

---

## What Was Built

### 1. `src/omniview/edge/ntp_guard.py` — NTP Drift Guard Module

| Component | Purpose |
|-----------|---------|
| `DriftStatus` | Frozen dataclass: `offset_seconds`, `is_synced`, `ntp_server`, `check_time`, `stratum`, `threshold_seconds`, `error` |
| `check_drift()` | One-shot function: queries NTP, computes offset, returns `DriftStatus` |
| `NTPDriftGuard` | Background thread: periodic checks, state tracking, MQTT alert publishing |

**Logic flow:**
1. Query NTP server (`ntplib`) → get signed offset in seconds
2. `abs(offset) > threshold?`
   - **YES** → log CRITICAL, publish `NTP_DRIFT_ALERT` to MQTT topic `omniview/{site_id}/system/ntp_drift_alert`, increment consecutive breach counter
   - **NO** → log INFO, reset breach counter
3. Track drift history (last 60 checks, ~1 hour at 60s interval)
4. Sleep `NTP_CHECK_INTERVAL_S`, repeat

**MQTT alert payload (drift breach):**
```json
{
  "event_type": "NTP_DRIFT_ALERT",
  "timestamp": "2026-08-19T12:00:00+05:30",
  "gateway_id": "omniview-edge-pune-isbm",
  "drift_seconds": 6.2,
  "threshold_seconds": 5.0,
  "ntp_server": "pool.ntp.org",
  "stratum": 2,
  "consecutive_failures": 3,
  "severity": "CRITICAL"
}
```

**MQTT alert payload (NTP unreachable):**
```json
{
  "event_type": "NTP_UNREACHABLE",
  "timestamp": "2026-08-19T12:00:00+05:30",
  "gateway_id": "omniview-edge-pune-isbm",
  "ntp_server": "pool.ntp.org",
  "consecutive_failures": 3,
  "last_error": "Network unreachable",
  "severity": "CRITICAL"
}
```

### 2. Failure Modes (documented for pilot)

| Failure Mode | Behavior | Recovery |
|---|---|---|
| **NTP server unreachable** (transient) | Log WARNING, retain last known offset, retry next cycle. No alert for single failure. | Automatic on next cycle |
| **Consecutive NTP failures ≥ max_retries** | Log CRITICAL "NTP UNREACHABLE", publish MQTT alert. Continues retrying. | Automatic when NTP server responds |
| **Gateway has no internet** | Guard degrades gracefully. Offline buffer (OI-28) caches telemetry. Guard resumes checking when connectivity returns. | Automatic on reconnect |
| **publish_fn raises** | Error logged, guard continues. Alert delivery failure does not crash the drift monitor. | Automatic on next check |

### 3. Config Constants Added to `config.py`

| Constant | Default | Purpose |
|----------|---------|---------|
| `NTP_SERVER` | `pool.ntp.org` | NTP server to query |
| `NTP_DRIFT_THRESHOLD_S` | `5.0` | Max acceptable drift (PRD NFR) |
| `NTP_CHECK_INTERVAL_S` | `60` | Seconds between checks |
| `NTP_MAX_RETRIES` | `3` | Consecutive NTP failures before "unreachable" alert |
| `NTP_TIMEOUT_S` | `5.0` | Per-query timeout |

All overridable via environment variables.

### 4. Updated `src/omniview/edge/__init__.py`

Added `NTPDriftGuard`, `DriftStatus`, `check_drift` to public API exports.

### 5. Added `ntplib` to `requirements.txt`

Lightweight, pure-Python NTP client (~7KB, no C deps).

---

## Files Created/Modified (5 total)

```
 NEW  src/omniview/edge/ntp_guard.py         — NTP drift guard module
 MOD  src/omniview/config.py                 — NTP config constants (5 new)
 MOD  src/omniview/edge/__init__.py          — Export NTPDriftGuard, DriftStatus, check_drift
 MOD  requirements.txt                       — Added ntplib>=0.4.0
 NEW  tests/test_ntp_guard.py               — 46 unit tests
```

---

## Verification Done

| Test | Result |
|------|--------|
| `pytest tests/test_ntp_guard.py -v` | ✅ 46/46 passed |
| `pytest tests/ -v` (full suite) | ✅ 268/268 passed (0 regressions) |
| All imports resolve | ✅ `from omniview.edge import NTPDriftGuard, DriftStatus, check_drift` |
| Config loads correctly | ✅ All 5 NTP constants have correct defaults |
| Frozen dataclass | ✅ DriftStatus is immutable |
| Thread lifecycle | ✅ start/stop/daemon verified |
| MQTT alert payloads | ✅ All required fields present |
| Failure modes | ✅ NTP unreachable, publish errors handled gracefully |

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| **`ntplib` (not `w32tm` or `chrony`)** | Pure-Python, cross-platform, no system-level deps. Works on Windows dev machines and Linux gateways. |
| **`check_drift()` as a standalone function** | Makes one-shot usage and unit testing trivial without instantiating the full guard. |
| **Daemon thread** | Guard doesn't prevent process exit. If the main process dies, the guard dies with it — correct for an edge service. |
| **`_stop_event.wait()` instead of `time.sleep()`** | `stop()` terminates instantly instead of waiting for the full `check_interval_s`. |
| **Alert via `publish_fn` callback, not direct MQTT client** | Decouples the guard from MQTT client lifecycle. Can be used with any publish mechanism, or log-only (no MQTT). |
| **`<= threshold` means synced (inclusive)** | PRD says "must not drift >5s", so exactly 5.0s is still within spec. |
| **Consecutive failure counter for NTP unreachable** | Avoids alert noise from single transient NTP timeouts. Only fires after `max_retries` consecutive failures. |
| **History capped at 60** | ~1 hour of checks at 60s interval. Enough for trend analysis without unbounded memory growth. |

---

## What's Unblocked Next

| Person | Ticket | Work | Depends On |
|--------|--------|------|------------|
| **Chinmay** | OI-13 | Physical Modbus sensor poller | Edge config ✅ + NTP guard ✅ |
| **Chinmay** | OI-68 | Live dashboard | NTP status available for system health panel |
| **Dnyandev** | OI-56 | Rolling 15-min kVA + MD alert | NTP guard ensures timestamp validity ✅ |

---

*Session completed: 19 August 2026, 11:39 AM IST*
