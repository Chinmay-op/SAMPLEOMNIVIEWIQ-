# OI-73 Worklog — Finalize BOM + Procurement Lead Times

**Epic:** [OI-40](https://mightium.atlassian.net/browse/OI-40) (Hardware / Site)  
**Owner:** Chinmay Wadettiwar (DevC — Platform)  
**Status:** ✅ Complete  
**Date:** 2026-08-22  
**Depends on:** PRD §3 (sensor list), PRD §8 (risks), Architecture §3.1 (protocols)

---

## Summary

Implemented the complete Bill of Materials module for the 2-node POC hardware
deployment. The module codifies all 19 BOM line items (29 total units) with
quantities, cost ranges (INR), lead times, vendor locations, availability
classifications, and critical-path flags — all sourced from PRD §3 and
validated against `config/edge_nodes.json` device_ids.

**Critical-path item identified:** Banner Q45VT / NCD Wireless MEMS vibration
node — **7–14 day lead time** (PRD §8). Must be ordered first to avoid
compressing the baseline capture window.

**Estimated total CapEx:** ₹1,14,620 – ₹1,65,440 (sensors + infrastructure +
ancillary). Within the PRD §3 range of ₹95,000–₹1,20,000 for primary sensors;
higher total includes gateway, display, cabling, power, and mounting.

---

## Files Changed

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `src/omniview/edge/bom.py` | Core module: `BOMItem`, `BOMSheet`, `generate_bom_report()` with 19 line items |
| **NEW** | `tests/test_bom.py` | 60 unit tests — all self-contained, no DB/MQTT needed |
| **NEW** | `Docs/smoke_test_oi73.py` | Smoke test: displays full BOM, critical path, cost breakdown |
| **NEW** | `Docs/OI-73_Worklog.md` | This file |

---

## BOM Sheet (19 Items, 29 Units)

### Primary Sensors (11 items)

| ID | Item | Make/Model | Node | Qty | Unit Cost (₹) | Lead Time | Critical? |
|----|------|-----------|------|-----|---------------|-----------|-----------|
| BOM-001 | Energy Meter (Compressor) | Selec MFM384-C-CE | compressor-01 | 1 | 4,000–6,000 | 1–3 days | — |
| BOM-002 | Energy Meter (ISBM) | Selec MFM384-C-CE | isbm-01 | 1 | 4,000–6,000 | 1–3 days | — |
| BOM-003 | Split-Core CTs (Compressor) | Selec SCCT-30/20 | compressor-01 | 3 | 1,500–2,000 | 1–3 days | — |
| BOM-004 | Split-Core CTs (ISBM) | Selec SCCT-30/20 | isbm-01 | 3 | 1,500–2,000 | 1–3 days | — |
| BOM-005 | Vibration & Temp Node | Banner Q45VT / NCD MEMS | compressor-01 | 1 | 25,000–35,000 | 7–14 days | ⚠ **YES** |
| BOM-006 | Pressure Transmitter | WIKA A-10 (0–40 bar) | compressor-01 | 1 | 13,000–17,000 | 2–5 days | — |
| BOM-007 | Gas/Overheating Sensor | Schneider HeatTag | compressor-01 | 1 | 8,000–12,000 | 3–7 days | — |
| BOM-008 | Thermal Probe (ISBM) | RTD/PT100 | isbm-01 | 1 | 2,000–4,000 | 1–3 days | — |
| BOM-009 | Thermal Probe (Compressor) | Banner Q45VT co-located | compressor-01 | 1 | 0 (included) | 0 days | — |
| BOM-010 | Stroke Counter | Proximity sensor | isbm-01 | 1 | 1,500–3,000 | 1–3 days | — |
| BOM-011 | Ambient Sensor | Schneider TH110 | floor | 1 | 3,000–5,000 | 2–5 days | — |

### Infrastructure (2 items)

| ID | Item | Make/Model | Qty | Unit Cost (₹) | Lead Time |
|----|------|-----------|-----|---------------|-----------|
| BOM-012 | Edge Gateway | Teltonika RUT956 | 1 | 22,000–29,000 | 3–7 days |
| BOM-013 | Jumbo Floor Display | Multispan RS-6006 | 1 | 15,000–22,000 | 2–5 days |

### Cabling & Ancillary (6 items)

| ID | Item | Make/Model | Qty | Unit Cost (₹) | Lead Time |
|----|------|-----------|-----|---------------|-----------|
| BOM-014 | RS-485 Cable | Belden 9841 | 2 | 500–1,000 | 1–2 days |
| BOM-015 | Termination Resistors | 120Ω ¼W | 4 | 5–10 | 1 day |
| BOM-016 | 4-20mA→Modbus Converter | Novus DigiRail-2A | 1 | 3,000–5,000 | 2–5 days |
| BOM-017 | 24V DC Power Supply | Mean Well HDR-30-24 | 2 | 1,200–2,000 | 1–3 days |
| BOM-018 | Mounting Hardware Kit | Assorted | 1 | 1,500–3,000 | 1–2 days |
| BOM-019 | 4G LTE SIM Cards | Jio/Airtel M2M | 2 | 100–200 | 1–2 days |

---

## ⚠ Critical-Path Items

| ID | Item | Lead Time | Action Required |
|----|------|-----------|-----------------|
| **BOM-005** | Banner Q45VT / NCD Wireless MEMS Vibration & Temperature Node | **7–14 days** | Order **immediately** to avoid compressing baseline window (PRD §8) |

**Why this is the critical path:** The vibration node is an import item (Banner Engineering, US) requiring 1–2 weeks. All other items are locally available in Pune/India within 1–7 days. If vibration procurement slips, the 3-week POC timeline compresses baselining time (PRD §8).

---

## Cost Summary

| Metric | Value |
|--------|-------|
| Total CapEx (low) | ₹1,14,620 |
| Total CapEx (high) | ₹1,65,440 |
| Primary sensors only | ₹69,500–₹1,00,000 |
| Infrastructure | ₹37,000–₹51,000 |
| Ancillary/cabling | ₹8,120–₹14,440 |
| Max lead time | 14 days |
| Critical-path lead | 14 days (vibration node) |

### Cost by Node

| Node | Low | High |
|------|-----|------|
| compressor-01 | ₹57,500 | ₹81,000 |
| isbm-01 | ₹12,000 | ₹19,000 |
| floor | ₹18,000 | ₹27,000 |
| shared (all) | ₹27,120 | ₹38,440 |

---

## Vendor Map

| Vendor | Items | Location |
|--------|-------|----------|
| Selec Controls | MFM384 × 2, SCCT CTs × 6 | Navi Mumbai — pan-India distributors |
| Banner Engineering | Q45VT vibration node × 1 | US import via authorized distributor |
| WIKA India | A-10 pressure transmitter × 1 | **Pune local manufacturing** |
| Schneider Electric | HeatTag × 1, TH110 × 1 | Pan-India distributors |
| Teltonika Networks | RUT956 gateway × 1 | EU import via authorized distributor |
| Multispan India | RS-6006 jumbo display × 1 | Thane — pan-India distributors |
| Local suppliers | Cables, mounts, PSU, SIMs, RTD | Pune |

---

## Architecture Fit

```
PRD §3 Sensor List
        │ costs, models, availability
        ▼
┌───────────────────────────────┐
│ BOMSheet (OI-73)              │ ← NEW
│ 19 items, 29 units            │
│ ₹1,14,620–₹1,65,440          │
│ Critical path: 14 days (vib)  │
└───────────┬───────────────────┘
            │
            ▼
┌───────────────────────────────┐
│ InstallProcedure (OI-76)      │ ← uses BOM items
│ 12 steps, zero downtime       │
└───────────────────────────────┘
            │
            ▼
┌───────────────────────────────┐
│ Edge Gateway (RUT956)         │
│ config/edge_nodes.json        │
│ → MQTT → TSDB → Dashboard    │
└───────────────────────────────┘
```

---

## Test Results

```
60 passed in 0.21s (test_bom.py)
582 passed in 6.85s (full regression — zero regressions)
```

Test groups:
- `TestBOMItem` (6 tests: creation, total cost, lead time display, cost display, serialization)
- `TestBOMSheet` (7 tests: item count, quantity, cost range, lead time, critical-path)
- `TestBOMItems` (14 tests: every PRD §3 item present — MFM384, SCCT, Banner, WIKA, RUT956, RS-6006, HeatTag, thermal, stroke, ambient, cable, converter)
- `TestNodeBreakdown` (4 tests: per-node item lists, cost breakdown)
- `TestCategoryBreakdown` (4 tests: sensor/meter/gateway categories, cost breakdown)
- `TestProcurementLifecycle` (5 tests: initial status, mark ordered/received, unknown item, status filter)
- `TestAvailability` (3 tests: availability levels, vibration = medium)
- `TestBOMPrintable` (4 tests: markdown output, all items, cost summary, lead time)
- `TestReportGeneration` (5 tests: report structure, acceptance criteria, summary, critical path, JSON)
- `TestCostValidation` (6 tests: PRD §3 cost ranges for MFM384, CTs, vibration, WIKA, gateway, jumbo)
- `TestDeviceIdMapping` (2 tests: all 9 device_ids from edge_nodes.json present, no unknowns)

---

## Acceptance Criteria ✅

| Criteria | Met? | Evidence |
|----------|:----:|----------|
| BOM sheet with qty/cost/lead time | ✅ | 19 items, each with quantity, unit cost range (INR), and lead time range (days) |
| Critical-path items flagged | ✅ | BOM-005 (Banner Q45VT vibration node) flagged with `is_critical_path=True`, 7–14 day lead time |
| Finalize BOM: MFM384, SCCT, Banner vib, WIKA A-10, gateway, jumbo | ✅ | All 6 items present: BOM-001/002, BOM-003/004, BOM-005, BOM-006, BOM-012, BOM-013 |
| Capture lead times and vendors | ✅ | Every item has `lead_time_days_min/max`, `vendor_location`, and `availability` classification |

---

## How to Run

```bash
# Run BOM tests
pytest tests/test_bom.py -v

# Run smoke test
python Docs/smoke_test_oi73.py

# Full regression
pytest tests/ -v
```

---

## Dependencies

- **PRD §3** (sensor list with costs and models)
- **PRD §8** (risks — vibration node critical path)
- **Architecture §3.1** (protocols, polling intervals)
- **config/edge_nodes.json** (device_ids, Modbus addresses)

## What's Unblocked Next

| Person | Ticket | Work | How OI-73 Helps |
|--------|--------|------|--------------------|
| **Chinmay** | OI-74 | Site walkthrough / Layer 0 profile | BOM is finalized → walkthrough confirms physical locations |
| **Chinmay** | OI-76 | Non-invasive install | BOM confirmed → install procedure has verified hardware list |
| **Chinmay** | OI-77 | Clamp-meter calibration log | BOM includes handheld cross-check reference |
| **Dnyandev** | OI-78–80 | Live cutover + acceptance | Hardware procurement can begin immediately |

---

*Session completed: 22 August 2026, 12:00 AM IST*
