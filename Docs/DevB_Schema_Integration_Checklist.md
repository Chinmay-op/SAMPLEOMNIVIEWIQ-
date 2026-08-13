# DevB Schema Integration Checklist

**Purpose:** When Vibhanshu (DevB) delivers the official JSON schemas for all 7 sensor families (OI-23, OI-5, OI-6, OI-7), the following files **must** be updated to replace the current placeholder schemas with the real ones.

**Status:** ⏳ WAITING ON DEVB  
**Blocked by:** OI-23 (Vibhanshu — JSON schema definitions for all sensor families)

---

## Files to Change

### 1. `src/omniview/ingest/validation.py`
**What to do:**
- Replace the `_PLACEHOLDER_ELECTRICAL_SCHEMA` dict with the official electrical schema from DevB.
- Add real schemas for the remaining 6 sensor families to the `_SCHEMAS` dict:
  - `vibration`
  - `thermal`
  - `pressure`
  - `gas`
  - `stroke`
  - `ambient`
- Once all 7 schemas are populated, the `validate_payload()` function will automatically enforce them — no logic changes needed, just populate the `_SCHEMAS` dictionary.

### 2. `tests/test_validation.py`
**What to do:**
- Add test cases for each of the 6 new sensor schemas (valid payload, missing required fields, wrong types).
- Update the `test_validate_payload_unknown_sensor_type` test — once all 7 schemas are defined, there are no "unknown" types that bypass validation. Replace it with explicit tests for each family.

### 3. `tests/test_subscriber.py`
**What to do:**
- Review all mock payloads in existing tests. Any test that sends data for a sensor type that now has a real schema must use a schema-valid payload, or the test will fail due to validation rejecting it.
- Specifically check: `test_missing_timestamp_uses_arrival_time` (sends `thermal` data), `test_unix_timestamp_parsed` (sends `pressure` data), and `test_payload_without_data_key_uses_full_payload` (sends `electrical` data — already compliant).

### 4. `src/omniview/edge/injector.py` *(if synthetic generator fields change)*
**What to do:**
- If DevB's official electrical schema renames or adds required fields beyond `kva`, `kw`, `pf`, verify the synthetic generator's `ELECTRICAL_FIELDS` list still produces compliant payloads.
- This is only needed if the field names or required fields differ from what's currently generated.

---

## Files That Do NOT Need Changes

| File | Why |
|------|-----|
| `subscriber.py` | Already calls `validate_payload()` — no code change needed, it will automatically enforce whatever schemas are in `validation.py`. |
| `db.py` | Schema-agnostic — stores everything as JSONB. No changes needed. |
| `config.py` | No schema-related config. |
| `topics.py` | Topic hierarchy is independent of payload schemas. |
| `__init__.py` (ingest) | Already exports `validate_payload`. |

---

## Quick Summary

| # | File | Action |
|---|------|--------|
| 1 | `src/omniview/ingest/validation.py` | Replace placeholder + add 6 new schemas |
| 2 | `tests/test_validation.py` | Add tests for all 7 families |
| 3 | `tests/test_subscriber.py` | Fix mock payloads to be schema-compliant |
| 4 | `src/omniview/edge/injector.py` | Verify field names match (only if changed) |

**Total files to touch: 3 guaranteed + 1 conditional**

---

*Created: 13 August 2026*  
*Context: OI-14 used placeholder schemas because DevB schemas weren't ready yet.*
