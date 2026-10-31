# Hospital Device & Sensor Master Tracker — Context & Requirements

**Status:** Draft for review — read this, then we build the Excel from it.
**Author input sources:** [`hospital-info.md`](../../hospital-info.md), [`sensor-info.md`](../../sensor-info.md), [`hd-working-brife.md`](../../hd-working-brife.md) (root, untracked scratch notes), [`Docs/DS/Hospital_Site_Survey_Field_Pack.docx`](Hospital_Site_Survey_Field_Pack.docx), [`Docs/sesnor-fetures.md`](../sesnor-fetures.md), [`Docs/OmniView_IQ_Sensor_Summary_CEO.md`](../OmniView_IQ_Sensor_Summary_CEO.md), [`Docs/DS/Base_Core_Site_Profile_ADR.md`](Base_Core_Site_Profile_ADR.md).

---

## 1. What this is for

You're visiting hospitals for site surveys (Apollo-style multi-specialty, or smaller general hospitals) to scope an OmniView IQ deployment. You need one **reusable master Excel** that you fill in on-site, per hospital, that:

- Lists the departments a hospital has (editable — add/remove per site).
- For each department, lets you pick which **sensor types** apply, how many, and auto-calculates line cost and total tentative cost.
- Uses **generic sensor type names** (e.g. "Vibration & Mechanical Health Sensor"), never a vendor/brand name — so the sheet is safe to hand to a client.
- Works as a **template**: one file, reused across many hospitals (Apollo Pune, next hospital, etc.), not a one-off.

This is a **business/sales survey tool**, distinct from the existing [`Hospital_Site_Survey_Field_Pack.docx`](Hospital_Site_Survey_Field_Pack.docx), which is a qualitative walkdown script (find → tag → attach, F0x use-case mapping, HITL/no-clinical-sensing guardrails). That doc stays as-is — the new Excel is the **quantitative companion**: it turns the walkdown findings into counts, sensor picks, and a costed BOM (bill of materials) per department, with a grand total.

**Hard constraint carried over from the field pack (keep in the new sheet too):** facility/utility sensing only. No patient/clinical sensors (no SpO2, ECG, ventilator waveform, bedside monitors). ICU/OT/Ward entries are about the **electrical, thermal, pressure, and vibration load** in that space — not clinical equipment.

---

## 2. Workbook structure (proposed — 5 sheets)

| # | Sheet | Purpose |
|---|-------|---------|
| 1 | **Instructions** | One page: how to use the sheet, legend, color key |
| 2 | **Sensor Catalog** | Master list of generic sensor types — name, category, description, use case, typical placement, tentative unit cost (min/max), OmniView function tag. This is the *lookup source* for dropdowns — locked/reference sheet. |
| 3 | **Department Master** | Master list of hospital departments (generic, editable) — feeds the department dropdown. You add a department here once, it's available everywhere. |
| 4 | **Site Survey** (main sheet, one per hospital — or a "Hospital Name" column if you want all hospitals in one running sheet) | Data entry grid: Department (dropdown) → Sensor Type (dropdown) → Qty → Unit cost (auto-filled from catalog, editable override) → Line total (formula) → Notes/placement detail. |
| 5 | **Cost Summary / Dashboard** | Auto-rolled-up pivot: total cost per department, total cost per sensor category, grand total, sensor count. |

Data validation (dropdowns) on Sheet 4 pulls from Sheet 2 and Sheet 3 named ranges, so adding a row to the catalog or department list instantly makes it selectable in the survey grid — that's how you "add a department if needed."

### 2a. What each Site Survey field means (re-verified — see §3a for the "why")

| Field | What it is | How it's used |
|---|---|---|
| **Department** | The major hospital function/area this cost belongs to (ICU, OT, Boiler Room, Electrical Room…) | Drives the **by-Department** cost rollup |
| **Sub-Department / Ward Name** | The specific *named instance* within a Department, only needed when there's more than one — e.g. Department = `ICU`, Sub-Department = `Gynec ICU` / `TB ICU` / `General ICU`. Leave blank if the department has just one instance. | Drives the **by-Sub-Department/Ward** rollup |
| **Floor** | The physical floor the asset/department sits on | Drives the **by-Floor** rollup — cabling/labor is usually planned per floor, not per department |
| **Sensor Type** | Which Sensor Catalog entry is being counted here | Drives Qty × Unit Cost = Line Total, and the **by-Category** rollup |

All four are kept — none are redundant, each answers a different planning question (function, specific instance, physical location, hardware).

---

## 3. Generic sensor catalog — re-verified against 3 sources, not 1

The first draft leaned mostly on the bottle-factory POC's sensor list ([`sesnor-fetures.md`](../sesnor-fetures.md), [`OmniView_IQ_Sensor_Summary_CEO.md`](../OmniView_IQ_Sensor_Summary_CEO.md)). This revision cross-checks every entry against:

