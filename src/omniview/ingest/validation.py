"""
Payload Validation — OI-14
==========================

Validates incoming MQTT payloads against JSON schemas.
If a payload is invalid, it is logged and skipped to prevent Database contamination.

Updated with real DevB schemas for all 7 sensor families.
"""

import json
import logging
from pathlib import Path
from typing import Any
import jsonschema
from jsonschema.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ── Load real schemas from repo root ────────────────────────────────────────
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"


def _load_schema(filename: str) -> dict | None:
    """Load a JSON schema file from the schemas/ directory."""
    path = _SCHEMA_DIR / filename
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    logger.warning("Schema file not found: %s", path)
    return None


# Mapping of sensor_type (from topics.py SENSOR_TYPES) → JSON schema
_SCHEMAS = {
    "electrical": _load_schema("electrical_schema.json"),
    "vibration":  _load_schema("vibration_schema.json"),
    "thermal":    _load_schema("thermal_schema.json"),
    "pressure":   _load_schema("pressure_schema.json"),
    "stroke":     _load_schema("stroke_schema.json"),
    "gas":        _load_schema("gas_schema.json"),
    "ambient":    _load_schema("ambient_schema.json"),
}


def validate_payload(sensor_type: str, schema_version: str, payload: dict[str, Any]) -> bool:
    """Validate a sensor payload against its corresponding JSON schema.

    Strips envelope-level transport fields (``scenario_label``,
    ``schema_version``) before validation — these are not part of the
    raw telemetry schema but are added by the ingestion pipeline and
    rule engine.  The JSON schemas enforce ``additionalProperties: false``
    and must NOT be modified to accommodate transport fields.

    Parameters
    ----------
    sensor_type : str
        The type of sensor (e.g. "electrical").
    schema_version : str
        The version of the schema.
    payload : dict
        The data dictionary to validate.

    Returns
    -------
    bool
        True if the payload is valid or if no schema is currently defined.
        False if the payload is invalid.
    """
    schema = _SCHEMAS.get(sensor_type)
    
    if not schema:
        # If no schema is defined yet, we allow the payload 
        # through so we don't block development on other sensors.
        logger.debug("No schema defined for sensor_type %r, allowing payload.", sensor_type)
        return True

    # Strip envelope-level transport fields before validation.
    # These are not part of the raw telemetry contract.
    _ENVELOPE_FIELDS = {"scenario_label", "schema_version"}
    clean_payload = {k: v for k, v in payload.items() if k not in _ENVELOPE_FIELDS}
        
    try:
        jsonschema.validate(instance=clean_payload, schema=schema)
        return True
    except ValidationError as e:
        logger.warning(
            "Payload validation failed for sensor_type %r (v%s): %s",
            sensor_type, schema_version, e.message
        )
        return False
