# F06 — Vibration ISO zones

**POC stance:** Must (zone bands); per-state pattern libraries later  
**HITL:** Vib zone alert / card — no auto hard-stop in POC (arbitration may *recommend*)  
**Nodes:** `hp-compressor` (motor/bearing); ISBM drive if instrumented

## Problem

Mechanical degradation on the compressor (or drive) is often noticed only after failure stops the line. The plant has no continuous ISO-aligned vibration view.

## Solution

Mount non-invasive vib + surface temp nodes; classify RMS velocity into **ISO 10816-3 Class II** bands (e.g. 2.8 / 7.1 mm/s style thresholds per PRD); emit vibration-zone events for HITL. Change-over-time pattern ID across idle/working/cooldown is a later enhancement on the same stream.

## What

- Poll vib/temp ≤60 s (FR2)
- Zone classification (A/B/C/D style bands for Class II)
- Layer3 vibration event for dashboard / arbitration (F09)

## Why

Mechanical safety signal for POC; feeds conflict cases with MD (safety vs compliance).

## Where (site / nodes / UI surface)

| Place | Role |
|-------|------|
| Compressor bearing / motor housing | Banner QM42VT / Q45VT (or equiv.) |
| Dashboard | Zone badge + trend later |

## Jira (existing)

| Key | Role |
|-----|------|
| [OI-58](https://mightium.atlassian.net/browse/OI-58) | Vibration zone rules (ISO 10816-3 Class II) |
| [OI-5](https://mightium.atlassian.net/browse/OI-5) | Vibration schema |

## Sensors / functions / algorithms

| Layer | Item |
|-------|------|
| Sensors | Triaxial MEMS vib + co-located temp |
| Functions | RMS velocity → zone mapper |
| Algorithms | Fixed ISO Class II thresholds (site confirmation of class); not deep anomaly ML in POC |

## Benefits

- Early mechanical risk visibility
- Standard language (ISO) for maintenance engineers
- Input to F09 when vib critical coincides with MD risk

## End goal (done when)

- Live or injected vib levels map to correct zone
- Alert fires on critical band with `machine_id`
- Documented thresholds match PRD §2.7

## Code / doc pointers

- PRD FR2, NFR vibration standard — `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`
- Sensor — `Docs/OmniView_IQ_Sensor_Summary_CEO.md`
- Layer3 vibration event contract