1. **[`hd-working-brife.md`](../../hd-working-brife.md)** — OmniView's own hardware spec: Electrical (MFD), Physical Process (Temperature, Pressure, **Flow**), Environmental (**AQI**, ambient temp/humidity, atmospheric/building pressure).
2. **[`Hospital_Site_Survey_Field_Pack.docx`](Hospital_Site_Survey_Field_Pack.docx)** — the team's field-tested hospital walkdown script. Its "Attach" vocabulary is narrower: `MFM+CT | ambient | vib | pressure | HeatTag | skip`.
3. **Live web search (Aug 2026)** — India-market evidence, including two hospital-specific sensors hd-brife names but the field pack doesn't yet cover: room differential pressure and air quality.

### 3a. What changed and why

| Sensor | Verdict | Why |
|---|---|---|
| Electrical Energy Meter + CTs | Kept | Validated by field pack (`MFM+CT`) + hd-brife (electrical MFD) |
| Panel Overheating / Gas-Particle Sensor | Kept | Validated by field pack (`HeatTag`) |
| Vibration & Mechanical Health Sensor | Kept, relabeled | Field pack notes temp is co-located on the *same* node as vibration ("vib + surface temp") — relabeled to say so explicitly, so it isn't bought twice for the same asset |
| Surface/Process Temperature Sensor | Kept, reframed, repriced | hd-brife lists "Temperature Sensors" as its own hardware category for **fluid/gas** temperature — distinct from motor-surface temp, used where there's no rotating part to co-locate a vibration node on (boiler water, chiller lines). Repriced down: bare PT100/RTD probes run ₹850–1,250 in India; ₹3,000–8,000 covers probe + transmitter for gateway integration |
| Pressure Sensor / Transmitter | Kept | Validated by field pack (`pressure`, O2/NG/plant air) + hd-brife (pipe pressure) |
| Ambient Temperature & Humidity Sensor | Kept | Validated by field pack (`ambient`) + hd-brife |
| Flow Meter (ultrasonic) | Kept, flagged | hd-brife lists flow meters as core hardware; hospital water sub-metering per department/floor is confirmed real practice (web research) — **not yet** in the field pack's tested attach vocabulary, so it's flagged "confirm on-site" rather than treated as fully proven |
| Digital Pulse / Cycle Counter | **Dropped** | Not backed by the field pack *or* hd-brife — purely the bottle-factory "stroke counter" repurposed. Weak hospital analogy (lift/autoclave cycles), no source treats it as commonly bought. Removed from the catalog; a one-line note in Instructions flags it as a rare, price-separately case |
| Edge Gateway / Communication Node | Kept, **relocated** | Real and necessary, but it's shared site infrastructure — one gateway serves ~10 sensors (hd-brife). Left in the per-department dropdown, a surveyor could pick it under two departments and double-count it. **Moved out of the Site Survey dropdown**, tracked once on Cost Summary as a standalone "Site Infrastructure" line |
| **Room Differential Pressure Sensor** *(new)* | Added | hd-brife names "building internal air pressure." Web research confirms this is standard hospital infection-control practice — OT rooms run positive pressure, isolation/AIIR wards run negative pressure, continuously monitored. India-market units: ₹9,400–19,000. Distinct from the plant Pressure Sensor above — different unit (Pascals, not bar) and different purpose (compliance, not leak detection) |
| **Air Quality Sensor (AQI/Particulate/CO2)** *(new)* | Added | hd-brife explicitly names AQI as an environmental parameter. Real hospital relevance for OT/ICU air cleanliness and general IAQ. India-market PM2.5/CO2/VOC monitors: ₹11,600–60,000 (mid-tier industrial, excluding lab-grade outliers) |

### 3b. Sensor Catalog (current — 9 selectable sensor types + 1 documented-only infrastructure line)

Cost bands are India-market rates (IndiaMART, Aug 2026 — sources below). "Tentative Unit Cost" is the value the workbook's formulas actually use; Min/Max are shown for reference and negotiation range.

