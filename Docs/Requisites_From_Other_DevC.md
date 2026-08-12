# Requisites From Other DevC Team Members

**Purpose:** Things that DevB (Vibhanshu) and Lead (Dnyandev) need to fill in / deliver so that the DevC platform layer works end-to-end.  
**Author:** Chinmay Wadettiwar (DevC)  
**Sprint:** OI Sprint 1  
**Last Updated:** 11 August 2026

---

## From DevB (Vibhanshu) — Sensor Schemas + Bots

### ✅ What DevC Currently Has Working
The platform is built and tested with **synthetic data** and hardcoded assumptions. The following needs to be replaced/validated by DevB:

| # | Requisite | Why DevC Needs It | Jira | Status | Filled In? |
|---|-----------|-------------------|------|--------|------------|
| 1 | **Electrical schema (JSON schema file)** | `subscriber.py` stores payload in JSONB. We need the final field list to validate incoming data and ensure `data->>'kva'` type queries work correctly. | OI-23 | ⬜ Waiting | ☐ |
| 2 | **Vibration schema** | Need to know the exact fields (rms_velocity, accel_x/y/z, etc.) so `readings_vibration` JSONB is queryable. | OI-5 | ⬜ Waiting | ☐ |
| 3 | **Thermal schema** | Fields for surface temp, barrel zone temp, etc. | OI-6 | ⬜ Waiting | ☐ |
| 4 | **Pressure schema** | Fields for bar reading, decay rate, etc. | OI-7 | ⬜ Waiting | ☐ |
| 5 | **Gas, Stroke, Ambient schemas** | Remaining 3 sensor families. | OI-45/46/47 | ⬜ Waiting | ☐ |
| 6 | **Electrical CSV replay bot output format** | The injector has 80+ column aliases, but we need the **final** CSV column headers from DevB's replay bot so we can validate the alias map is complete. | OI-8 | ⬜ Waiting | ☐ |
| 7 | **Sample CSV file (5-10 rows)** | For integration testing. Injector currently uses synthetic data. Need a real DevB-produced CSV to confirm end-to-end. | OI-8 | ⬜ Waiting | ☐ |
| 8 | **Schema version string convention** | Currently defaulting to `"1.0"`. Need DevB's versioning convention (semver? date-based?) so `schema_version` column is consistent. | OI-23 | ⬜ Waiting | ☐ |

### Format Expected
For each schema, please provide:
```json
{
  "sensor_type": "electrical",
  "schema_version": "1.0.0",
  "fields": {
    "field_name": { "type": "float", "unit": "kVA", "description": "..." },
    ...
  }
}
```

---

## From Lead (Dnyandev) — Contracts + Rule Engine

| # | Requisite | Why DevC Needs It | Jira | Status | Filled In? |
|---|-----------|-------------------|------|--------|------------|
| 1 | **Layer 3 architecture contracts** | Need the final contract spec so `ingest/` module boundaries are confirmed. Currently built to our best understanding. | OI-42 | ⬜ Waiting | ☐ |
| 2 | **Rule engine event output format** | Dashboard (OI-68) will consume rule engine events (MD alert, lazy-idle, vib zone). Need the event payload schema to build action cards. | OI-56-61 | ⬜ Waiting | ☐ |
| 3 | **`maintenance_risk` event schema** | Health Index trend widget on dashboard needs this event format. | OI-62-67 | ⬜ Waiting | ☐ |
| 4 | **Monetize / ₹ hero metric format** | Dashboard hero card will show "₹ penalty avoided". Need the output format from the monetize module. | OI-70 | ⬜ Waiting | ☐ |
| 5 | **Alert priority levels** | For alert routing stub (OI-69). Need to know priority tiers (critical/warning/info) and which rules map to which tier. | OI-60 | ⬜ Waiting | ☐ |
| 6 | **Scenario injector label format** | If scenarios produce labeled events, need the label schema so the subscriber can store/skip them appropriately. | OI-50 | ⬜ Waiting | ☐ |
| 7 | **Contracted demand value confirmation** | Currently using `500 kVA` from `.env.example`. Need confirmation this is the correct Pune ISBM-PET site value, or the actual value. | OI-42 | ⬜ Waiting | ☐ |

---

## Action Items for Next Standup

1. **Vibhanshu**: Can you share even a draft of the electrical schema (OI-23)? We can start validating the subscriber pipeline today.
2. **Vibhanshu**: A sample 5-row CSV from the electrical replay bot (OI-8) would let us test the injector alias mapping.
3. **Dnyandev**: What format will rule engine events take? Even a rough JSON example would help us start the dashboard action cards.
4. **Dnyandev**: Confirmed contracted demand for Pune site?

---

## How to Fill In

1. Update the **"Filled In?"** column to ☑ when delivered.
2. Add the file/link/value in the **"Status"** column.
3. Ping Chinmay on the team channel once updated.

---

*This is a living document — update as requisites are delivered.*
