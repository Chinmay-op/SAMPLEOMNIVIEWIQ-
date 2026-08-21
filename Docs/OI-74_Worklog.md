# OI-74 Worklog — Site Walkthrough + Layer 0 Profile

**Epic:** [OI-40](https://mightium.atlassian.net/browse/OI-40) (Hardware / Site)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-22  
**Depends on:** PRD §1.4, §9 Phase 0, Architecture §3.4

---

## Summary

Implemented the complete Layer 0 site configuration profile and site
walkthrough checklist module. Layer 0 (Architecture §3.4) is the lowest
layer in the stack — nothing below it hardcodes site-specific facts.

The module captures:
- **2 machine profiles** with nameplate data, physical location, access level
- **10 sensor mount locations** with exact floor positions, cable routes, and safety notes
- **MSEDCL tariff parameters** (contracted demand, billing window, penalty rates)
- **20-item walkthrough checklist** covering all PRD §9 Phase 0 confirmations

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/edge/site_profile.py` | Core module: `Layer0Profile`, `SiteWalkthrough`, `LocationPoint`, `MachineProfile` |
| **NEW** | `tests/test_site_profile.py` | 60 unit tests — all self-contained |
| **NEW** | `Docs/smoke_test_oi74.py` | Smoke test with full profile + checklist output |
| **NEW** | `Docs/OI-74_Worklog.md` | This file |

---

## Location Map (10 Mount Points)

### compressor-01 — 4 locations

| ID | Name | Device | Zone | Access | Dist |
|----|------|--------|------|--------|------|
| LOC-C01 | Main Panel — Exterior Door | pune-comp-mfm384 | compressor_room | panel_door | 0m |
| LOC-C02 | Bearing Housing — Drive End | pune-comp-vib01 | compressor_room | open | 8m |
| LOC-C03 | Output Receiver — Gauge Port | pune-comp-wika01 | compressor_room | open | 11m |
| LOC-C04 | Motor Switchboard — Interior | pune-comp-gas01 | compressor_room | panel_door | 1m |

### isbm-01 — 3 locations

| ID | Name | Device | Zone | Access | Dist |
|----|------|--------|------|--------|------|
| LOC-I01 | Main Electrical Panel — Exterior | pune-isbm-mfm384 | production_floor | panel_door | 0m |
| LOC-I02 | Barrel / Hot-Runner Zone | pune-isbm-therm01 | production_floor | open | 6m |
| LOC-I03 | Ejection / Stroke Mechanism | pune-isbm-stroke01 | production_floor | open | 10m |

### Infrastructure — 3 locations

| ID | Name | Zone | Access | Dist |
|----|------|------|--------|------|
| LOC-F01 | Ambient Sensor Mount | common_area | open | 0m |
| LOC-F02 | Jumbo Display Mount | common_area | open | 5m |
| LOC-F03 | Edge Gateway Cabinet | electrical_room | panel_door | 2m |

---

## Machine Profiles

| Field | Compressor (MACH-COMP-01) | ISBM (MACH-ISBM-01) |
|-------|---------------------------|----------------------|
| Node | compressor-01 | isbm-01 |
| Class | rotary_screw_compressor | injection_stretch_blow_molder |
| Make/Model | TBC on-site | Nissei ASB-70DPH (TBC) |
| Rated Power | 37 kW | TBC |
| Rated Pressure | 40 bar | N/A |
| Voltage | 415V 3-phase | 415V 3-phase |
| Zone | compressor_room | production_floor |
| Connection | single_feed | single_feed (TBC) |
| Noise | >85 dB | 70–80 dB |
| Temperature | 30–45°C ambient | 25–35°C ambient, 150–280°C barrel |

---

## Layer 0 Profile Fields

| Category | Fields Captured |
|----------|----------------|
| **Site** | site_id, name, address, timezone, utility, digital infra, connectivity, hours, shifts |
| **Tariff** | utility (MSEDCL), category (HT-I), contracted demand (500 kVA), penalty rate, billing window (15 min) |
| **Machines** | machine_id, node_id, make/model, nameplate kW/bar, voltage, zone, panel location, cable entry, connection type, access, environment, noise, temperature |
| **Locations** | point_id, name, node_id, device_id, zone, description, access level, floor level, distance from panel, cable route, safety notes |

---

## Walkthrough Checklist (20 Items)

| Group | Items | Coverage |
|-------|-------|----------|
| Compressor (WT-01 to WT-07) | 7 | Nameplate, panel, CTs, bearing, gauge port, RS-485 route |
| ISBM (WT-08 to WT-13) | 6 | Nameplate, single feed check, CTs, barrel, stroke, RS-485 route |
| Site-wide (WT-14 to WT-20) | 7 | Contracted demand, MSEDCL bills, gateway, display, ambient, safety, power |

---

## Test Results

```
 60 passed in 0.29s  (test_site_profile.py)
642 passed in 7.32s  (full regression — zero regressions)
```

Test groups:
- `TestSiteInfo` (3 tests)
- `TestTariffProfile` (2 tests)
- `TestLocationPoint` (2 tests)
- `TestMachineProfile` (8 tests: both machines, zones, lookups, serialization)
- `TestLayer0Profile` (11 tests: counts, node locations, zone queries, JSON, markdown)
- `TestLocationMapDetails` (11 tests: every mount point verified, safety/cable notes present)
- `TestSiteWalkthrough` (12 tests: lifecycle, confirm/revision, checklist output)
- `TestWalkthroughItems` (7 tests: PRD §9 Phase 0 coverage)
- `TestReportGeneration` (4 tests: report structure, acceptance criteria, JSON)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| Location map for both nodes | ✅ | 4 locations for compressor-01, 3 for isbm-01, 3 for infrastructure |
| Layer 0 profile draft complete | ✅ | 2 machines, 10 locations, tariff params, 20-item walkthrough |

---

## How to Run

```bash
pytest tests/test_site_profile.py -v
python Docs/smoke_test_oi74.py
pytest tests/ -v
```

---

*Session completed: 22 August 2026, 12:35 AM IST*