| Sensor Type (generic) | Category | Description / What it measures | Typical Placement (hospital) | Cost Min (₹) | Cost Max (₹) | Tentative Unit Cost (₹) |
|---|---|---|---|---|---|---|
| **Electrical Energy Meter + Current Transformers** | Electrical | 3-phase kW/kVA/PF/voltage/current/kWh at a feeder or panel, non-invasive split-core CTs | Transformer incomer, DG output, department sub-panel, MCC | 8,000 | 20,000 | 14,000 |
| **Panel Overheating / Gas-Particle Sensor** | Electrical / Safety | Detects early cable/connection overheating and micro-particles inside enclosed panels before smoke/fire | HT/LT switchboards, breaker panels, enclosed electrical cabinets | 40,000 | 80,000 | 60,000 |
| **Vibration & Mechanical Health Sensor** (incl. co-located surface temp) | Physical (Mechanical) | Triaxial vibration velocity + surface temp on the *same* node — imbalance, bearing wear, misalignment | Chiller compressors, pumps (CHW/CDW/water/STP), AHU fan motors, DG engine, lift machinery | 15,000 | 35,000 | 25,000 |
| **Standalone Process/Fluid Temperature Sensor** (RTD, no rotating part) | Physical | Fluid/gas temperature, rate-of-rise, where there's no motor to co-locate a vib node on | Boiler water, chiller supply/return lines, calorifier/DHW, cold-storage/pharmacy fridge | 3,000 | 8,000 | 5,500 |
| **Pressure Sensor / Transmitter** (plant/utility, bar range) | Physical | Line pressure (bar), drop-rate — leak / low-supply detection | O2 manifold, medical air line, plant compressed air, water supply line, boiler | 6,000 | 15,000 | 10,000 |
| **Room Differential Pressure Sensor** (Pa range, OT/isolation) | Environmental / Compliance | Room-to-corridor pressure differential — confirms OT positive / isolation negative pressure | Operation Theatre, Isolation/AIIR wards, clean rooms, laminar-flow areas | 9,400 | 19,000 | 14,000 |
| **Ambient Temperature & Humidity Sensor** | Environmental | Room °C / %RH baseline | OT, ICU, wards, pharmacy, server/IT room, blood bank, plant room | 3,000 | 8,000 | 5,500 |
| **Air Quality Sensor** (AQI/Particulate/CO2) | Environmental | PM2.5/PM10/CO2/VOC indoor air quality index | OT/ICU air cleanliness, general indoor air quality | 11,600 | 60,000 | 25,000 |
| **Flow Meter** (Ultrasonic, non-invasive) — *flagged, confirm on-site* | Physical | Liquid/gas flow rate, clamp-on, no pipe-cut install | Water supply lines, oxygen/medical-gas lines, DHW/calorifier | 50,000 | 85,000 | 65,000 |
| **Edge Gateway / Communication Node** — *documented only, not in Site Survey dropdown* | Infrastructure (shared, once per site) | Aggregates data from ~10 nearby sensors, pushes to cloud | Near main electrical room / MCC | 5,000 | 12,000 | 8,000 |

All prices exclude GST, installation, and cabling — per your answer, no contingency markup is applied; the workbook totals are pure sensor cost. Gateway cost is tracked separately (see §5) so it's never multiplied by department count.

