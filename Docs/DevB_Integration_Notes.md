# Notes for DevB (Vibhanshu) — Integration Handoff

**From**: DevC (Chinmay) · `chinmay` branch · 11 Sep 2026  
**Status**: 712/712 tests green on `chinmay`. Gate 0 cleared on our side.

---

## What We Fixed on Our Side

| Item | What | Commit |
|------|------|--------|
| Bot API signature | `seed.py` adapted to your no-arg `generate_reading()` | `e0a1798` |
| V2→V3 migration tests | Rewrote tests for plain `scenario_label TEXT` column | `ca640fb` |
| `build_payload()` signature | Tests updated for your new `device_id` first param | `ca640fb` |
| Working tree cleanup | 13 modified files from merge committed & pushed | `620fd52` |

---

## What You Need to Fix (Phase B — your ownership)

### 1. Schema `sensor_type` const values — contract mismatch

Your schemas use descriptive names. The Layer 3 contract (§2) and `SENSOR_TYPES` in `topics.py` use short names. This will break validation when we integrate.

| Schema file | Your `const` | Contract says | 
|-------------|-------------|---------------|
| `electrical_schema.json` | `electrical_meter` | `electrical` |
| `vibration_schema.json` | `vibration_node` | `vibration` |
| `thermal_schema.json` | `thermal_probe` | `thermal` |
| `pressure_schema.json` | `pressure_transmitter` | `pressure` |
| `gas_schema.json` | `gas_particle_sensor` | `gas` |
| `stroke_schema.json` | `digital_pulse_counter` | `stroke` |
| `ambient_schema.json` | `ambient_weather` | `ambient` |

**Action**: Update the `"const"` value in each schema's `sensor_type` field to the short name.

### 2. `schema_version` missing from all schemas

None of the 7 schemas declare a `schema_version` field. Our seed script hardcodes `"1.0"` but the envelope contract requires it.

**Action**: Add `"schema_version": {"type": "string", "const": "1.0"}` to each schema's `properties` and `required` array.

### 3. Edge-computed `rolling_kva_15min` violates §4.1

`electrical_schema.json` includes `rolling_kva_15min` as a bot output field. Per contract §4.1, window math happens server-side (TSDB/rules), not on the edge.

**Action**: Remove `rolling_kva_15min` from the schema. If the bot computes it, keep it as a convenience field but mark it non-required and document it as edge-local only.

---

## Your Top Priority After Phase B: Stroke Bot (Phase F)

The `stroke_bot.py` exists but has **no schema field, no MQTT wiring, no rule**. It's the **#1 blocker** in the project — three features wait on it:

- **W5** — Specific energy consumption  
- **W7 / Hero 3** — kWh per 1,000 bottles  
- **H1** — Molding rate for pressure health  

**What's needed** (per Lead's Phase F spec):
- `stroke_bot` emits: `cycle_count`, `cycle_duration_s`, `machine_state`
- Synthetic pulse train tied to electrical on/off state
- `synthetic: true` flag in payload
- Rows land in `readings_stroke` via MQTT topic `omniview/{site}/compressor-01/stroke`

**Acceptance**: Bot emits schema-valid stroke rows; count increments only when electrical says "running"; idle gaps recorded.

---

## When We Integrate

When you're ready, we merge on `integration/live-spine`. Our side expects:
1. Short `sensor_type` names in payloads
2. `schema_version` in the envelope
3. No edge-computed window fields in schema

If you push your fixes to `production_branch`, ping me and I'll pull + test.
