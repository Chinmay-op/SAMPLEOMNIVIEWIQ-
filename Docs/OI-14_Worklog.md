# OI-14: Payload Validation + Schema Versioning

## Context
DevB is preparing JSON schemas (OI-23) that define the data contract for each of the 7 sensor families. To maintain a clean TimescaleDB (as owned by DevC), the MQTT subscriber needs to intercept and validate incoming payloads against these schemas before running the idempotent insert.

## Implementation Details
1. **Dependency Added**: Added `jsonschema>=4.0,<5.0` to `requirements.txt` and `pyproject.toml` as it is the industry standard for JSON Schema validation in Python.
2. **Validation Module**: Created `src/omniview/ingest/validation.py` exposing a `validate_payload` function. 
3. **Placeholder Schema**: Since DevB's final schemas aren't delivered yet, a placeholder JSON Schema for `electrical` was defined locally (requiring `kva`, `kw`, `pf`). All other sensor types bypass validation for now, allowing parallel development.
4. **Subscriber Integration**: Updated `subscriber.py` to extract the `schema_version` and validate the `data` payload. Invalid payloads increment a `validation_failures` counter and are safely skipped.
5. **Testing**: 
    - Added unit tests for validation (`tests/test_validation.py`).
    - Updated `tests/test_subscriber.py` mock payloads to be schema-compliant.
    - Added a test to verify that invalid payloads are indeed skipped and metrics are correctly incremented.

## Output
- Payload schema validation layer is successfully integrated into the ingest bridge.
- Awaiting DevB's final JSON schemas to replace the placeholder `electrical` schema and populate the rest.