**Pricing sources (IndiaMART / web listings, Aug 2026):**
[Three-phase multifunction energy meters](https://dir.indiamart.com/impcat/three-phase-digital-energy-meter.html) · [Wireless panel/cable overheating sensors](https://dir.indiamart.com/impcat/wireless-sensors.html) · [Wireless vibration + temperature sensors](https://dir.indiamart.com/impcat/wireless-vibration-sensor.html) · [4–20mA pressure transmitters](https://dir.indiamart.com/impcat/pressure-transmitters.html) · [PT100/RTD temperature sensors](https://dir.indiamart.com/impcat/pt100-temperature-sensor.html) · [Hospital isolation/OT room pressure monitors](https://www.indiamart.com/proddetail/isolation-room-pressure-monitor-4344700291.html) · [Indoor air quality (PM2.5/CO2) monitors](https://dir.indiamart.com/impcat/air-quality-monitors.html) · [Wireless ambient temperature/humidity sensors](https://dir.indiamart.com/impcat/wireless-sensors.html) · [Clamp-on ultrasonic flow meters](https://dir.indiamart.com/impcat/ultrasonic-flow-meter.html) · [RS485 Modbus-to-cloud IoT gateways](https://www.indiamart.com/proddetail/rs485-modbus-rtu-to-mqtt-gprs-gateway-20126353212.html)

---

## 4. Department master list (draft — editable dropdown)

Generic hospital departments, generalized from a large multi-specialty hospital (Apollo-style) down to what a basic general hospital has too, plus the **utility/plant spaces** that actually carry the sensors (since sensors attach to feeders/plant rooms, not to clinical department names):

**Clinical / patient-facing (for department count + rough sizing only — no clinical sensors placed here):**
Emergency / Casualty · ICU (general or split MICU/SICU/NICU/PICU) · Operation Theatre (OT) Complex · OPD · General Wards · Private/Semi-Private Rooms · Radiology & Imaging · Pathology / Lab · Pharmacy · Blood Bank · Physiotherapy & Rehab

**Support / back-of-house:**
CSSD (Central Sterile Services) · Laundry · Kitchen / Dietary · Housekeeping & Waste

**Facility / utility (this is where most sensors actually go):**
Electrical Room / Transformer / Incomer · DG + ATS Room · Boiler Room · HVAC Plant / Chiller Room · Medical Gas Plant (O2 / medical air / vacuum / NG) · Lifts · Server / IT / BMS Room · Water Supply / STP-ETP Pump House

**Administrative:**
Reception / Billing / Admin · Biomedical Engineering

Each row will just be a name + a free-text "notes" column — you add/remove rows per hospital as needed, and the dropdown in the Site Survey sheet updates automatically.

---

## 5. How the auto-calculation works

Per row in **Site Survey**:

```
Line Total = Quantity × Unit Cost
```

Unit Cost defaults from the Sensor Catalog lookup (INDEX/MATCH by Sensor Type) but stays editable per row, in case a hospital's actual site conditions push the price up/down.

**Cost Summary** sheet then sums:
- **Site Infrastructure** (top of sheet) — a standalone "number of gateways × unit cost" box, separate from the department sensor lines, since a gateway is shared across ~10 sensors and would double-count if it lived in the per-department dropdown (see §3a)
- **Sensor Hardware Total** — sum of every Site Survey line
- **GRAND TOTAL** — Sensor Hardware Total + Site Infrastructure Total
- Total per Department, per Floor, per Sensor Category (auto, SUMIFS off Site Survey)
- Total per **Sub-Department / Ward Name** — a small manual-pivot table: type the Department + Ward Name combos you used in Site Survey (copy-paste), the Total Cost column fills in automatically via SUMIFS

---

## 6. Decisions (confirmed)

1. **One workbook per hospital (client).** The delivered file is a **template** — copy it per hospital, rename with the hospital name, fill in.
2. **Departments can have multiple named sub-units under one department type.** e.g. Department = `ICU`, with separate Site Survey rows for "General ICU", "Gynec ICU", "TB ICU", "Paediatric ICU" — each with its own floor, sensors, and counts. The Site Survey sheet has a dedicated **Sub-Department / Ward Name** column for this.
3. **Cost rollup: per department, per floor, then grand total.** The Site Survey sheet has a **Floor** column (dropdown); Cost Summary auto-rolls up by Department, by Floor, and a single Grand Total — plus a by-sensor-category breakdown as a bonus (uses the same underlying data, no extra entry work).
4. **Cost bands refreshed from live web search** (IndiaMART, Aug 2026) instead of the old CEO-brief vendor prices — see the updated table in §3 with sources.
5. **No GST/install/cabling contingency line.** Cost Summary totals are pure sensor cost only (Qty × Unit Cost, summed) — nothing added on top.
6. **Sensor catalog re-verified against 3 sources** (hd-working-brife.md, the Hospital Site Survey Field Pack, live web research) instead of just the bottle-factory list — see §3a for the full reasoning. Net effect: dropped Digital Pulse/Cycle Counter (no hospital backing), added Room Differential Pressure + Air Quality (both backed by hd-brife and real hospital practice), relabeled/repriced the Vibration and Temperature rows to remove ambiguity.
7. **Edge Gateway moved out of the per-department picklist**, tracked once as a "Site Infrastructure" line on Cost Summary — see §5.
8. **Sub-Department / Ward Name now gets its own cost rollup** on Cost Summary (manual-pivot table, fill Department + Ward, cost auto-calculates).

---

## 7. Delivered

Built: [`Hospital_Device_Sensor_Master_Tracker_TEMPLATE.xlsx`](Hospital_Device_Sensor_Master_Tracker_TEMPLATE.xlsx)

- **Instructions** — how to use, field definitions, the gateway relocation explained in plain language, the Pulse Counter caveat, scope note, cost basis.
- **Sensor Catalog** — the 9 re-verified generic sensor types from §3b, no vendor names, client-shareable, plus the Edge Gateway documented (but not selectable) as infrastructure.
- **Department Master** — editable department list (§4), add rows to extend the dropdown.
- **Site Survey** — main entry grid with dropdowns (Department, Floor, Sensor Type — Gateway excluded), auto-filled/overridable Unit Cost, formula-driven Line Total, 4 example rows showing the format (multi-ICU, and the new Room Differential Pressure sensor on an OT).
- **Cost Summary** — Site Infrastructure box, Sensor Hardware Total, Grand Total, Total by Department, Total by Floor, Total by Sensor Category, Total by Sub-Department/Ward — all formula-driven (SUMIFS/INDEX-MATCH), recalculates live as you fill in Site Survey.

All formulas verified via LibreOffice recalculation (0 errors across 699 formulas). Spot-checked: Grand Total ₹91,500 = ₹83,500 sensor hardware (4 example rows) + ₹8,000 site infrastructure (1 gateway); Gynec ICU sub-department subtotal ₹19,500 matches its two example rows exactly.
